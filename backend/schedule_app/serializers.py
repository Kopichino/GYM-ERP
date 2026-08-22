from rest_framework import serializers

from .models import ClassSession


class ClassSessionSerializer(serializers.ModelSerializer):
    instructor_name = serializers.CharField(source="instructor.name", read_only=True, default=None)

    class Meta:
        model = ClassSession
        fields = [
            "id",
            "title",
            "instructor",
            "instructor_name",
            "date",
            "start_time",
            "end_time",
            "capacity",
            "description",
        ]
