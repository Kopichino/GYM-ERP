from rest_framework import serializers

from core.uploads import validate_gallery_media

from .models import GalleryPost


class GalleryPostSerializer(serializers.ModelSerializer):
    uploader_name = serializers.CharField(source="uploader.get_full_name", read_only=True)

    class Meta:
        model = GalleryPost
        fields = [
            "id",
            "uploader",
            "uploader_name",
            "media",
            "media_type",
            "caption",
            "approved",
            "created_at",
        ]
        read_only_fields = ["id", "uploader", "approved", "created_at"]

    def validate(self, attrs):
        media = attrs.get("media")
        if media:
            # The declared media type decides which formats are acceptable; the
            # file's own bytes decide whether it is one. The browser's content
            # type decides nothing -- see core.uploads.
            try:
                validate_gallery_media(media, attrs.get("media_type"))
            except serializers.ValidationError as exc:
                raise serializers.ValidationError({"media": exc.detail}) from None
        return attrs
