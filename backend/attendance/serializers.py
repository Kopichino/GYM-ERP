from rest_framework import serializers

from .models import CheckInOut


class CheckInOutSerializer(serializers.ModelSerializer):
    # Whoever the visit belongs to -- a member or a walk-in -- so a caller
    # doesn't have to check which of the two fields is set.
    who = serializers.SerializerMethodField()

    def get_who(self, obj):
        if obj.user_id:
            return obj.user.get_full_name() or obj.user.username
        return obj.day_pass.name if obj.day_pass_id else None

    class Meta:
        model = CheckInOut
        # `method` is read-only like the rest: which route recorded the visit
        # is decided by the service that opened it, never by the client.
        fields = [
            "id",
            "user",
            "day_pass",
            "who",
            "check_in_time",
            "check_out_time",
            "method",
        ]
        read_only_fields = fields
