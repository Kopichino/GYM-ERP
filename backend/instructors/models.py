from django.conf import settings
from django.db import models

from tenancy.managers import TenantManager, UnscopedManager


class Instructor(models.Model):
    """Public-facing trainer profile. `user` links it to a login account with
    role=TRAINER, which is what turns this profile into a trainer who can sign
    in to the trainer portal. Profiles with no `user` still work as
    content-only entries (e.g. a guest instructor shown on the schedule)."""
    # The branch this belongs to. Operational data is isolated per building:
    # "who came in yesterday" is a question about a gym, not about a brand.
    # Nullable for now; the backfill fills it and a later migration requires it.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="instructor_profile",
    )
    name = models.CharField(max_length=150)
    bio = models.TextField(blank=True)
    specialty = models.CharField(max_length=150, blank=True)
    photo = models.ImageField(upload_to="instructor_photos/", null=True, blank=True)
    active = models.BooleanField(default=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
