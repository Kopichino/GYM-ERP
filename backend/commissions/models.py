from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from tenancy.managers import TenantManager, UnscopedManager
from django.utils import timezone

from accounts.models import Role


class CommissionBasis(models.TextChoices):
    PERCENT = "percent", "Percentage of the payment"
    FLAT = "flat", "Flat amount per payment"


class CommissionRule(models.Model):
    """How a trainer earns from a member's payment.

    Resolution is most-specific-first: a rule naming both the trainer and the
    plan beats one naming only the trainer, which beats the gym-wide default.
    """
    # Shared across the brand's branches: a chain maintains one price list, one
    # badge ladder, one identity -- not one copy per building. Nullable for now;
    # the backfill fills it and a later migration makes it required.
    organisation = models.ForeignKey(
        "tenancy.Organisation",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    trainer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="commission_rules",
        limit_choices_to={"role": Role.TRAINER},
        help_text="Blank applies the rule to every trainer.",
    )
    plan = models.ForeignKey(
        "billing.Plan",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="commission_rules",
        help_text="Blank applies the rule to every plan.",
    )
    basis = models.CharField(max_length=10, choices=CommissionBasis.choices)
    rate = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(0)]
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    #: Scoped to the brand that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "organisation"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-is_active", "-id"]

    @property
    def specificity(self):
        """Higher wins. Used to pick between overlapping rules."""
        return (1 if self.trainer_id else 0) + (1 if self.plan_id else 0)

    def __str__(self):
        who = self.trainer.username if self.trainer else "all trainers"
        what = self.plan.name if self.plan else "all plans"
        suffix = "%" if self.basis == CommissionBasis.PERCENT else ""
        return f"{who} / {what}: {self.rate}{suffix}"


class EntryStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PAID = "paid", "Paid out"
    VOID = "void", "Void"


class Payout(models.Model):
    """A batch of entries settled together."""
    # The branch this belongs to. Operational data is isolated per building:
    # "who came in yesterday" is a question about a gym, not about a brand.
    # Nullable for now; the backfill fills it and a later migration requires it.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    trainer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payouts"
    )
    period_start = models.DateField()
    period_end = models.DateField()
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    paid_on = models.DateField(default=timezone.localdate)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-paid_on", "-id"]

    def __str__(self):
        return f"{self.trainer} {self.period_start}..{self.period_end}: {self.total}"


class CommissionEntry(models.Model):
    """What one trainer earned from one payment.

    `rate_applied` and `amount` are snapshotted rather than recomputed: editing
    a rule later must not silently restate what a trainer was already told they
    had earned.
    """
    # The branch this belongs to. Operational data is isolated per building:
    # "who came in yesterday" is a question about a gym, not about a brand.
    # Nullable for now; the backfill fills it and a later migration requires it.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    trainer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="commission_entries"
    )
    payment = models.OneToOneField(
        "billing.Payment", on_delete=models.CASCADE, related_name="commission_entry"
    )
    rule = models.ForeignKey(
        CommissionRule, null=True, blank=True, on_delete=models.SET_NULL, related_name="entries"
    )
    basis = models.CharField(max_length=10, choices=CommissionBasis.choices)
    rate_applied = models.DecimalField(max_digits=8, decimal_places=2)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=10, choices=EntryStatus.choices, default=EntryStatus.PENDING
    )
    payout = models.ForeignKey(
        Payout, null=True, blank=True, on_delete=models.SET_NULL, related_name="entries"
    )
    earned_on = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-earned_on", "-id"]
        indexes = [models.Index(fields=["trainer", "status"])]
        verbose_name_plural = "commission entries"

    def __str__(self):
        return f"{self.trainer} earned {self.amount} on {self.earned_on}"
