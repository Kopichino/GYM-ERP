from rest_framework import serializers

from .models import Branding


class BrandingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branding
        fields = [
            "id",
            "name",
            "tagline",
            "logo",
            "accent",
            "accent_2",
            "display_font",
            "phone",
            "email",
            "address",
            "website",
            "instagram",
            "opening_hours",
            "gstin",
            "state",
            "is_active",
            "updated_at",
        ]
        read_only_fields = ["id", "is_active", "updated_at"]

    def validate_logo(self, logo):
        from core.uploads import validate_image_upload

        return validate_image_upload(logo)
