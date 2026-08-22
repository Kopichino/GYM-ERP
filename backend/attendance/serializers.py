from rest_framework import serializers

from .models import CheckInOut


class CheckInOutSerializer(serializers.ModelSerializer):
    class Meta:
        model = CheckInOut
        fields = ["id", "user", "check_in_time", "check_out_time"]
        read_only_fields = ["id", "user", "check_in_time", "check_out_time"]
