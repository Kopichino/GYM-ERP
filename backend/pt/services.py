"""Working out when a trainer is actually free, and booking them.

Open slots are never stored. They are the trainer's weekly windows for that
weekday, minus the days they have blocked out, minus what is already booked --
computed every time they are asked for. A stored slot table would need
regenerating whenever any of those three changed, and the first thing anyone
would notice is a member booking a slot the trainer had already given away.
"""

from datetime import date as date_cls, datetime, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from .models import Availability, PTSession, SessionStatus, Unavailable

# How long one slot is. A gym that sells half-hours changes this; the whole
# derivation follows from it.
SLOT_MINUTES = 60


class BookingError(Exception):
    """A booking that cannot go ahead, with a reason to show the member."""


def _times_between(start, end, minutes):
    """Slot start times inside a window, dropping any tail too short to sell."""
    cursor = datetime.combine(date_cls.min, start)
    finish = datetime.combine(date_cls.min, end)
    step = timedelta(minutes=minutes)
    while cursor + step <= finish:
        yield cursor.time(), (cursor + step).time()
        cursor += step


def open_slots(trainer, on, slot_minutes=SLOT_MINUTES, now=None):
    """Bookable slots for one trainer on one day.

    Past slots are left out even when nothing is booked: a member should not be
    offered eight o'clock this morning.
    """
    now = now or timezone.localtime()
    if Unavailable.objects.filter(trainer=trainer, date=on).exists():
        return []

    windows = Availability.objects.filter(
        trainer=trainer, weekday=on.weekday(), is_active=True
    )
    taken = set(
        PTSession.objects.filter(
            trainer=trainer, date=on, status=SessionStatus.BOOKED
        ).values_list("start_time", flat=True)
    )

    slots = []
    for window in windows:
        for start, end in _times_between(window.start_time, window.end_time, slot_minutes):
            if start in taken:
                continue
            if on < now.date() or (on == now.date() and start <= now.time()):
                continue
            slots.append({"start_time": start, "end_time": end})

    slots.sort(key=lambda slot: slot["start_time"])
    return slots


def _within_availability(trainer, on, start, end):
    return Availability.objects.filter(
        trainer=trainer,
        weekday=on.weekday(),
        is_active=True,
        start_time__lte=start,
        end_time__gte=end,
    ).exists()


def _clashes(trainer, member, on, start, end, exclude_id=None):
    """Anything already booked that overlaps, for either person.

    The member side matters as much as the trainer side: someone booking two
    trainers for the same hour is a mistake worth catching at the point of
    booking rather than at the door.
    """
    query = PTSession.objects.filter(
        date=on, status=SessionStatus.BOOKED, start_time__lt=end, end_time__gt=start
    ).filter(Q(trainer=trainer) | Q(member=member))
    if exclude_id:
        query = query.exclude(pk=exclude_id)
    return query


def book_session(*, trainer, member, on, start_time, end_time, price=0, booked_by=None,
                 notes=""):
    """Book one slot, refusing anything the trainer has not actually offered.

    The lock is the point: two members tapping the same slot at the same moment
    would otherwise both look, both see it free, and both book it. This mirrors
    how class capacity is held.
    """
    if end_time <= start_time:
        raise BookingError("A session has to end after it starts.")
    if on < timezone.localdate():
        raise BookingError("That day has already been and gone.")
    if trainer == member:
        raise BookingError("A trainer cannot book a session with themselves.")

    with transaction.atomic():
        # Lock the two people, not the sessions.
        #
        # Locking the trainer's existing sessions was the obvious thing and it
        # does not work: `SELECT ... FOR UPDATE` can only hold rows that are
        # already there, so on a trainer's first booking of a day it matches
        # nothing, holds nothing, and two callers both read the slot as free.
        # The exact-clash case survived that because the unique index caught
        # it; a partial overlap -- 09:00-10:00 against 09:30-10:30, different
        # start times -- has no index to catch it and both rows were written.
        # The same hole let one member be booked with two different trainers at
        # the same hour, since those two calls locked different session sets.
        #
        # The trainer and member rows always exist, so they give every booking
        # that could possibly conflict something in common to queue on: two
        # bookings clash only if they share a trainer or share a member.
        # Ordered by pk so two calls sharing a person can never take the locks
        # in opposite orders and deadlock.
        User = get_user_model()
        list(
            User.objects.select_for_update()
            .filter(pk__in={trainer.pk, member.pk})
            .order_by("pk")
        )

        if Unavailable.objects.filter(trainer=trainer, date=on).exists():
            raise BookingError("That trainer is not available on that day.")
        if not _within_availability(trainer, on, start_time, end_time):
            raise BookingError("That time is outside the trainer's hours.")

        clash = _clashes(trainer, member, on, start_time, end_time).first()
        if clash:
            raise BookingError(
                "That slot has just been taken."
                if clash.trainer_id == trainer.id
                else "You already have a session booked at that time."
            )

        try:
            return PTSession.objects.create(
                trainer=trainer,
                member=member,
                date=on,
                start_time=start_time,
                end_time=end_time,
                price=price,
                booked_by=booked_by or member,
                notes=notes,
            )
        except IntegrityError:
            # The partial unique index caught a race the lock could not see.
            raise BookingError("That slot has just been taken.")


def cancel_session(session):
    """Cancelling frees the slot, because the index only counts live bookings."""
    if session.status != SessionStatus.BOOKED:
        raise BookingError("That session is not open to cancel.")
    session.status = SessionStatus.CANCELLED
    session.save(update_fields=["status"])
    return session


def utilisation(trainer, start, end, slot_minutes=SLOT_MINUTES):
    """(booked hours, offered hours) across a date range.

    Both sides are derived: offered comes from the weekly pattern less blocked
    days, booked from the sessions themselves. Nothing counts a slot that was
    never on sale.
    """
    windows = list(Availability.objects.filter(trainer=trainer, is_active=True))
    blocked = set(
        Unavailable.objects.filter(
            trainer=trainer, date__gte=start, date__lte=end
        ).values_list("date", flat=True)
    )

    offered_minutes = 0
    day = start
    while day <= end:
        if day not in blocked:
            for window in windows:
                if window.weekday != day.weekday():
                    continue
                offered_minutes += sum(
                    slot_minutes
                    for _ in _times_between(window.start_time, window.end_time, slot_minutes)
                )
        day += timedelta(days=1)

    booked_minutes = 0
    for session in PTSession.objects.filter(
        trainer=trainer,
        date__gte=start,
        date__lte=end,
        status__in=[SessionStatus.BOOKED, SessionStatus.COMPLETED, SessionStatus.NO_SHOW],
    ):
        begin = session.start_time.hour * 60 + session.start_time.minute
        finish = session.end_time.hour * 60 + session.end_time.minute
        booked_minutes += finish - begin

    return round(booked_minutes / 60, 2), round(offered_minutes / 60, 2)
