"""Rota rules that a column can't express.

The one rule worth enforcing is that a person cannot be in two places at once.
A unique index catches an exact duplicate but not a genuine overlap (06:00-14:00
against 12:00-20:00), so that check lives here -- and it runs inside the same
transaction as the insert, because a rota is edited by two people at a desk at
the same time far more often than anything else in this system.
"""

from django.db import transaction
from django.utils import timezone

from .models import Shift


class ShiftError(Exception):
    """A rota clash, with wording for whoever is building the rota."""


def clashing(staff, date, start_time, end_time, exclude_id=None):
    """Any shift for this person that overlaps the given window.

    Two windows overlap when each starts before the other ends. Touching ends
    (one finishing at 14:00, the next starting at 14:00) are a handover, not a
    clash.
    """
    query = Shift.objects.filter(
        staff=staff, date=date, start_time__lt=end_time, end_time__gt=start_time
    )
    if exclude_id:
        query = query.exclude(pk=exclude_id)
    return query


def save_shift(*, staff, date, start_time, end_time, position, notes="", created_by=None,
               instance=None):
    """Create or update a shift, refusing a clash.

    `select_for_update` on the day's rows: without it, two people adding a
    shift for the same person at the same moment would each look, see no
    clash, and both write.
    """
    if end_time <= start_time:
        raise ShiftError("A shift has to end after it starts.")

    with transaction.atomic():
        Shift.objects.select_for_update().filter(staff=staff, date=date).exists()
        clash = clashing(
            staff, date, start_time, end_time, exclude_id=instance.pk if instance else None
        ).first()
        if clash:
            raise ShiftError(
                f"{staff.username} is already on {clash.start_time:%H:%M}-"
                f"{clash.end_time:%H:%M} that day."
            )

        if instance is None:
            return Shift.objects.create(
                staff=staff,
                date=date,
                start_time=start_time,
                end_time=end_time,
                position=position,
                notes=notes,
                created_by=created_by,
            )

        instance.staff = staff
        instance.date = date
        instance.start_time = start_time
        instance.end_time = end_time
        instance.position = position
        instance.notes = notes
        instance.save()
        return instance


def on_floor(at=None):
    """Who is rostered right now.

    Derived from the rota rather than a "currently working" flag somebody would
    have to remember to clear -- the same reason a check-in is a row with two
    times rather than a boolean.
    """
    at = at or timezone.localtime()
    return (
        Shift.objects.filter(
            date=at.date(), start_time__lte=at.time(), end_time__gt=at.time()
        )
        .select_related("staff")
        .order_by("start_time")
    )
