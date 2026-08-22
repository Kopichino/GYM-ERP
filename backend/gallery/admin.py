from django.contrib import admin

from .models import GalleryPost


@admin.register(GalleryPost)
class GalleryPostAdmin(admin.ModelAdmin):
    list_display = ["uploader", "media_type", "approved", "created_at"]
    list_filter = ["approved", "media_type"]
    actions = ["approve_posts"]

    @admin.action(description="Approve selected posts")
    def approve_posts(self, request, queryset):
        queryset.update(approved=True)
