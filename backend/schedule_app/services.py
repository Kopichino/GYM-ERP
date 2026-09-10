"""Booking rules for class sessions.

Capacity is the same class of problem as the one-open-check-in rule: counting
seats and then inserting is a race, and two members hitting Book at once will
both see the last seat free. Every seat-changing operation here therefore takes
a row lock on the ClassSession first, so capacity is decided one caller at a
time rather than by whoever reads fastest.
"""

from django.db import transaction
from django.utils import timezone

from .models import BookingStatus, ClassBooking, ClassSession


class BookingError(Exception):
    """A booking that cannot be made for a reason the member should be told."""


def _is_past(session):
    starts_at = timezone.datetime.combine(session.date, session.start_time)
    if timezone.is_naive(starts_at):
        starts_at = timezone.make_aware(starts_at)
    return starts_at < timezone.now()


def booked_count(session):
    return session.bookings.filter(status=BookingStatus.BOOKED).count()


def spots_left(session):
    """None when the class is uncapped."""
    if session.capacity is None:
        return None
    return max(session.capacity - booked_count(session), 0)


@transaction.atomic
def book(session_id, member):
    """Take a seat, or join the waitlist when the class is full."""
    session = ClassSession.objects.select_for_update().get(pk=session_id)

    if _is_past(session):
        raise BookingError("That class has already started.")

    existing = ClassBooking.objects.filter(member=member, session=session).first()
    if existing and existing.status in (BookingStatus.BOOKED, BookingStatus.WAITLISTED):
        raise BookingError(
            "You're already on the waitlist for this class."
            if existing.status == BookingStatus.WAITLISTED
            else "You've already booked this class."
        )

    taken = session.bookings.filter(status=BookingStatus.BOOKED).count()
    full = session.capacity is not None and taken >= session.capacity

    if full:
        last = (
            session.bookings.filter(status=BookingStatus.WAITLISTED)
            .order_by("-position")
            .first()
        )
        status = BookingStatus.WAITLISTED
        position = (last.position or 0) + 1 if last else 1
    else:
        status, position = BookingStatus.BOOKED, None

    if existing:
        existing.status = status
        existing.position = position
        existing.save(update_fields=["status", "position", "updated_at"])
        return existing

    return ClassBooking.objects.create(
        member=member, session=session, status=status, position=position
    )


@transaction.atomic
def cancel(session_id, member):
    """Give up a seat and, if that frees one, promote the first waitlister."""
    session = ClassSession.objects.select_for_update().get(pk=session_id)
    booking = ClassBooking.objects.filter(member=member, session=session).first()

    if not booking or booking.status in (BookingStatus.CANCELLED, BookingStatus.ATTENDED):
        raise BookingError("You don't have a place on this class.")

    freed_a_seat = booking.status == BookingStatus.BOOKED
    booking.status = BookingStatus.CANCELLED
    booking.position = None
    booking.save(update_fields=["status", "position", "updated_at"])

    promoted = _promote_next(session) if freed_a_seat else None
    return booking, promoted


def _promote_next(session):
    """Move the head of the waitlist into the seat that just opened."""
    if session.capacity is None:
        return None
    if session.bookings.filter(status=BookingStatus.BOOKED).count() >= session.capacity:
        return None

    nxt = (
        session.bookings.filter(status=BookingStatus.WAITLISTED)
        .order_by("position", "booked_at")
        .first()
    )
    if not nxt:
        return None

    nxt.status = BookingStatus.BOOKED
    nxt.position = None
    nxt.save(update_fields=["status", "position", "updated_at"])
    return nxt


def mark_attended(session_id, member_ids):
    """Trainer marking off who actually turned up."""
    return ClassBooking.objects.filter(
        session_id=session_id, member_id__in=member_ids, status=BookingStatus.BOOKED
    ).update(status=BookingStatus.ATTENDED)
