from django.conf import settings
from django.db import models

from tenancy.managers import TenantManager, UnscopedManager


class Direction(models.TextChoices):
    INBOUND = "in", "From the member"
    OUTBOUND = "out", "To the member"


class DeliveryStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"
    RECEIVED = "received", "Received"


def normalise_phone(value):
    """Digits only, so the same number written six ways still matches.

    WhatsApp hands us "919820011122"; the front desk types "+91 98200 11122".
    Comparing anything but the digits means a member's own number fails to find
    their account, which is the difference between a useful reply and a useless
    one.
    """
    return "".join(c for c in (value or "") if c.isdigit())


class Message(models.Model):
    """One WhatsApp message, in or out.

    Kept in full rather than summarised: when a member says "but I asked you on
    Tuesday", the desk needs to be able to read Tuesday.
    """
    # The branch this belongs to. Operational data is isolated per building:
    # "who came in yesterday" is a question about a gym, not about a brand.
    # Nullable for now; the backfill fills it and a later migration requires it.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    # Resolved from the phone number where possible; a message from a number we
    # don't recognise is still logged, since that is often an enquiry.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="messages",
    )
    phone = models.CharField(max_length=20, help_text="Digits only.")
    direction = models.CharField(max_length=3, choices=Direction.choices)
    body = models.TextField()
    status = models.CharField(
        max_length=10, choices=DeliveryStatus.choices, default=DeliveryStatus.QUEUED
    )
    # The provider's own id, so a delivery receipt can be matched back, and so a
    # redelivered webhook is recognised rather than logged twice.
    external_id = models.CharField(max_length=128, blank=True, db_index=True)
    error = models.CharField(max_length=300, blank=True)
    # Set on replies the assistant wrote itself, so "what did the bot say" is
    # answerable without guessing from the wording.
    is_automated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["phone", "-created_at"])]

    def save(self, *args, **kwargs):
        self.phone = normalise_phone(self.phone)
        super().save(*args, **kwargs)

    def __str__(self):
        arrow = "<-" if self.direction == Direction.INBOUND else "->"
        return f"{arrow} {self.phone}: {self.body[:40]}"
