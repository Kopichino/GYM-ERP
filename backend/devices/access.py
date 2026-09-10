"""Deciding whether a turnstile should let someone through.

The decision is read from the same derived membership status the rest of the
app uses -- it is not a second copy of "who is allowed in" that could disagree
with the billing ledger. A member who pays at the desk is through the turnstile
on their next swipe with nothing to sync.

A denial is logged as a `DeviceEvent` with the `denied` outcome rather than in a
table of its own. A refused entry *is* a punch, and putting it in the same feed
means the front desk sees "Rahul was turned away at 07:12, membership expired"
in the log they already read, instead of somewhere they have to remember to
look.
"""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import MembershipStatus, Role, User


def staff_at(user, tenant):
    """Whether `user` holds an admin or trainer role at `tenant`, right now.

    Read from Membership rather than from `User.role`: on a platform running
    many gyms, being an admin somewhere says nothing about being staff here.
    """
    from tenancy.models import Membership

    rows = Membership.objects.filter(
        user=user, tenant=tenant, is_active=True, role__in=[Role.ADMIN, Role.TRAINER]
    )
    return any(row.is_current() for row in rows)
from attendance.models import CheckInMethod
from attendance.services import AttendanceError, toggle_visit
from billing.services import get_latest_completed_payment

from .models import DeviceEvent, DeviceKind, EventOutcome

GATING_KINDS = {DeviceKind.TURNSTILE, DeviceKind.DOOR}


class Decision:
    """Why someone was let in or turned away. The reason codes are stable so a
    turnstile can show its own wording on its own screen."""

    ALLOWED = "allowed"
    UNKNOWN = "unknown"
    DISABLED = "disabled"
    EXPIRED = "expired"
    PAUSED = "paused"
    NO_PLAN = "no_plan"


MESSAGES = {
    Decision.UNKNOWN: "Card not recognised. Please see the front desk.",
    Decision.DISABLED: "This account is closed. Please see the front desk.",
    Decision.EXPIRED: "Membership has expired. Please see the front desk.",
    Decision.PAUSED: "Membership is on hold. Please see the front desk.",
    Decision.NO_PLAN: "No membership on file. Please see the front desk.",
}


def _member_for(identifier):
    return User.objects.filter(profile__biometric_id=identifier).select_related("profile").first()


def judge(member, tenant=None, grace_days=0, on=None):
    """(reason, allowed) for one member, without touching anything.

    Staff are always let in: a trainer whose own membership lapsed still has to
    be able to get to the floor and take their sessions.
    """
    on = on or timezone.localdate()

    if member is None:
        return Decision.UNKNOWN, False
    if not member.is_active:
        return Decision.DISABLED, False
    # Staff walk in without a membership check -- but only staff of *this*
    # gym. Previously read off `User.role`, which on a multi-tenant platform
    # would have opened every turnstile to anyone who is an admin anywhere.
    if tenant is not None and staff_at(member, tenant):
        return Decision.ALLOWED, True

    profile = getattr(member, "profile", None)
    if profile is not None and profile.membership_status == MembershipStatus.PAUSED:
        return Decision.PAUSED, False

    payment = get_latest_completed_payment(member)
    if payment is None:
        return Decision.NO_PLAN, False
    if payment.period_end + timedelta(days=grace_days) < on:
        return Decision.EXPIRED, False

    return Decision.ALLOWED, True


def request_access(device, identifier, at=None, raw_payload=None):
    """A turnstile asking whether to open, and recording what happened.

    Returns `(allow, reason, event)`. On an allow the member's visit is toggled
    through the usual attendance service, so the one-open-visit-per-member rule
    is enforced in exactly one place -- a turnstile cannot create a second open
    visit any more than the dashboard button can.
    """
    identifier = str(identifier).strip()
    at = at or timezone.now()
    member = _member_for(identifier)

    # A device that only records attendance never refuses anyone; it is not
    # standing in the doorway. This is what keeps every terminal registered
    # before access control existed behaving exactly as before.
    gating = device.kind in GATING_KINDS

    reason, allowed = judge(member, tenant=device.tenant, grace_days=device.grace_days)
    if not gating:
        allowed = member is not None

    try:
        with transaction.atomic():
            event = DeviceEvent.objects.create(
                device=device,
                biometric_id=identifier,
                event_time=at,
                raw_payload=raw_payload or {},
                member=member,
            )
    except IntegrityError:
        # The same swipe again -- most likely the turnstile retrying. Report
        # the original decision rather than logging a second one.
        event = DeviceEvent.objects.filter(
            device=device, biometric_id=identifier, event_time=at
        ).first()
        return (event.outcome != EventOutcome.DENIED if event else False), reason, event

    if member is None:
        event.outcome = EventOutcome.UNMATCHED
        event.detail = f"No member enrolled with id {identifier}."
        event.save(update_fields=["outcome", "detail"])
        return False, Decision.UNKNOWN, event

    if not allowed:
        event.outcome = EventOutcome.DENIED
        event.detail = MESSAGES.get(reason, "Refused entry.")
        event.save(update_fields=["outcome", "detail"])
        return False, reason, event

    try:
        record, action = toggle_visit(member, method=CheckInMethod.BIOMETRIC)
    except AttendanceError as exc:
        # The gate still opens: the member is entitled to be here, and a
        # bookkeeping problem is not a reason to leave them outside.
        event.outcome = EventOutcome.FAILED
        event.detail = str(exc)
        event.save(update_fields=["outcome", "detail"])
        return True, Decision.ALLOWED, event

    event.check_in = record
    event.outcome = (
        EventOutcome.CHECKED_IN if action == "in" else EventOutcome.CHECKED_OUT
    )
    event.save(update_fields=["check_in", "outcome"])
    return True, Decision.ALLOWED, event
