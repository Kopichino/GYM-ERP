"""The "new PR" moment, and what to say in it.

A record on its own is a number. What makes it worth interrupting someone for
is the comparison -- *what they beat* -- and that is derived here from the
record immediately before it on the same exercise, never stored. Only the fact
that the member has been shown it is written down, because that is the one
thing no other row can answer.
"""

from django.utils import timezone

from .models import PersonalRecord
from .records import sync_records


def _previous(record):
    """The record this one beat, if there was one."""
    return (
        PersonalRecord.objects.filter(
            member_id=record.member_id,
            exercise_id=record.exercise_id,
            achieved_on__lt=record.achieved_on,
        )
        .order_by("-achieved_on")
        .first()
    )


def describe(record):
    """One record, with the story of what it beat."""
    previous = _previous(record)
    gain = None
    if previous is not None:
        gain = record.weight_kg - previous.weight_kg

    return {
        "id": record.id,
        "exercise": record.exercise.name,
        "exercise_id": record.exercise_id,
        "weight_kg": record.weight_kg,
        "reps": record.reps,
        "achieved_on": record.achieved_on,
        "previous_kg": previous.weight_kg if previous else None,
        "gain_kg": gain,
        # A member's first ever record on a lift is a different kind of moment
        # from beating one, and deserves different words.
        "is_first": previous is None,
        "ratio": record.ratio,
    }


def pending(member, resync=True):
    """Records the member has not been shown yet, newest first.

    Syncs first by default, so a set logged a moment ago is already a record by
    the time this is asked -- the alternative is hooking the workout write path,
    which would put badge bookkeeping in front of somebody logging a set.
    """
    if resync:
        sync_records(member)

    records = (
        PersonalRecord.objects.filter(member=member, seen_at__isnull=True)
        .select_related("exercise")
        .order_by("-achieved_on", "-weight_kg")
    )
    return [describe(record) for record in records]


def mark_seen(member, ids=None):
    """Stamp records as shown. Returns how many were still unseen.

    Scoped to the member on purpose: an id from someone else's account simply
    matches nothing rather than being an error, because there is no case where
    one member acknowledging another's PR means anything.
    """
    unseen = PersonalRecord.objects.filter(member=member, seen_at__isnull=True)
    if ids:
        unseen = unseen.filter(id__in=ids)
    return unseen.update(seen_at=timezone.now())
