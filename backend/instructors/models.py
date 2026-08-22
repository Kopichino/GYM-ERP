from django.db import models


class Instructor(models.Model):
    """Content-only profile -- instructors don't need their own login for
    this MVP; admins manage these profiles."""

    name = models.CharField(max_length=150)
    bio = models.TextField(blank=True)
    specialty = models.CharField(max_length=150, blank=True)
    photo = models.ImageField(upload_to="instructor_photos/", null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
