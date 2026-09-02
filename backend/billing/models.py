from django.conf import settings
from django.db import models
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

    name = models.CharField(max_length=100, unique=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    duration_days = models.PositiveIntegerField(
        help_text="Length of one billing period in days, e.g. 30 for monthly, 365 for annual."
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Payment(models.Model):
    """A single payment record. This *is* the subscription ledger -- a
    member's current subscription is derived from their most recent
    completed payment's period_end rather than stored on a separate model,
    so there's nothing to drift out of sync."""

    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payments"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=8, decimal_places=2)
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

    class Meta:
        ordering = ["-paid_date", "-id"]

    def __str__(self):
        return f"{self.member} - {self.plan} ({self.paid_date})"
