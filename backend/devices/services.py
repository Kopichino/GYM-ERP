"""Turning raw terminal punches into attendance.

The punch is written down first and interpreted second. That ordering is what
lets a mis-enrolled biometric id be fixed and reprocessed later instead of the
gym losing a day of attendance to a mapping bug.
"""

from datetime import timedelta

from django.db import IntegrityError, transaction

from accounts.models import User
from attendance.models import CheckInMethod
from attendance.services import AttendanceError, toggle_visit

from .models import DeviceEvent, EventOutcome

# A terminal that re-sends its buffer can repeat a punch with a slightly
# different timestamp, so the unique constraint alone won't catch every repeat.
DEDUPE_WINDOW_SECONDS = 60


def record_punch(device, biometric_id, event_time, raw_payload=None):
    """Store one punch and resolve it. Always returns an event, even when the
    punch could not be matched -- an unmatched punch is a fact worth keeping."""
    biometric_id = str(biometric_id).strip()

    try:
        with transaction.atomic():
            event = DeviceEvent.objects.create(
                device=device,
                biometric_id=biometric_id,
                event_time=event_time,
                raw_payload=raw_payload or {},
            )
    except IntegrityError:
        # Exactly this punch is already on file; report the original.
        existing = DeviceEvent.objects.filter(
            device=device, biometric_id=biometric_id, event_time=event_time
        ).first()
        return existing, False

    _resolve(event)
    return event, True


def _resolve(event):
    member = User.objects.filter(profile__biometric_id=event.biometric_id).first()
    if member is None:
        event.outcome = EventOutcome.UNMATCHED
        event.detail = f"No member enrolled with biometric id {event.biometric_id}."
        event.save(update_fields=["outcome", "detail"])
        return event

    event.member = member

    if _is_repeat(event, member):
        event.outcome = EventOutcome.DUPLICATE
        event.detail = "Repeat punch within the dedupe window; ignored."
        event.save(update_fields=["member", "outcome", "detail"])
        return event

    try:
        record, action = toggle_visit(member, method=CheckInMethod.BIOMETRIC)
    except AttendanceError as exc:
        event.outcome = EventOutcome.FAILED
        event.detail = str(exc)
        event.save(update_fields=["member", "outcome", "detail"])
        return event

    event.check_in = record
    event.outcome = (
        EventOutcome.CHECKED_IN if action == "in" else EventOutcome.CHECKED_OUT
    )
    event.detail = ""
    event.save(update_fields=["member", "check_in", "outcome", "detail"])
    return event


def _is_repeat(event, member):
    """A second punch seconds after the first is someone swiping twice, not a
    member leaving immediately."""
    window_start = event.event_time - timedelta(seconds=DEDUPE_WINDOW_SECONDS)
    return (
        DeviceEvent.objects.filter(
            member=member,
            event_time__gte=window_start,
            event_time__lt=event.event_time,
            outcome__in=[EventOutcome.CHECKED_IN, EventOutcome.CHECKED_OUT],
        )
        .exclude(pk=event.pk)
        .exists()
    )


def reprocess(event):
    """Re-run resolution after an enrolment id has been corrected."""
    event.outcome = EventOutcome.PENDING
    event.detail = ""
    event.member = None
    event.check_in = None
    event.save(update_fields=["outcome", "detail", "member", "check_in"])
    return _resolve(event)
