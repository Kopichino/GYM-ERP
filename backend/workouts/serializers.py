from rest_framework import serializers

from .models import (
    Exercise,
    ExerciseVideo,
    SplitDay,
    SplitExercise,
    WorkoutLog,
    WorkoutSession,
    WorkoutSplit,
)


class ExerciseVideoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExerciseVideo
        fields = ["id", "title", "url", "order"]


class ExerciseSerializer(serializers.ModelSerializer):
    videos = ExerciseVideoSerializer(many=True, read_only=True)

    class Meta:
        model = Exercise
        fields = ["id", "name", "category", "muscle_group", "region", "videos"]


class WorkoutLogSerializer(serializers.ModelSerializer):
    exercise_name = serializers.CharField(source="exercise.name", read_only=True)

    class Meta:
        model = WorkoutLog
        fields = [
            "id",
            "session",
            "exercise",
            "exercise_name",
            "set_number",
            "reps",
            "weight",
            "weight_unit",
        ]


class WorkoutSessionSerializer(serializers.ModelSerializer):
    logs = WorkoutLogSerializer(many=True, read_only=True)
    user_name = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = WorkoutSession
        # `user` is writable so a trainer can open a session on behalf of an
        # assigned member; the view rejects members they aren't assigned to.
        fields = ["id", "user", "user_name", "date", "notes", "logs"]
        read_only_fields = ["id", "date"]
        extra_kwargs = {"user": {"required": False}}


class SplitExerciseSerializer(serializers.ModelSerializer):
    exercise_name = serializers.CharField(source="exercise.name", read_only=True)
    muscle_group = serializers.CharField(source="exercise.muscle_group", read_only=True)
    region = serializers.CharField(source="exercise.region", read_only=True)
    videos = ExerciseVideoSerializer(source="exercise.videos", many=True, read_only=True)

    class Meta:
        model = SplitExercise
        fields = [
            "id",
            "day",
            "exercise",
            "exercise_name",
            "muscle_group",
            "region",
            "videos",
            "order",
            "target_sets",
            "target_reps",
        ]
        read_only_fields = ["id"]


class SplitDaySerializer(serializers.ModelSerializer):
    exercises = SplitExerciseSerializer(many=True, read_only=True)
    weekday_name = serializers.CharField(source="get_weekday_display", read_only=True)
    display_label = serializers.CharField(read_only=True)

    class Meta:
        model = SplitDay
        fields = [
            "id",
            "split",
            "weekday",
            "weekday_name",
            "label",
            "display_label",
            "target_muscles",
            "notes",
            "exercises",
        ]
        read_only_fields = ["id"]

    def validate_target_muscles(self, value):
        if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
            raise serializers.ValidationError("Expected a list of muscle group names.")
        # Trim and de-duplicate while keeping the order the member chose.
        seen, cleaned = set(), []
        for muscle in (v.strip() for v in value):
            if muscle and muscle.lower() not in seen:
                seen.add(muscle.lower())
                cleaned.append(muscle)
        return cleaned


class WorkoutSplitSerializer(serializers.ModelSerializer):
    days = SplitDaySerializer(many=True, read_only=True)
    days_per_week = serializers.IntegerField(read_only=True)

    class Meta:
        model = WorkoutSplit
        fields = ["id", "user", "name", "is_active", "days_per_week", "days", "created_at"]
        # `is_active` is not client-settable: a new plan is always the current
        # one, and switching back to an old plan goes through the `activate`
        # action. Leaving it writable meant a form-encoded POST that simply
        # omitted the field arrived as False -- DRF reads a missing boolean in
        # form data as unchecked -- which silently filed the new plan away as
        # inactive and left the old one current.
        read_only_fields = ["id", "user", "is_active", "created_at"]


class TodaySplitSerializer(serializers.Serializer):
    """What the check-in screen needs: is today a training day, and what's on it."""

    is_training_day = serializers.BooleanField()
    weekday_name = serializers.CharField()
    has_split = serializers.BooleanField()
    day = SplitDaySerializer(allow_null=True)
