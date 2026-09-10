from django.contrib import admin

from .models import Branding


@admin.register(Branding)
class BrandingAdmin(admin.ModelAdmin):
    list_display = ["name", "accent", "accent_2", "is_active", "updated_at"]
