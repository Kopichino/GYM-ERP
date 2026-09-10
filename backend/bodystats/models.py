from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from tenancy.managers import TenantManager, UnscopedManager
from django.utils import timezone


class BodyMeasurement(models.Model):
    """One weigh-in. Weight is stored canonically in kilograms so BMI and trend
    maths never have to guess at units -- the UI converts for display.

    BMI is deliberately *not* a column here: it is a pure function of this row's
    weight and the profile's height, so storing it would create a second copy of
    the truth that drifts the moment either input changes (the same reasoning
    that keeps subscription status derived from the payment ledger)."""
    # Logged in the context of one gym's programme, trainers and badges. A
    # member who trains at two gyms has a history at each; Gym A's sets must not
    # feed Gym B's leaderboards.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="measurements"
    )
    recorded_on = models.DateField(default=timezone.localdate)
    weight_kg = models.DecimalField(
        max_digits=5, decimal_places=2, validators=[MinValueValidator(1)]
    )
    body_fat_pct = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    notes = models.CharField(max_length=200, blank=True)
    # Set when a trainer weighs a member in, so the log shows who took it.
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="measurements_recorded",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-recorded_on", "-id"]
        constraints = [
            # One weigh-in per member per day keeps the trend chart honest; a
            # second reading for the same date updates the first.
            models.UniqueConstraint(
                fields=["user", "recorded_on"], name="one_measurement_per_user_per_day"
            )
        ]

    def __str__(self):
        return f"{self.user} - {self.weight_kg}kg on {self.recorded_on}"


class GoalType(models.TextChoices):
    WEIGHT = "weight", "Target weight"
    BODY_FAT = "body_fat", "Target body fat"
    ATTENDANCE = "attendance", "Monthly visits"
    CUSTOM = "custom", "Custom"


class GoalStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    ACHIEVED = "achieved", "Achieved"
    ARCHIVED = "archived", "Archived"


class MemberGoal(models.Model):
    """A target a member is working toward. Progress is computed from live data
    (latest weigh-in, this month's check-ins) rather than stored, so it can
    never fall out of step with the numbers it summarises."""
    # Logged in the context of one gym's programme, trainers and badges. A
    # member who trains at two gyms has a history at each; Gym A's sets must not
    # feed Gym B's leaderboards.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="goals"
    )
    goal_type = models.CharField(max_length=12, choices=GoalType.choices)
    title = models.CharField(
        max_length=150, blank=True, help_text="Shown instead of the type label for custom goals."
    )
    # Snapshot of where the member stood when the goal was set -- without it,
    # "40% of the way there" has no baseline to measure from.
    start_value = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    target_value = models.DecimalField(max_digits=7, decimal_places=2)
    # Only custom goals carry a hand-entered current value; the rest read theirs
    # from measurements or attendance.
    current_value = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    target_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=GoalStatus.choices, default=GoalStatus.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["status", "-created_at"]

    def __str__(self):
        return f"{self.user} - {self.get_goal_type_display()} {self.target_value}"
