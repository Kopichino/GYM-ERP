from rest_framework import serializers

from accounts.models import Role
from tenancy import context
from tenancy.models import Membership

from .models import BookingStatus, ClassBooking, ClassSession
from .services import booked_count, spots_left


class UserNameField(serializers.RelatedField):
    """An account shown as a person's name, falling back to their username.

    Read-only. None when there is no account -- a class nobody in particular
    runs has no trainer to name.
    """

    def __init__(self, **kwargs):
        kwargs["read_only"] = True
        super().__init__(**kwargs)

    def to_representation(self, user):
        return user.get_full_name() or user.username


class ClassSessionSerializer(serializers.ModelSerializer):
    trainer_name = UserNameField(source="trainer")
    booked_count = serializers.SerializerMethodField()
    spots_left = serializers.SerializerMethodField()
    my_status = serializers.SerializerMethodField()

    class Meta:
        model = ClassSession
        fields = [
            "id",
            "title",
            "trainer",
            "trainer_name",
            "date",
            "start_time",
            "end_time",
            "capacity",
            "description",
            "booked_count",
            "spots_left",
            "my_status",
        ]

    def validate_trainer(self, trainer):
        """Only someone who trains at this gym can run one of its classes.

        The field would otherwise take any account id -- a member here, or a
        trainer at a different gym, whose name would then appear on this gym's
        timetable.
        """
        if trainer is None:
            return trainer
        trains_here = Membership.objects.filter(
            user=trainer, tenant=context.require(), role=Role.TRAINER, is_active=True
        ).exists()
        if not trains_here:
            raise serializers.ValidationError("That person is not a trainer at this gym.")
        return trainer

    def get_booked_count(self, obj):
        return booked_count(obj)

    def get_spots_left(self, obj):
        return spots_left(obj)

    def get_my_status(self, obj):
        """The requesting member's own place on this class, so the list can
        render Book or Cancel without a second round trip."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        booking = next(
            (b for b in obj.bookings.all() if b.member_id == request.user.id), None
        )
        if booking is None or booking.status == BookingStatus.CANCELLED:
            return None
        return booking.status


class ClassBookingSerializer(serializers.ModelSerializer):
    member_name = serializers.SerializerMethodField()
    session_title = serializers.CharField(source="session.title", read_only=True)
    date = serializers.DateField(source="session.date", read_only=True)
    start_time = serializers.TimeField(source="session.start_time", read_only=True)
    end_time = serializers.TimeField(source="session.end_time", read_only=True)
    trainer_name = UserNameField(source="session.trainer")

    class Meta:
        model = ClassBooking
        fields = [
            "id",
            "member",
            "member_name",
            "session",
            "session_title",
            "date",
            "start_time",
            "end_time",
            "trainer_name",
            "status",
            "position",
            "booked_at",
        ]
        read_only_fields = fields

    def get_member_name(self, obj):
        return obj.member.get_full_name() or obj.member.username
