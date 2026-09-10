from django.conf import settings
from django.db import models

from tenancy.managers import TenantManager, UnscopedManager


class MediaType(models.TextChoices):
    IMAGE = "image", "Image"
    VIDEO = "video", "Video"


class GalleryPost(models.Model):
    # The branch this belongs to. Operational data is isolated per building:
    # "who came in yesterday" is a question about a gym, not about a brand.
    # Nullable for now; the backfill fills it and a later migration requires it.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )
    uploader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gallery_posts",
    )
    media = models.FileField(upload_to="gallery/")
    media_type = models.CharField(max_length=5, choices=MediaType.choices)
    caption = models.CharField(max_length=300, blank=True)
    # Uploads are hidden from the public feed until an admin approves them --
    # keeps moderation lightweight with no extra infrastructure.
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.media_type} by {self.uploader} ({'approved' if self.approved else 'pending'})"
