from rest_framework import serializers

from .models import Device, DeviceEvent


class DeviceSerializer(serializers.ModelSerializer):
    event_count = serializers.SerializerMethodField()

    kind_name = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Device
        fields = [
            "id",
            "name",
            "serial",
            "location",
            "kind",
            "kind_name",
            "grace_days",
            "is_active",
            "last_seen_at",
            "event_count",
            "created_at",
        ]
        read_only_fields = ["id", "last_seen_at", "created_at"]

    def get_event_count(self, obj):
        return obj.events.count()


class DeviceEventSerializer(serializers.ModelSerializer):
    device_name = serializers.CharField(source="device.name", read_only=True)
    member_name = serializers.SerializerMethodField()

    class Meta:
        model = DeviceEvent
        fields = [
            "id",
            "device",
            "device_name",
            "biometric_id",
            "event_time",
            "outcome",
            "detail",
            "member",
            "member_name",
            "check_in",
            "received_at",
        ]
        read_only_fields = fields

    def get_member_name(self, obj):
        if not obj.member:
            return None
        return obj.member.get_full_name() or obj.member.username


class PunchSerializer(serializers.Serializer):
    """One punch as a terminal sends it."""

    biometric_id = serializers.CharField(max_length=64)
    event_time = serializers.DateTimeField()
    raw = serializers.JSONField(required=False)


class PunchBatchSerializer(serializers.Serializer):
    """Terminals buffer while offline, so the endpoint takes a batch."""

    punches = PunchSerializer(many=True, allow_empty=False, max_length=500)


class AccessRequestSerializer(serializers.Serializer):
    """What a turnstile sends when someone presents a card or finger."""

    identifier = serializers.CharField(max_length=64)
    # Optional: a gate that buffered while offline can report when the swipe
    # actually happened rather than when it managed to phone home.
    event_time = serializers.DateTimeField(required=False)
    raw = serializers.JSONField(required=False)
