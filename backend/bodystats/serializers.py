from rest_framework import serializers

from .models import BodyMeasurement, GoalType, MemberGoal
from .services import calculate_bmi, current_value_for, goal_progress


class BodyMeasurementSerializer(serializers.ModelSerializer):
    bmi = serializers.SerializerMethodField()
    recorded_by_name = serializers.CharField(source="recorded_by.username", read_only=True)

    class Meta:
        model = BodyMeasurement
        fields = [
            "id",
            "user",
            "recorded_on",
            "weight_kg",
            "body_fat_pct",
            "bmi",
            "notes",
            "recorded_by",
            "recorded_by_name",
            "created_at",
        ]
        # `user` is resolved by the view from `?member=` / the `user` field in
        # the request body and checked against the caller's roster, so it must
        # not be settable straight through the serializer.
        read_only_fields = ["id", "user", "recorded_by", "created_at"]

    def get_bmi(self, obj):
        height = getattr(getattr(obj.user, "profile", None), "height_cm", None)
        return calculate_bmi(obj.weight_kg, height)


class MemberGoalSerializer(serializers.ModelSerializer):
    current_value = serializers.DecimalField(
        max_digits=7, decimal_places=2, required=False, allow_null=True
    )
    progress_pct = serializers.SerializerMethodField()
    live_value = serializers.SerializerMethodField()
    label = serializers.SerializerMethodField()

    class Meta:
        model = MemberGoal
        fields = [
            "id",
            "user",
            "goal_type",
            "label",
            "title",
            "start_value",
            "target_value",
            "current_value",
            "live_value",
            "progress_pct",
            "target_date",
            "status",
            "created_at",
        ]
        read_only_fields = ["id", "user", "created_at"]

    def get_progress_pct(self, obj):
        return goal_progress(obj)

    def get_live_value(self, obj):
        """What the goal is actually being measured against right now."""
        return current_value_for(obj)

    def get_label(self, obj):
        return obj.title or obj.get_goal_type_display()

    def validate(self, attrs):
        goal_type = attrs.get("goal_type", getattr(self.instance, "goal_type", None))
        title = attrs.get("title", getattr(self.instance, "title", ""))
        if goal_type == GoalType.CUSTOM and not title:
            raise serializers.ValidationError(
                {"title": "Give the custom goal a name so it's recognisable."}
            )
        return attrs
