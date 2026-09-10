from django.conf import settings
from django.db import models

from tenancy.managers import TenantManager, UnscopedManager


class Position(models.TextChoices):
    """What someone is on the floor to do.

    Kept separate from `User.role`: a trainer can cover the front desk on a
    Saturday, and the rota needs to say so without changing what they are
    allowed to do in the system.
    """

    FLOOR = "floor", "Gym floor"
    FRONT_DESK = "front_desk", "Front desk"
    PT = "pt", "Personal training"
    CLASSES = "classes", "Classes"
    CLEANING = "cleaning", "Cleaning"
    MANAGEMENT = "management", "Management"


class Shift(models.Model):
    """One person, on the floor, between two times.

    Deliberately not `schedule_app`: a class is something members book onto and
    a shift is not. Putting them in one table would mean every class query had
    to remember to exclude rota rows, which is the kind of thing that is
    remembered right up until it isn't.

    Times are stored as a date plus two times rather than two datetimes, to
    match how the rota is actually written ("Ravi, Tuesday, 6 till 2") and how
    `ClassSession` already stores its slots.
    """
    # The branch this belongs to. Operational data is isolated per building:
    # "who came in yesterday" is a question about a gym, not about a brand.
    # Nullable for now; the backfill fills it and a later migration requires it.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shifts"
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    position = models.CharField(
        max_length=12, choices=Position.choices, default=Position.FLOOR
    )
    notes = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="shifts_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["date", "start_time"]
        indexes = [models.Index(fields=["date", "start_time"])]
        constraints = [
            # A shift that ends before it starts is a typo, not an overnight
            # shift -- those are entered as two rows, one per calendar day,
            # which is also how they are paid.
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="shift_ends_after_it_starts",
            ),
            # The same person cannot be rostered twice at the same moment.
            # Overlap needs more than a unique index, so the service checks it;
            # this catches the exact duplicate, which is the common slip.
            models.UniqueConstraint(
                fields=["staff", "date", "start_time"], name="one_shift_per_start"
            ),
        ]

    @property
    def hours(self):
        """Length in hours, worked out from the two times rather than stored --
        a duration column would drift the moment either end was edited."""
        start = self.start_time.hour * 60 + self.start_time.minute
        end = self.end_time.hour * 60 + self.end_time.minute
        return round((end - start) / 60, 2)

    def __str__(self):
        return f"{self.staff} {self.date} {self.start_time:%H:%M}-{self.end_time:%H:%M}"
