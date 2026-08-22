from rest_framework import serializers

from .models import GalleryPost

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB -- keeps Cloudinary's free bandwidth/storage cap safe
ALLOWED_CONTENT_TYPES = {
    "image": {"image/jpeg", "image/png", "image/webp", "image/gif"},
    "video": {"video/mp4", "video/quicktime", "video/webm"},
}


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
        media_type = attrs.get("media_type")
        if media and media.size > MAX_UPLOAD_BYTES:
            raise serializers.ValidationError("File too large (max 20MB).")
        if media and media_type:
            content_type = getattr(media, "content_type", "")
            if content_type not in ALLOWED_CONTENT_TYPES.get(media_type, set()):
                raise serializers.ValidationError(
                    f"File type {content_type!r} doesn't match declared media_type {media_type!r}."
                )
        return attrs
