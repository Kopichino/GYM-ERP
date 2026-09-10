"""Earning and reversing trainer commission.

Commission follows the money: an entry is raised when a payment completes and
voided if that payment is later refunded or deleted. Without the reversal a
trainer would keep credit for money the gym gave back.
"""

from decimal import ROUND_HALF_UP, Decimal

from billing.models import PaymentStatus

from .models import CommissionBasis, CommissionEntry, CommissionRule, EntryStatus

TWO_DP = Decimal("0.01")


def rule_for(trainer, plan):
    """The most specific active rule that covers this trainer and plan."""
    candidates = [
        rule
        for rule in CommissionRule.objects.filter(is_active=True).select_related("trainer", "plan")
        if rule.trainer_id in (None, trainer.id) and rule.plan_id in (None, plan.id)
    ]
    if not candidates:
        return None
    # Most specific first; newest breaks a tie.
    return sorted(candidates, key=lambda r: (r.specificity, r.id), reverse=True)[0]


def compute(rule, payment):
    if rule.basis == CommissionBasis.PERCENT:
        return (Decimal(payment.amount) * Decimal(rule.rate) / 100).quantize(
            TWO_DP, rounding=ROUND_HALF_UP
        )
    return Decimal(rule.rate).quantize(TWO_DP)


def accrue_for_payment(payment):
    """Raise the commission entry for a completed payment, if one is due.

    Returns the entry, or None when the member has no trainer, no rule matches,
    or the payment isn't in a state that earns anything.
    """
    existing = CommissionEntry.objects.filter(payment=payment).first()

    if payment.status != PaymentStatus.COMPLETED:
        # Refunded or failed: reverse rather than leave the credit standing.
        if existing and existing.status != EntryStatus.PAID:
            existing.status = EntryStatus.VOID
            existing.save(update_fields=["status"])
        return None

    if existing:
        return existing

    trainer = getattr(payment.member.profile, "trainer", None)
    if trainer is None:
        return None

    rule = rule_for(trainer, payment.plan)
    if rule is None:
        return None

    return CommissionEntry.objects.create(
        trainer=trainer,
        payment=payment,
        rule=rule,
        basis=rule.basis,
        rate_applied=rule.rate,
        amount=compute(rule, payment),
        earned_on=payment.paid_date,
    )


def void_for_payment(payment):
    """Called when a payment is voided. An entry already paid out stays put --
    clawing back settled money is a decision for a person, not a signal."""
    entry = CommissionEntry.objects.filter(payment=payment).first()
    if entry and entry.status == EntryStatus.PENDING:
        entry.status = EntryStatus.VOID
        entry.save(update_fields=["status"])
    return entry


def settle(trainer, period_start, period_end, notes=""):
    """Marks every pending entry in the window as paid, under one payout."""
    from .models import Payout

    entries = CommissionEntry.objects.filter(
        trainer=trainer,
        status=EntryStatus.PENDING,
        earned_on__gte=period_start,
        earned_on__lte=period_end,
    )
    total = sum((e.amount for e in entries), Decimal("0.00"))

    payout = Payout.objects.create(
        trainer=trainer,
        period_start=period_start,
        period_end=period_end,
        total=total,
        notes=notes,
    )
    entries.update(status=EntryStatus.PAID, payout=payout)
    return payout
