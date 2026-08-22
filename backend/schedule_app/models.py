from django.db import models

from instructors.models import Instructor


class ClassSession(models.Model):
    """An upcoming/scheduled class, e.g. "Yoga, Mon 6pm with Instructor X"."""

    title = models.CharField(max_length=150)
    instructor = models.ForeignKey(
        Instructor, on_delete=models.SET_NULL, null=True, blank=True, related_name="class_sessions"
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    capacity = models.PositiveIntegerField(null=True, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["date", "start_time"]

    def __str__(self):
        return f"{self.title} - {self.date} {self.start_time}"
