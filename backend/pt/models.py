from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from tenancy.managers import TenantManager, UnscopedManager
from django.utils import timezone

from workouts.models import Weekday


class Availability(models.Model):
    """A window a trainer is open for one-to-one work, week after week.

    Recurring rather than a row per day: a trainer says "Tuesdays and Thursdays,
    two till six" once, not fifty-two times. The exceptions table below is how
    a specific day gets taken back.
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
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pt_availability"
    )
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["weekday", "start_time"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="availability_ends_after_it_starts",
            ),
            models.UniqueConstraint(
                fields=["trainer", "weekday", "start_time"],
                name="one_availability_per_start",
            ),
        ]

    def __str__(self):
        return (
            f"{self.trainer} {self.get_weekday_display()} "
            f"{self.start_time:%H:%M}-{self.end_time:%H:%M}"
        )


class Unavailable(models.Model):
    """A single day a trainer is not taking sessions, despite their pattern.

    Holidays and sick days are exceptions to a rule, so they are stored as
    exceptions -- deleting the weekly window and putting it back afterwards
    would lose the pattern and take every future slot with it.
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
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pt_unavailable"
    )
    date = models.DateField()
    reason = models.CharField(max_length=120, blank=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["date"]
        constraints = [
            models.UniqueConstraint(fields=["trainer", "date"], name="one_block_per_day")
        ]

    def __str__(self):
        return f"{self.trainer} unavailable {self.date}"


class SessionStatus(models.TextChoices):
    BOOKED = "booked", "Booked"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
    NO_SHOW = "no_show", "No show"


class PTSession(models.Model):
    """One member, one trainer, one hour.

    Its own table rather than `schedule_app.ClassSession`: a class is one
    session many members book onto, and a PT session is one member's slot that
    nobody else can take. Sharing a table would mean every capacity and
    waitlist rule had to carry an exception for the case where capacity is
    always exactly one.

    Money is recorded here rather than pushed through `record_payment`: that
    service writes membership periods, and a PT session does not extend
    anybody's membership. Mixing the two would make the derived subscription
    status wrong.
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
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pt_sessions_taken"
    )
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pt_sessions"
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    status = models.CharField(
        max_length=10, choices=SessionStatus.choices, default=SessionStatus.BOOKED
    )
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    is_paid = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    booked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pt_sessions_booked",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["date", "start_time"]
        indexes = [models.Index(fields=["trainer", "date"]), models.Index(fields=["member", "date"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="pt_session_ends_after_it_starts",
            ),
            # A trainer cannot have two live bookings starting at the same
            # moment. Genuine overlap needs more than an index, so the booking
            # service checks that under a lock; this catches the exact clash,
            # which is what a double-tapped Book button produces.
            models.UniqueConstraint(
                fields=["trainer", "date", "start_time"],
                condition=models.Q(status="booked"),
                name="one_live_pt_booking_per_slot",
            ),
        ]

    @property
    def is_past(self):
        return timezone.localdate() > self.date

    def __str__(self):
        return f"{self.member} with {self.trainer} on {self.date} {self.start_time:%H:%M}"
