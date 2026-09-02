from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from accounts.models import MembershipStatus

from .models import Payment, PaymentGateway, PaymentStatus


def get_latest_completed_payment(user):
    return (
        Payment.objects.filter(member=user, status=PaymentStatus.COMPLETED)
        .select_related("plan")
        .order_by("-period_end")
        .first()
    )


def compute_membership_status(user):
    """The derived status for `user`, or None if they have no completed
    payment yet (caller decides whether to touch the profile)."""
    payment = get_latest_completed_payment(user)
    if payment is None:
        return None
    today = timezone.localdate()
    return MembershipStatus.ACTIVE if payment.period_end >= today else MembershipStatus.EXPIRED


def sync_membership_status(user, *, respect_pause=False):
    """Recomputes and writes MemberProfile.membership_status from payment
    history. Members with no completed payment yet are left untouched --
    otherwise every pre-existing member would flip to "expired" the moment
    this app ships. `respect_pause=True` (used by the nightly sweep) skips a
    member an admin has manually paused; recording a *new* payment always
    calls with `respect_pause=False` since a fresh payment should reactivate
    even a paused member."""
    status = compute_membership_status(user)
    if status is None:
        return
    profile = user.profile
    if respect_pause and profile.membership_status == MembershipStatus.PAUSED:
        return
    if profile.membership_status != status:
        profile.membership_status = status
        profile.save(update_fields=["membership_status"])


def record_payment(
    *,
    member,
    plan,
    amount,
    method,
    paid_date=None,
    notes="",
    recorded_by=None,
    status=PaymentStatus.COMPLETED,
    external_reference="",
    gateway=None,
):
    """Creates a Payment, computing its period from the member's existing
    subscription. If they still have time left on a completed period, the
    new one stacks on top of it (period_start = old period_end) so an early
    renewal never loses paid-for days; otherwise it starts on paid_date."""
    paid_date = paid_date or timezone.localdate()
    gateway = gateway or PaymentGateway.MANUAL

    with transaction.atomic():
        existing = get_latest_completed_payment(member) if status == PaymentStatus.COMPLETED else None
        if existing and existing.period_end >= paid_date:
            period_start = existing.period_end
        else:
            period_start = paid_date
        period_end = period_start + timedelta(days=plan.duration_days)

        payment = Payment.objects.create(
            member=member,
            plan=plan,
            amount=amount,
            method=method,
            status=status,
            paid_date=paid_date,
            period_start=period_start,
            period_end=period_end,
            notes=notes,
            recorded_by=recorded_by,
            external_reference=external_reference,
            gateway=gateway,
        )
        if status == PaymentStatus.COMPLETED:
            sync_membership_status(member, respect_pause=False)
    return payment
