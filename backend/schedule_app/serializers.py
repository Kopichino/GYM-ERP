from rest_framework import serializers

from .models import BookingStatus, ClassBooking, ClassSession
from .services import booked_count, spots_left


class ClassSessionSerializer(serializers.ModelSerializer):
    instructor_name = serializers.CharField(source="instructor.name", read_only=True, default=None)
    booked_count = serializers.SerializerMethodField()
    spots_left = serializers.SerializerMethodField()
    my_status = serializers.SerializerMethodField()

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
            "booked_count",
            "spots_left",
            "my_status",
        ]

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
    instructor_name = serializers.CharField(
        source="session.instructor.name", read_only=True, default=None
    )

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
            "instructor_name",
            "status",
            "position",
            "booked_at",
        ]
        read_only_fields = fields

    def get_member_name(self, obj):
        return obj.member.get_full_name() or obj.member.username
