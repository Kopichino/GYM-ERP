"""Working out personal records from the workout log.

A PR is not something a member enters -- it is the heaviest set they have
actually logged, found by reading the log. So this rebuilds the record set from
those logs and reconciles it with what is stored, which makes it idempotent:
running it twice changes nothing, and a deleted set takes its record with it.

The one thing that genuinely has to be *stored* is the member's bodyweight at
the moment of the lift. Everything else here could be recomputed, but that
number cannot: once the member is weighed again, what they weighed last March
is gone from anywhere else the leaderboard could ask.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from bodystats.models import BodyMeasurement
from workouts.models import WorkoutLog

from .models import PersonalRecord

# One pound in kilograms. Logs are stored in whichever unit the member typed,
# so everything is normalised before two lifts are ever compared.
LB_IN_KG = Decimal("0.45359237")
TWO_DP = Decimal("0.01")

#: How recent a record has to be for the member to be shown a "new PR"
#: moment. Anything older is stamped as seen the instant it is created --
#: importing a member's back catalogue should not greet them with fifty
#: celebrations for lifts they did last year and already know about.
CELEBRATE_WITHIN_DAYS = 14


def to_kg(weight, unit):
    value = Decimal(weight)
    return (value * LB_IN_KG if unit == "lb" else value).quantize(TWO_DP)


def _bodyweight_on(measurements, day):
    """What the member weighed on or before `day`.

    Deliberately never looks forward. Using a later weigh-in would score a lift
    against a body the member did not have yet, which is exactly the distortion
    the snapshot exists to avoid.
    """
    for recorded_on, weight in measurements:
        if recorded_on <= day:
            return weight
    return None


def sync_records(member):
    """Rebuild `member`'s records from their logs. Returns the stored records.

    Cheap enough to call on read: a member's whole lifting history is a few
    hundred rows, and the alternative -- hooking the workout write path -- would
    put badge bookkeeping in front of someone logging a set.
    """
    logs = (
        WorkoutLog.objects.filter(session__user=member)
        .select_related("session", "exercise")
        .order_by("session__date", "id")
    )

    # Newest first, so the first row that is on or before a date is the one
    # that was current then.
    measurements = list(
        BodyMeasurement.objects.filter(user=member)
        .order_by("-recorded_on")
        .values_list("recorded_on", "weight_kg")
    )

    # (exercise_id, date) -> the best set that day; plus the running best per
    # exercise, so only a set that beats everything before it becomes a record.
    best_by_day = {}
    for log in logs:
        weight = to_kg(log.weight, log.weight_unit)
        if weight <= 0:
            # Bodyweight movements are logged at zero; they are real training
            # but they are not a weight record.
            continue
        key = (log.exercise_id, log.session.date)
        current = best_by_day.get(key)
        if current is None or weight > current["weight"]:
            best_by_day[key] = {"weight": weight, "log": log, "reps": log.reps}

    running_best = {}
    wanted = {}
    for (exercise_id, day), entry in sorted(best_by_day.items(), key=lambda kv: kv[0][1]):
        previous = running_best.get(exercise_id)
        if previous is not None and entry["weight"] <= previous:
            continue
        running_best[exercise_id] = entry["weight"]
        wanted[(exercise_id, day)] = entry

    with transaction.atomic():
        existing = {
            (record.exercise_id, record.achieved_on): record
            for record in PersonalRecord.objects.filter(member=member)
        }

        for key, entry in wanted.items():
            exercise_id, day = key
            record = existing.get(key)
            fields = {
                "weight_kg": entry["weight"],
                "reps": entry["reps"],
                "bodyweight_kg": _bodyweight_on(measurements, day),
                "log": entry["log"],
            }
            if record is None:
                recent = (timezone.localdate() - day).days <= CELEBRATE_WITHIN_DAYS
                PersonalRecord.objects.create(
                    member=member,
                    exercise_id=exercise_id,
                    achieved_on=day,
                    # Backfilled history arrives already seen; only a lift from
                    # the last fortnight is news worth interrupting someone for.
                    seen_at=None if recent else timezone.now(),
                    **fields,
                )
            else:
                # A later weigh-in backdated to before the lift, or an edited
                # set, should correct the record rather than leave it stale.
                changed = [
                    name
                    for name, value in fields.items()
                    if getattr(record, name if name != "log" else "log_id")
                    != (value.id if name == "log" else value)
                ]
                if changed:
                    for name, value in fields.items():
                        setattr(record, name, value)
                    record.save()

        # Anything no longer a record -- because the set behind it was deleted
        # or edited down -- goes, so the table never claims a PR that isn't one.
        stale = [key for key in existing if key not in wanted]
        if stale:
            PersonalRecord.objects.filter(
                member=member,
                id__in=[existing[key].id for key in stale],
            ).delete()

    return PersonalRecord.objects.filter(member=member).select_related("exercise")
