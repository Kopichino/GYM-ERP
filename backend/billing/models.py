from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from tenancy.managers import TenantManager, UnscopedManager
from django.utils import timezone


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    UPI = "upi", "UPI"
    BANK_TRANSFER = "bank_transfer", "Bank transfer"
    CARD = "card", "Card"
    OTHER = "other", "Other"


class PaymentStatus(models.TextChoices):
    COMPLETED = "completed", "Completed"
    PENDING = "pending", "Pending"
    FAILED = "failed", "Failed"
    REFUNDED = "refunded", "Refunded"


class PaymentGateway(models.TextChoices):
    MANUAL = "manual", "Manual"
    RAZORPAY = "razorpay", "Razorpay"
    STRIPE = "stripe", "Stripe"


class Plan(models.Model):
    """A subscription tier, e.g. "Monthly", "Quarterly", "Annual"."""
    # Shared across the brand's branches: a chain maintains one price list, one
    # badge ladder, one identity -- not one copy per building. Nullable for now;
    # the backfill fills it and a later migration makes it required.
    organisation = models.ForeignKey(
        "tenancy.Organisation",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    duration_days = models.PositiveIntegerField(
        help_text="Length of one billing period in days, e.g. 30 for monthly, 365 for annual."
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    #: Scoped to the brand that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "organisation"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["name"]
        constraints = [
            # Per brand, not per platform: two unrelated gyms both selling a
            # plan called "Monthly" is the normal case, not a collision.
            models.UniqueConstraint(
                fields=["organisation", "name"], name="one_plan_name_per_organisation"
            )
        ]

    def __str__(self):
        return self.name


class DiscountType(models.TextChoices):
    PERCENT = "percent", "Percentage off"
    FLAT = "flat", "Flat amount off"


class Discount(models.Model):
    """An offer the front desk can apply at checkout.

    How many times a code has been used is deliberately not a column: it is
    `Payment.objects.filter(discount=self, status=COMPLETED).count()`, so the
    ledger stays the single source of truth. A stored counter would drift the
    moment a payment was voided or refunded -- the same reasoning that keeps
    membership status derived rather than written down.
    """
    # Shared across the brand's branches: a chain maintains one price list, one
    # badge ladder, one identity -- not one copy per building. Nullable for now;
    # the backfill fills it and a later migration makes it required.
    organisation = models.ForeignKey(
        "tenancy.Organisation",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    code = models.CharField(max_length=30)
    description = models.CharField(max_length=200, blank=True)
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices)
    value = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="A percentage (0-100) or a flat amount, depending on the type.",
    )
    # Empty means the offer applies to every plan.
    plans = models.ManyToManyField(Plan, blank=True, related_name="discounts")
    valid_from = models.DateField(default=timezone.localdate)
    valid_until = models.DateField(null=True, blank=True, help_text="Blank = no end date.")
    max_uses = models.PositiveIntegerField(null=True, blank=True, help_text="Blank = unlimited.")
    max_uses_per_member = models.PositiveIntegerField(
        default=1, help_text="0 = unlimited per member."
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    #: Scoped to the brand that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "organisation"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-is_active", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "code"], name="one_discount_code_per_organisation"
            )
        ]

    def save(self, *args, **kwargs):
        # Codes are matched case-insensitively, so store one canonical form.
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    @property
    def times_used(self):
        return self.payments.filter(status=PaymentStatus.COMPLETED).count()

    def __str__(self):
        suffix = "%" if self.discount_type == DiscountType.PERCENT else ""
        return f"{self.code} ({self.value}{suffix} off)"


class Payment(models.Model):
    """A single payment record. This *is* the subscription ledger -- a
    member's current subscription is derived from their most recent
    completed payment's period_end rather than stored on a separate model,
    so there's nothing to drift out of sync."""
    # The branch this belongs to. Operational data is isolated per building:
    # "who came in yesterday" is a question about a gym, not about a brand.
    # Nullable for now; the backfill fills it and a later migration requires it.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payments"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="payments")
    # What the member actually handed over, after any discount. Gross is
    # `amount + discount_amount` -- derived rather than stored so the ledger
    # total is always the money that really moved.
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    discount = models.ForeignKey(
        Discount, null=True, blank=True, on_delete=models.SET_NULL, related_name="payments"
    )
    discount_amount = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    status = models.CharField(
        max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.COMPLETED
    )
    paid_date = models.DateField(default=timezone.localdate)
    # Server-computed in billing.services.record_payment, not client-supplied.
    period_start = models.DateField()
    period_end = models.DateField()
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="payments_recorded",
    )
    # Extension points for a future payment-gateway integration -- unused today.
    external_reference = models.CharField(max_length=100, blank=True)
    gateway = models.CharField(
        max_length=10, choices=PaymentGateway.choices, default=PaymentGateway.MANUAL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-paid_date", "-id"]

    def __str__(self):
        return f"{self.member} - {self.plan} ({self.paid_date})"


class OrderStatus(models.TextChoices):
    CREATED = "created", "Awaiting payment"
    PAID = "paid", "Paid"
    FAILED = "failed", "Failed"


class PaymentOrder(models.Model):
    """An intent to pay online, opened before any money moves.

    This row exists for one reason: when the gateway calls back it names only an
    order id, and the amount that gets recorded has to come from what we priced
    at the time -- not from whatever the browser posts. A member who edits the
    amount in the callback changes nothing, because the callback is only ever
    used to confirm *that* the order was paid.
    """
    # The branch this belongs to. Operational data is isolated per building:
    # "who came in yesterday" is a question about a gym, not about a brand.
    # Nullable for now; the backfill fills it and a later migration requires it.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payment_orders"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="payment_orders")
    discount = models.ForeignKey(
        Discount, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    gateway = models.CharField(
        max_length=12, choices=PaymentGateway.choices, default=PaymentGateway.RAZORPAY
    )
    order_id = models.CharField(max_length=64, unique=True)
    status = models.CharField(
        max_length=10, choices=OrderStatus.choices, default=OrderStatus.CREATED
    )
    # The gateway's own id for the money, kept for reconciliation with their
    # dashboard. Set once the order is settled.
    gateway_payment_id = models.CharField(max_length=64, blank=True)
    # One order settles to at most one payment; the OneToOne is what makes a
    # replayed callback or a doubled webhook impossible to double-charge.
    payment = models.OneToOneField(
        "Payment", null=True, blank=True, on_delete=models.SET_NULL, related_name="order"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["member", "-created_at"])]

    def __str__(self):
        return f"{self.order_id} - {self.member} {self.amount} ({self.status})"


class DayPass(models.Model):
    """A walk-in who is not a member.

    Given its own table rather than a stub `User`: a guest has no login, no
    plan, no derived membership status and no trainer, and inventing an account
    for them would put someone in every member list, every at-risk sweep and
    every reminder email who has no business being there.

    They are still a real visit, though, which is why the check-in itself lives
    in `attendance` alongside everyone else's -- the occupancy figures would be
    wrong from day one otherwise.
    """
    # The branch this belongs to. Operational data is isolated per building:
    # "who came in yesterday" is a question about a gym, not about a brand.
    # Nullable for now; the backfill fills it and a later migration requires it.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    valid_on = models.DateField(
        default=timezone.localdate, help_text="The single day this pass is good for."
    )
    amount = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    method = models.CharField(
        max_length=15, choices=PaymentMethod.choices, default=PaymentMethod.CASH
    )
    notes = models.CharField(max_length=200, blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="day_passes_issued",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-valid_on", "-id"]
        indexes = [models.Index(fields=["valid_on"])]

    @property
    def is_valid_today(self):
        return self.valid_on == timezone.localdate()

    def __str__(self):
        return f"{self.name} - day pass {self.valid_on}"
