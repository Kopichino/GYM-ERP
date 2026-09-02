from rest_framework import serializers

from .models import Exercise, ExerciseVideo, WorkoutLog, WorkoutSession


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

    class Meta:
        model = WorkoutSession
        fields = ["id", "user", "date", "notes", "logs"]
        read_only_fields = ["id", "user", "date"]
