"""Sending member email, and deciding who is due one.

Who to write to is derived from the payment ledger every time the sweep runs --
there is no "reminder due" flag on a member that could drift out of step with
what they have actually paid for. The only thing stored is what was already
sent, so a re-run is silent rather than a second email.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.utils import timezone

from accounts.models import MembershipStatus, Role, User
from billing.services import get_latest_completed_payment

from .models import NotificationKind, NotificationLog
from tenancy.people import members_here

# How many days before expiry a member hears from us. Several nudges rather
# than one, because the first is easy to miss and the last is the one that
# actually gets people to the desk.
EXPIRY_WINDOWS = (7, 3, 1)


logger = logging.getLogger(__name__)

def gym_name():
    # Shared with invoices and the WhatsApp assistant, so a gym that renames
    # itself is renamed everywhere at once.
    from branding.identity import gym_name as configured_name

    return configured_name()


def send(user, kind, subject_date, subject, template, context=None):
    """Sends one email, once.

    Returns the NotificationLog on a real send, or None when this exact message
    has already gone out. The log row is written before the mail goes, inside a
    transaction: if the send raises, the row rolls back and the next sweep will
    try again rather than recording a message nobody received.
    """
    to_email = (user.email or "").strip()
    if not to_email:
        return None

    body = render_to_string(
        f"notifications/{template}.txt",
        {
            "user": user,
            "gym_name": gym_name(),
            **(context or {}),
        },
    )

    try:
        with transaction.atomic():
            log = NotificationLog.objects.create(
                user=user,
                kind=kind,
                subject_date=subject_date,
                to_email=to_email,
                subject=subject,
            )
            # From the gym the member actually joined, when that gym has
            # proved it may send as its own domain -- otherwise from the
            # platform. `sender_for` makes that choice; nothing here should
            # build a From header itself.
            from tenancy import context
            from tenancy.email_identity import sender_for

            send_mail(
                subject=subject,
                message=body,
                from_email=sender_for(context.get()),
                recipient_list=[to_email],
                fail_silently=False,
            )
            return log
    except IntegrityError:
        # Already sent for this subject date -- the unique constraint is the
        # thing that decides, so a doubled cron run costs nothing.
        return None


def expiring_members(on=None):
    """(member, payment, days_left) for everyone inside a reminder window.

    Read from the ledger, so a member who renewed this morning drops out of the
    list without anything having to clear a flag.
    """
    on = on or timezone.localdate()
    targets = {on + timedelta(days=n): n for n in EXPIRY_WINDOWS}
    for member in members_here().select_related("profile"):
        payment = get_latest_completed_payment(member)
        if payment is None or payment.period_end not in targets:
            continue
        # A member an admin has paused isn't about to lose anything.
        if member.profile.membership_status == MembershipStatus.PAUSED:
            continue
        yield member, payment, targets[payment.period_end]


def just_expired_members(on=None):
    """Members whose paid period ran out yesterday and who haven't renewed."""
    on = on or timezone.localdate()
    yesterday = on - timedelta(days=1)
    for member in members_here().select_related("profile"):
        payment = get_latest_completed_payment(member)
        if payment is None or payment.period_end != yesterday:
            continue
        if member.profile.membership_status == MembershipStatus.PAUSED:
            continue
        yield member, payment


def send_expiry_reminders(on=None, tenant=None):
    """The nightly sweep, for one gym. Returns (sent, skipped).

    Takes a tenant because it runs from cron rather than from a request, so
    nothing has resolved one for it. Passing it explicitly is what keeps each
    gym's reminders drawn from that gym's ledger -- and it is where a
    per-tenant sending identity will attach once outgoing mail is per-gym.

    `sweep_all_tenants` below is the entry point cron actually calls.
    """
    from tenancy import context

    if tenant is not None:
        with context.scope(tenant):
            return send_expiry_reminders(on=on)

    on = on or timezone.localdate()
    sent = skipped = 0

    for member, payment, days_left in expiring_members(on):
        subject = (
            f"Your {gym_name()} membership ends tomorrow"
            if days_left == 1
            else f"Your {gym_name()} membership ends in {days_left} days"
        )
        # Keyed on today, not on the expiry: 7 / 3 / 1 days out are three
        # separate nudges, and only a second sweep the same morning is a repeat.
        result = send(
            member,
            NotificationKind.EXPIRY_SOON,
            on,
            subject,
            "expiry_soon",
            {"payment": payment, "days_left": days_left, "plan": payment.plan},
        )
        sent += result is not None
        skipped += result is None

    for member, payment in just_expired_members(on):
        # Keyed on the expiry itself: this one goes out once, ever.
        result = send(
            member,
            NotificationKind.EXPIRED,
            payment.period_end,
            f"Your {gym_name()} membership has expired",
            "expired",
            {"payment": payment, "plan": payment.plan},
        )
        sent += result is not None
        skipped += result is None

    return sent, skipped


def sweep_all_tenants(on=None):
    """Run the nightly sweep once per gym. Returns (sent, skipped) totalled.

    Each gym is swept inside its own scope, so a query that forgets to filter
    still cannot reach across -- the same guarantee a request gets. A gym that
    raises does not stop the others: one misconfigured branch should not mean
    nobody on the platform gets their renewal notice.
    """
    from tenancy.models import Tenant

    sent = skipped = 0
    for tenant in Tenant.objects.filter(is_active=True).iterator():
        try:
            gym_sent, gym_skipped = send_expiry_reminders(on=on, tenant=tenant)
        except Exception:  # noqa: BLE001 -- one gym must not stop the sweep
            logger.exception("expiry sweep failed for tenant %s", tenant.slug)
            continue
        sent += gym_sent
        skipped += gym_skipped
    return sent, skipped
