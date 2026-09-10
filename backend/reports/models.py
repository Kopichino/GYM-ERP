from django.conf import settings
from django.db import models

from tenancy.managers import TenantManager, UnscopedManager


class SavedReport(models.Model):
    """A custom report definition someone wants to keep.

    Only the definition is stored, never its results -- reopening a saved report
    re-runs it against today's data rather than showing a stale snapshot.
    """
    # The branch this belongs to. Operational data is isolated per building:
    # "who came in yesterday" is a question about a gym, not about a brand.
    # Nullable for now; the backfill fills it and a later migration requires it.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    name = models.CharField(max_length=120)
    description = models.CharField(max_length=250, blank=True)
    definition = models.JSONField()
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="saved_reports",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
