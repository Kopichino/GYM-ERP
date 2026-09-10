from django.conf import settings
from django.db import models

from tenancy.managers import TenantManager, UnscopedManager


class Exercise(models.Model):
    """Admin-seeded catalog. Members pick from this rather than free-typing
    exercise names, which keeps progress-tracker aggregation (charting the
    same exercise over time) clean."""

    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=50, blank=True)
    muscle_group = models.CharField(max_length=50, blank=True)
    region = models.CharField(
        max_length=60,
        blank=True,
        help_text="Sub-muscle group within muscle_group, e.g. 'Upper Chest'.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ExerciseVideo(models.Model):
    """Admin-curated tutorial links (YouTube Shorts, etc.) shown under an
    exercise so members can check their form without leaving the app."""

    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name="videos")
    title = models.CharField(max_length=150, blank=True)
    url = models.URLField()
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title or self.url


class WorkoutSession(models.Model):
    # Logged in the context of one gym's programme, trainers and badges. A
    # member who trains at two gyms has a history at each; Gym A's sets must not
    # feed Gym B's leaderboards.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workout_sessions"
    )
    date = models.DateField(auto_now_add=True)
    notes = models.TextField(blank=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.user} - {self.date}"


class Weekday(models.IntegerChoices):
    """Matches Python's date.weekday(), so "is today a training day?" is a
    direct lookup rather than an offset calculation."""

    MONDAY = 0, "Monday"
    TUESDAY = 1, "Tuesday"
    WEDNESDAY = 2, "Wednesday"
    THURSDAY = 3, "Thursday"
    FRIDAY = 4, "Friday"
    SATURDAY = 5, "Saturday"
    SUNDAY = 6, "Sunday"


class WorkoutSplit(models.Model):
    """A member's weekly training plan.

    Days are pinned to weekdays rather than run as a rotating cycle, because
    the check-in screen has to answer "what am I training today?" with no
    ambiguity -- a rotating cycle would need a start date and would drift every
    time someone skipped a session.

    How many days a week the member trains is deliberately not a column: it is
    just how many days they've added, and storing it as well would give the two
    a way to disagree.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="splits"
    )
    name = models.CharField(max_length=100, default="My weekly split")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_active", "-updated_at"]
        constraints = [
            # Only one plan can be the current one, so "today's split" always
            # has a single answer. Old plans are kept, deactivated.
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_active=True),
                name="one_active_split_per_user",
            )
        ]

    @property
    def days_per_week(self):
        return self.days.count()

    def __str__(self):
        return f"{self.user} - {self.name}"


class SplitDay(models.Model):
    """One training day. `target_muscles` is asked for before any exercise is
    picked -- it's what narrows the catalog down to a sensible shortlist."""

    split = models.ForeignKey(WorkoutSplit, on_delete=models.CASCADE, related_name="days")
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    label = models.CharField(
        max_length=60, blank=True, help_text="e.g. Push, Pull, Legs. Defaults to the muscles."
    )
    # Free-form strings matched against Exercise.muscle_group, which is itself a
    # CharField populated from the imported catalog rather than a fixed enum.
    target_muscles = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["weekday"]
        constraints = [
            models.UniqueConstraint(fields=["split", "weekday"], name="one_day_per_weekday")
        ]

    @property
    def display_label(self):
        return self.label or " / ".join(self.target_muscles) or "Training"

    def __str__(self):
        return f"{self.get_weekday_display()} - {self.display_label}"


class SplitExercise(models.Model):
    """An exercise slotted into a training day, with an optional target."""

    day = models.ForeignKey(SplitDay, on_delete=models.CASCADE, related_name="exercises")
    exercise = models.ForeignKey("Exercise", on_delete=models.PROTECT, related_name="split_entries")
    order = models.PositiveSmallIntegerField(default=0)
    target_sets = models.PositiveSmallIntegerField(null=True, blank=True)
    target_reps = models.CharField(
        max_length=20, blank=True, help_text="Free text so ranges like '8-12' work."
    )

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.day} - {self.exercise}"


class WeightUnit(models.TextChoices):
    KG = "kg", "kg"
    LB = "lb", "lb"


class WorkoutLog(models.Model):
    # Logged in the context of one gym's programme, trainers and badges. A
    # member who trains at two gyms has a history at each; Gym A's sets must not
    # feed Gym B's leaderboards.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )
    session = models.ForeignKey(WorkoutSession, on_delete=models.CASCADE, related_name="logs")
    exercise = models.ForeignKey(Exercise, on_delete=models.PROTECT, related_name="logs")
    set_number = models.PositiveSmallIntegerField()
    reps = models.PositiveIntegerField()
    weight = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    weight_unit = models.CharField(max_length=2, choices=WeightUnit.choices, default=WeightUnit.KG)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["set_number"]

    def __str__(self):
        return f"{self.exercise} set {self.set_number}: {self.reps}x{self.weight}{self.weight_unit}"
