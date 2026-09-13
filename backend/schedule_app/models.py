from django.conf import settings
from django.db import models

from tenancy.managers import TenantManager, UnscopedManager


class ClassSession(models.Model):
    """An upcoming/scheduled class, e.g. "Yoga, Mon 6pm with Ravi"."""
    # The branch this belongs to. Operational data is isolated per building:
    # "who came in yesterday" is a question about a gym, not about a brand.
    # Nullable for now; the backfill fills it and a later migration requires it.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    title = models.CharField(max_length=150)
    #: The trainer running the class -- their own account. This used to point
    #: at a separate instructor profile, but it is the same person who logs in,
    #: takes the roster and marks who turned up, so a second record naming them
    #: was only ever something to keep in step. Null for a class nobody in
    #: particular runs.
    trainer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="classes_run",
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    capacity = models.PositiveIntegerField(null=True, blank=True)
    description = models.TextField(blank=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["date", "start_time"]

    def __str__(self):
        return f"{self.title} - {self.date} {self.start_time}"


class BookingStatus(models.TextChoices):
    BOOKED = "booked", "Booked"
    WAITLISTED = "waitlisted", "Waitlisted"
    CANCELLED = "cancelled", "Cancelled"
    ATTENDED = "attended", "Attended"


class ClassBooking(models.Model):
    """A member's place on a class.

    One row per member per class for its whole life -- cancelling flips the
    status rather than deleting, so re-booking reuses the row and the unique
    constraint below can stay simple. `position` orders the waitlist, which is
    how a cancellation knows who to promote.
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
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="class_bookings"
    )
    session = models.ForeignKey(ClassSession, on_delete=models.CASCADE, related_name="bookings")
    status = models.CharField(
        max_length=10, choices=BookingStatus.choices, default=BookingStatus.BOOKED
    )
    position = models.PositiveIntegerField(
        null=True, blank=True, help_text="Place in the waitlist queue; null once booked."
    )
    booked_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["position", "booked_at"]
        constraints = [
            # A member cannot hold two places on the same class.
            models.UniqueConstraint(
                fields=["member", "session"], name="one_booking_per_member_per_class"
            )
        ]

    def __str__(self):
        return f"{self.member} - {self.session} ({self.status})"
