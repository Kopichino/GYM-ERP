from rest_framework import serializers

from .models import Instructor


class InstructorSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = Instructor
        fields = ["id", "user", "username", "name", "bio", "specialty", "photo", "active"]
