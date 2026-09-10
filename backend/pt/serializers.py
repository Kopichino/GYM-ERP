from rest_framework import serializers

from .models import Availability, PTSession, Unavailable


class AvailabilitySerializer(serializers.ModelSerializer):
    trainer_name = serializers.CharField(source="trainer.username", read_only=True)
    weekday_name = serializers.CharField(source="get_weekday_display", read_only=True)
    # Declared with an explicit default rather than left to the model's.
    # A form-encoded POST simply omits an unchecked box, and DRF reads a
    # missing boolean in form data as False -- which created every new window
    # switched off, offering no slots and reporting "outside the trainer's
    # hours" to anyone who tried to book. The workout split hit exactly this.
    is_active = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = Availability
        fields = [
            "id",
            "trainer",
            "trainer_name",
            "weekday",
            "weekday_name",
            "start_time",
            "end_time",
            "is_active",
        ]
        read_only_fields = ["id", "trainer"]

    def validate(self, attrs):
        start = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end = attrs.get("end_time", getattr(self.instance, "end_time", None))
        if start and end and end <= start:
            raise serializers.ValidationError(
                {"end_time": "A window has to end after it starts."}
            )
        return attrs


class UnavailableSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unavailable
        fields = ["id", "trainer", "date", "reason"]
        read_only_fields = ["id", "trainer"]


class SlotSerializer(serializers.Serializer):
    """A derived slot -- there is no slot table behind this."""

    start_time = serializers.TimeField()
    end_time = serializers.TimeField()


class PTSessionSerializer(serializers.ModelSerializer):
    trainer_name = serializers.SerializerMethodField()
    member_name = serializers.SerializerMethodField()
    status_name = serializers.CharField(source="get_status_display", read_only=True)
    is_past = serializers.BooleanField(read_only=True)

    class Meta:
        model = PTSession
        fields = [
            "id",
            "trainer",
            "trainer_name",
            "member",
            "member_name",
            "date",
            "start_time",
            "end_time",
            "status",
            "status_name",
            "price",
            "is_paid",
            "is_past",
            "notes",
            "created_at",
        ]
        # Status moves through the cancel/complete actions, never by a PATCH:
        # a booking that could be edited into "completed" from the client is a
        # booking anybody can mark attended.
        read_only_fields = ["id", "status", "is_past", "created_at"]
        # DRF turns the model's partial unique index into a validator that
        # fires before the view runs, answering a member who tapped a taken
        # slot with "The fields trainer, date, start_time must make a unique
        # set." Cleared so the booking service gets to explain in words --
        # it also distinguishes "that slot has gone" from "you are already
        # booked then", which one index cannot. The constraint still stands
        # in the database, which is what actually guarantees the rule.
        validators = []

    def get_trainer_name(self, obj):
        return obj.trainer.get_full_name() or obj.trainer.username

    def get_member_name(self, obj):
        return obj.member.get_full_name() or obj.member.username
