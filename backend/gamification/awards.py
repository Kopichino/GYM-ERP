"""Deciding which badges a member has earned.

The numbers a badge is measured against are all derived -- visits, streaks,
sessions, sets, records, months joined are counted from rows that already
exist. The only thing written down is the award itself, because "you earned
this on this date" is a fact nothing else records.

Awards are one-way on purpose. A badge that could be taken back after a quiet
month is not a badge, it is a status bar, and it would make the thing worthless
to earn.
"""

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from attendance.services import streaks, visit_dates
from schedule_app.models import BookingStatus, ClassBooking
from workouts.models import WorkoutLog, WorkoutSession

from .models import Badge, Criterion, MemberBadge, PersonalRecord


def _months_since(day, today):
    if day is None:
        return 0
    months = (today.year - day.year) * 12 + (today.month - day.month)
    # Not a full month until the day-of-month comes round again.
    return max(months - (1 if today.day < day.day else 0), 0)


def month_streak(dates):
    """Longest run of consecutive calendar months with at least one visit.

    A daily streak long enough to mean "kept it up for six months" is not
    something anybody actually does, so the half-year milestone is measured in
    months that were trained in rather than days in a row.
    """
    months = sorted({(day.year, day.month) for day in dates})
    if not months:
        return 0

    longest = run = 1
    for previous, current in zip(months, months[1:]):
        # The month after (y, 12) is (y + 1, 1).
        expected = (previous[0] + (previous[1] == 12), (previous[1] % 12) + 1)
        run = run + 1 if current == expected else 1
        longest = max(longest, run)
    return longest


def best_lift(member, exercise_id):
    """The heaviest the member has ever gone on one exercise, in kg.

    Read off the personal records rather than the raw log, so it is already
    normalised out of pounds and already excludes the bodyweight movements
    logged at zero.
    """
    return PersonalRecord.objects.filter(
        member=member, exercise_id=exercise_id
    ).aggregate(best=Max("weight_kg"))["best"] or Decimal("0")


def current_values(member, today=None):
    """Every number a badge can be measured against, for one member."""
    today = today or timezone.localdate()
    dates = visit_dates(member)
    _, longest = streaks(member, dates)
    profile = getattr(member, "profile", None)

    return {
        # Distinct days, not raw check-in rows: someone who steps out for lunch
        # and back has been to the gym once.
        Criterion.VISITS: len(dates),
        Criterion.STREAK: longest,
        Criterion.WORKOUTS: WorkoutSession.objects.filter(user=member).count(),
        Criterion.SETS: WorkoutLog.objects.filter(session__user=member).count(),
        Criterion.RECORDS: PersonalRecord.objects.filter(member=member).count(),
        Criterion.MONTHS: _months_since(getattr(profile, "join_date", None), today),
        # Only classes actually marked off by a trainer. Counting a booking the
        # member never turned up for would make the badge a badge for booking.
        Criterion.CLASSES: ClassBooking.objects.filter(
            member=member, status=BookingStatus.ATTENDED
        ).count(),
        Criterion.MONTH_STREAK: month_streak(dates),
    }


def value_for(badge, member, values):
    """Where the member stands against one badge.

    Lift badges are the odd one out: they are measured per exercise, so they
    cannot live in the single `values` dict the counting criteria share.
    """
    if badge.criterion == Criterion.LIFT:
        return best_lift(member, badge.exercise_id)
    return values.get(badge.criterion, 0)


def evaluate(member, today=None):
    """Award any badge the member now qualifies for. Returns the new ones.

    Safe to call as often as you like: the unique constraint on
    (member, badge) is what makes a second run a no-op, not a check that could
    race with another request.
    """
    today = today or timezone.localdate()
    values = current_values(member, today)
    held = set(
        MemberBadge.objects.filter(member=member).values_list("badge_id", flat=True)
    )

    awarded = []
    for badge in Badge.objects.filter(is_active=True):
        if badge.id in held:
            continue
        value = value_for(badge, member, values)
        if value < badge.threshold:
            continue
        try:
            with transaction.atomic():
                awarded.append(
                    MemberBadge.objects.create(
                        member=member,
                        badge=badge,
                        awarded_on=today,
                        # Kilograms round down to whole numbers here; the
                        # column counts things, and "lifted 102kg" is close
                        # enough to explain a 100kg badge.
                        value_at_award=int(value),
                    )
                )
        except IntegrityError:
            # Two requests evaluated at once; the constraint decided, and the
            # member has the badge either way.
            continue
    return awarded


def progress(member, today=None):
    """Every active badge with where the member stands against it.

    Locked badges are returned too, with their current number -- a ladder you
    cannot see the next rung of is not motivating, it is a surprise.
    """
    today = today or timezone.localdate()
    values = current_values(member, today)
    held = {
        award.badge_id: award
        for award in MemberBadge.objects.filter(member=member).select_related("badge")
    }

    rows = []
    for badge in Badge.objects.filter(is_active=True).select_related("exercise"):
        award = held.get(badge.id)
        value = value_for(badge, member, values)
        rows.append(
            {
                "badge": badge,
                "earned": award is not None,
                "awarded_on": award.awarded_on if award else None,
                # What they had when it was awarded, not what they have now --
                # otherwise an old badge's number keeps climbing after the fact.
                "value": award.value_at_award if award else int(value),
                "threshold": badge.threshold,
                "percent": min(round(value * 100 / badge.threshold), 100)
                if badge.threshold
                else 100,
            }
        )
    # Earned first, then whatever they are closest to finishing.
    rows.sort(key=lambda row: (not row["earned"], -row["percent"], row["badge"].tier))
    return rows
