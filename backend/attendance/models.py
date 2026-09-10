from django.conf import settings
from django.db import models

from tenancy.managers import TenantManager, UnscopedManager


class CheckInMethod(models.TextChoices):
    TAP = "tap", "Self-service tap"
    QR = "qr", "QR scan"
    BIOMETRIC = "biometric", "Biometric device"
    MANUAL = "manual", "Added by staff"


class CheckInOut(models.Model):
    """One visit, by a member or a day-pass guest.

    Guests share this table on purpose. A separate guest-visit table would mean
    every occupancy, heatmap and busiest-hour figure had to remember to union
    two sources, and the first one that forgot would quietly under-report the
    gym's actual footfall.
    """
    # The branch this belongs to. Operational data is isolated per building:
    # "who came in yesterday" is a question about a gym, not about a brand.
    # Nullable for now; the backfill fills it and a later migration requires it.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    # Null for a guest visit. The existing partial unique index below is
    # unaffected by that: NULLs are distinct in a unique index, so guest rows
    # simply do not participate in the one-open-check-in-per-user rule, and
    # every member row still does.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="check_ins",
    )
    day_pass = models.ForeignKey(
        "billing.DayPass",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="visits",
    )
    check_in_time = models.DateTimeField(auto_now_add=True)
    check_out_time = models.DateTimeField(null=True, blank=True)
    # How the visit was recorded. Every route -- the dashboard button, a QR
    # scan, a fingerprint terminal -- lands on the same row and the same
    # one-open-check-in constraint below.
    method = models.CharField(
        max_length=10, choices=CheckInMethod.choices, default=CheckInMethod.TAP
    )

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-check_in_time"]
        constraints = [
            # At most one open (not-yet-checked-out) record per user.
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(check_out_time__isnull=True),
                name="one_open_checkin_per_user",
            ),
            # The same rule for a guest, as its own index -- a day pass cannot
            # be used to hold two visits open either.
            models.UniqueConstraint(
                fields=["day_pass"],
                condition=models.Q(check_out_time__isnull=True),
                name="one_open_checkin_per_day_pass",
            ),
            # A visit belongs to exactly one of the two. Without this a row
            # with neither would be a visit by nobody, and a row with both
            # would be counted twice.
            models.CheckConstraint(
                condition=(
                    models.Q(user__isnull=False, day_pass__isnull=True)
                    | models.Q(user__isnull=True, day_pass__isnull=False)
                ),
                name="visit_belongs_to_member_or_guest",
            ),
        ]

    @property
    def who(self):
        return self.user or self.day_pass

    def __str__(self):
        return f"{self.who} @ {self.check_in_time:%Y-%m-%d %H:%M}"
