from rest_framework import serializers

from .models import Message


class MessageSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    direction_name = serializers.CharField(source="get_direction_display", read_only=True)

    class Meta:
        model = Message
        fields = [
            "id",
            "user",
            "username",
            "phone",
            "direction",
            "direction_name",
            "body",
            "status",
            "external_id",
            "error",
            "is_automated",
            "created_at",
        ]
        read_only_fields = fields
