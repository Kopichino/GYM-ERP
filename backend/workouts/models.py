from django.conf import settings
from django.db import models


class Exercise(models.Model):
    """Admin-seeded catalog. Members pick from this rather than free-typing
    exercise names, which keeps progress-tracker aggregation (charting the
    same exercise over time) clean."""

    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=50, blank=True)
    muscle_group = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class WorkoutSession(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workout_sessions"
    )
    date = models.DateField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.user} - {self.date}"


class WeightUnit(models.TextChoices):
    KG = "kg", "kg"
    LB = "lb", "lb"


class WorkoutLog(models.Model):
    session = models.ForeignKey(WorkoutSession, on_delete=models.CASCADE, related_name="logs")
    exercise = models.ForeignKey(Exercise, on_delete=models.PROTECT, related_name="logs")
    set_number = models.PositiveSmallIntegerField()
    reps = models.PositiveIntegerField()
    weight = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    weight_unit = models.CharField(max_length=2, choices=WeightUnit.choices, default=WeightUnit.KG)

    class Meta:
        ordering = ["set_number"]

    def __str__(self):
        return f"{self.exercise} set {self.set_number}: {self.reps}x{self.weight}{self.weight_unit}"
