from django.conf import settings
from django.db import models

from tenancy.managers import TenantManager, UnscopedManager


class NotificationKind(models.TextChoices):
    EXPIRY_SOON = "expiry_soon", "Membership expiring soon"
    EXPIRED = "expired", "Membership expired"
    PAYMENT_DUE = "payment_due", "Payment reminder"
    WELCOME = "welcome", "Welcome"


class NotificationLog(models.Model):
    """One row per message actually sent.

    This is what stops the nightly sweep from mailing the same member twice:
    the send is keyed on (member, kind, subject_date), and the unique constraint
    -- not an application check -- is what makes a re-run safe. A cron job that
    fires twice, or a sweep re-run by hand after a failure, must never turn into
    two emails.
    """
    # The branch this belongs to. Operational data is isolated per building:
    # "who came in yesterday" is a question about a gym, not about a brand.
    # Nullable for now; the backfill fills it and a later migration requires it.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=20, choices=NotificationKind.choices)
    # What identifies this message, which depends on what kind it is. A
    # one-off announcement ("your membership expired") is keyed on the date of
    # the event, so it is sent once ever. A recurring nudge ("ends in 3 days")
    # is keyed on the day it fires, so the 7-, 3- and 1-day reminders are three
    # separate messages while a doubled sweep on any one morning is still one.
    subject_date = models.DateField()
    to_email = models.EmailField()
    subject = models.CharField(max_length=200, blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-sent_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "kind", "subject_date"], name="one_notification_per_subject"
            )
        ]
        indexes = [models.Index(fields=["kind", "-sent_at"])]

    def __str__(self):
        return f"{self.get_kind_display()} -> {self.to_email} ({self.subject_date})"
