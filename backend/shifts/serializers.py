from rest_framework import serializers

from .models import Position, Shift


class ShiftSerializer(serializers.ModelSerializer):
    staff_name = serializers.SerializerMethodField()
    staff_role = serializers.CharField(source="staff.role", read_only=True)
    position_name = serializers.CharField(source="get_position_display", read_only=True)
    # Length worked out from the two times, never stored.
    hours = serializers.FloatField(read_only=True)

    class Meta:
        model = Shift
        fields = [
            "id",
            "staff",
            "staff_name",
            "staff_role",
            "date",
            "start_time",
            "end_time",
            "hours",
            "position",
            "position_name",
            "notes",
            "created_by",
            "created_at",
        ]
        read_only_fields = ["id", "created_by", "created_at"]

    def get_staff_name(self, obj):
        return obj.staff.get_full_name() or obj.staff.username

    def validate(self, attrs):
        start = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end = attrs.get("end_time", getattr(self.instance, "end_time", None))
        if start and end and end <= start:
            raise serializers.ValidationError(
                {"end_time": "A shift has to end after it starts."}
            )
        return attrs


class PositionSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()

    @staticmethod
    def all():
        return [{"value": value, "label": label} for value, label in Position.choices]
