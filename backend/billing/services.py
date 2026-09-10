from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from accounts.models import MembershipStatus

from .models import Discount, DiscountType, Payment, PaymentGateway, PaymentStatus


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


class DiscountError(Exception):
    """A code that cannot be applied, with a reason to show at the counter."""


TWO_DP = Decimal("0.01")


def compute_period(member, plan, paid_date=None, status=PaymentStatus.COMPLETED, duration_days=None):
    """The period a payment would cover. Shared by the quote and the commit so
    the total shown at the counter is the one that gets written.

    `duration_days` overrides the plan's own length, for the cases where a
    membership gains time that isn't a plan purchase -- a referral reward, say.
    Those still stack on the existing period like any renewal.
    """
    paid_date = paid_date or timezone.localdate()
    existing = get_latest_completed_payment(member) if status == PaymentStatus.COMPLETED else None
    if existing and existing.period_end >= paid_date:
        start = existing.period_end
    else:
        start = paid_date
    days = plan.duration_days if duration_days is None else duration_days
    return start, start + timedelta(days=days)


def find_discount(code):
    if not code:
        return None
    discount = Discount.objects.filter(code__iexact=code.strip()).first()
    if discount is None:
        raise DiscountError(f"No offer with the code '{code.strip().upper()}'.")
    return discount


def price_with_discount(plan, member, code=None, on=None):
    """Prices one plan for one member.

    Returns (discount, amount_off, total). Raises DiscountError with a
    counter-readable reason rather than silently charging full price -- a
    discount that quietly fails to apply is worse than one that is refused.
    """
    on = on or timezone.localdate()
    # Quantised up front so every path returns money to two places -- otherwise
    # an undiscounted total comes back as "14000" and a discounted one as
    # "12600.00", and the till renders them inconsistently.
    gross = Decimal(plan.price).quantize(TWO_DP)

    discount = find_discount(code)
    if discount is None:
        return None, Decimal("0.00"), gross

    if not discount.is_active:
        raise DiscountError(f"{discount.code} is no longer active.")
    if discount.valid_from > on:
        raise DiscountError(f"{discount.code} isn't valid until {discount.valid_from}.")
    if discount.valid_until and discount.valid_until < on:
        raise DiscountError(f"{discount.code} expired on {discount.valid_until}.")

    # An empty plan list means the offer is good on anything.
    allowed = discount.plans.all()
    if allowed.exists() and plan not in allowed:
        raise DiscountError(f"{discount.code} doesn't apply to the {plan.name} plan.")

    if discount.max_uses is not None and discount.times_used >= discount.max_uses:
        raise DiscountError(f"{discount.code} has been fully redeemed.")

    if discount.max_uses_per_member:
        used_by_member = discount.payments.filter(
            member=member, status=PaymentStatus.COMPLETED
        ).count()
        if used_by_member >= discount.max_uses_per_member:
            raise DiscountError(f"{member.username} has already used {discount.code}.")

    if discount.discount_type == DiscountType.PERCENT:
        amount_off = (gross * Decimal(discount.value) / Decimal(100)).quantize(TWO_DP)
    else:
        amount_off = Decimal(discount.value).quantize(TWO_DP)

    # Never let an offer hand money back.
    amount_off = min(amount_off, gross)
    return discount, amount_off, (gross - amount_off).quantize(TWO_DP)


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
    discount=None,
    discount_amount=Decimal("0"),
    duration_days=None,
):
    """Creates a Payment, computing its period from the member's existing
    subscription. If they still have time left on a completed period, the
    new one stacks on top of it (period_start = old period_end) so an early
    renewal never loses paid-for days; otherwise it starts on paid_date.

    This stays the only place a Payment is written. Checkout prices the sale
    and then calls in here, because this is also what re-syncs the member's
    derived status -- inserting a Payment directly would skip that."""
    paid_date = paid_date or timezone.localdate()
    gateway = gateway or PaymentGateway.MANUAL

    with transaction.atomic():
        period_start, period_end = compute_period(
            member, plan, paid_date, status, duration_days=duration_days
        )

        payment = Payment.objects.create(
            member=member,
            plan=plan,
            amount=amount,
            discount=discount,
            discount_amount=discount_amount or Decimal("0"),
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


def open_online_order(member, plan, code=None, on=None):
    """Prices a sale and opens a gateway order for it.

    The price is worked out here, server-side, and written to the order row. The
    callback that follows can only confirm that this order was paid -- it can't
    say what it was worth.
    """
    from .gateway import GatewayError, create_order  # local: gateway needs settings
    from .models import OrderStatus, PaymentGateway, PaymentOrder

    on = on or timezone.localdate()
    discount, amount_off, total = price_with_discount(plan, member, code, on=on)

    if total <= 0:
        raise DiscountError("That comes to nothing to pay -- record it at the desk instead.")

    order = create_order(
        total,
        receipt=f"m{member.id}-p{plan.id}-{int(timezone.now().timestamp())}",
        notes={"member": member.username, "plan": plan.name},
    )

    return PaymentOrder.objects.create(
        member=member,
        plan=plan,
        discount=discount,
        amount=total,
        discount_amount=amount_off,
        gateway=PaymentGateway.RAZORPAY,
        order_id=order["id"],
        status=OrderStatus.CREATED,
    )


def settle_online_order(order, gateway_payment_id="", method=None):
    """Turns a paid gateway order into a real payment, exactly once.

    Both the browser callback and the webhook land here, and either may arrive
    first or twice. The order's one-to-one link to a payment is what makes that
    safe: a second call returns the payment the first one wrote.
    """
    from .models import OrderStatus, PaymentGateway, PaymentMethod

    if order.payment_id:
        return order.payment

    with transaction.atomic():
        # Lock the row so a callback and a webhook arriving together can't both
        # decide the order is unpaid.
        locked = order.__class__.objects.select_for_update().get(pk=order.pk)
        if locked.payment_id:
            return locked.payment

        payment = record_payment(
            member=locked.member,
            plan=locked.plan,
            # Read off our own row, never off the callback.
            amount=locked.amount,
            method=method or PaymentMethod.UPI,
            notes="Paid online.",
            discount=locked.discount,
            discount_amount=locked.discount_amount,
            external_reference=gateway_payment_id,
            gateway=PaymentGateway.RAZORPAY,
        )
        locked.payment = payment
        locked.status = OrderStatus.PAID
        locked.gateway_payment_id = gateway_payment_id
        locked.save(update_fields=["payment", "status", "gateway_payment_id", "updated_at"])

    # Same downstream bookkeeping a counter sale gets. Imported locally so
    # billing doesn't hard-depend on either app at module load.
    from commissions.services import accrue_for_payment
    from invoicing.services import issue_invoice

    issue_invoice(payment)
    accrue_for_payment(payment)
    return payment
