"""The strength-to-bodyweight leaderboard.

Scored on `weight / bodyweight at the time of the lift`, so a 60kg member who
squats their own bodyweight twice over outranks a 100kg member lifting more
absolute weight. Using *current* bodyweight instead would rewrite the board
every time somebody was weighed, which is why the snapshot lives on the record.

Two rules keep it honest rather than merely fun:

* Opt-in. Nobody's lifts appear because a feature shipped.
* It resets every month, so the board is about who is training now rather than
  a permanent monument to one lift from two years ago.
"""

from datetime import date
from math import ceil

from django.utils import timezone

from .models import GamificationProfile, PersonalRecord


def month_bounds(year=None, month=None, today=None):
    """First and last day of the month being scored, defaulting to this one."""
    today = today or timezone.localdate()
    year = year or today.year
    month = month or today.month
    start = date(year, month, 1)
    end = date(year + (month == 12), (month % 12) + 1, 1)
    return start, end


def board(exercise_id=None, year=None, month=None, today=None, limit=25):
    """Ranked rows for one exercise in one month.

    Records with no bodyweight snapshot are left out entirely rather than
    guessed at -- a member who had never been weighed has a real PR, but not a
    ratio, and inventing one would put them somewhere they did not earn.
    """
    start, end = month_bounds(year, month, today)

    opted_in = GamificationProfile.objects.filter(leaderboard_opt_in=True).values_list(
        "user_id", flat=True
    )

    records = (
        PersonalRecord.objects.filter(
            member_id__in=opted_in,
            achieved_on__gte=start,
            achieved_on__lt=end,
            bodyweight_kg__isnull=False,
        )
        .select_related("member", "exercise")
    )
    if exercise_id:
        records = records.filter(exercise_id=exercise_id)

    # One entry per member per exercise: their best ratio that month, not every
    # session they improved in.
    best = {}
    for record in records:
        ratio = record.ratio
        if ratio is None:
            continue
        key = (record.member_id, record.exercise_id)
        if key not in best or ratio > best[key]["ratio"]:
            best[key] = {
                "member_id": record.member_id,
                "username": record.member.username,
                "full_name": record.member.get_full_name(),
                "exercise_id": record.exercise_id,
                "exercise": record.exercise.name,
                "weight_kg": record.weight_kg,
                "reps": record.reps,
                "bodyweight_kg": record.bodyweight_kg,
                "ratio": ratio,
                "achieved_on": record.achieved_on,
            }

    rows = sorted(best.values(), key=lambda row: row["ratio"], reverse=True)[:limit]
    for position, row in enumerate(rows, start=1):
        row["rank"] = position
    return {"month_start": start, "rows": rows}


#: Below this many people, a percentile stops being anonymous. "Top 33%" of a
#: pool of three, in a gym where everyone knows who trains, names somebody.
MIN_POOL = 5


def _ratios(exercise_id, start, end):
    """Every member's best ratio for one exercise in one month.

    Deliberately *not* filtered to opt-ins. This feeds the private view only:
    it produces a single anonymous denominator and never leaves this module as
    a list of people. Opting out is about not being *named* on a public board,
    which nothing here does.
    """
    best = {}
    records = PersonalRecord.objects.filter(
        exercise_id=exercise_id,
        achieved_on__gte=start,
        achieved_on__lt=end,
        bodyweight_kg__isnull=False,
    ).only("member_id", "weight_kg", "bodyweight_kg")

    for record in records:
        ratio = record.ratio
        if ratio is None:
            continue
        if record.member_id not in best or ratio > best[record.member_id]:
            best[record.member_id] = ratio
    return best


def my_standing(member, exercise_id, year=None, month=None, today=None):
    """Where one member sits, told only to them.

    The "just for me" mode: a member who wants nothing to do with a public
    board can still see whether they are moving, without their name appearing
    anywhere and without learning anyone else's. Nothing in the return value
    identifies another person -- only a count and a position.
    """
    start, end = month_bounds(year, month, today)
    best = _ratios(exercise_id, start, end)

    mine = best.get(member.id)
    pool = len(best)

    if mine is None:
        return {
            "month_start": start,
            "exercise_id": exercise_id,
            "ratio": None,
            "pool": pool,
            "rank": None,
            "top_percent": None,
            "better_than": None,
            "reason": (
                "No scored lift on this exercise this month. A record counts "
                "once you have been weighed, so the ratio has a bodyweight to "
                "divide by."
            ),
        }

    if pool < MIN_POOL:
        return {
            "month_start": start,
            "exercise_id": exercise_id,
            "ratio": mine,
            "pool": pool,
            "rank": None,
            "top_percent": None,
            "better_than": None,
            "reason": (
                f"Only {pool} member{'' if pool == 1 else 's'} "
                f"{'has' if pool == 1 else 'have'} a scored lift on this "
                "exercise this month — too few to place you without giving "
                "away who they are."
            ),
        }

    # Standard competition ranking: everybody strictly above you, plus one.
    rank = sum(1 for ratio in best.values() if ratio > mine) + 1

    return {
        "month_start": start,
        "exercise_id": exercise_id,
        "ratio": mine,
        "pool": pool,
        "rank": rank,
        # Two numbers rather than one "percentile", because that word is read
        # both ways round and the difference matters to the person reading it.
        # Rank 1 of 10 is the *top 10%* and is *better than 90%* -- both true,
        # neither derivable from the other without knowing which convention
        # the number was built with.
        "top_percent": ceil(rank * 100 / pool),
        "better_than": round((pool - rank) * 100 / pool),
        "reason": None,
    }
