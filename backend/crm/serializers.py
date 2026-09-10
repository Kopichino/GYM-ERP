from rest_framework import serializers

from .models import Enquiry, EnquiryNote, RetentionPolicy


class EnquiryNoteSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.username", read_only=True)

    class Meta:
        model = EnquiryNote
        fields = ["id", "enquiry", "body", "author", "author_name", "created_at"]
        read_only_fields = ["id", "author", "created_at"]


class EnquirySerializer(serializers.ModelSerializer):
    is_due = serializers.BooleanField(read_only=True)
    is_converted = serializers.BooleanField(read_only=True)
    days_overdue = serializers.IntegerField(read_only=True)
    created_by_name = serializers.CharField(source="created_by.username", read_only=True)
    assigned_to_name = serializers.CharField(source="assigned_to.username", read_only=True)
    converted_username = serializers.CharField(source="converted_user.username", read_only=True)
    interested_in_name = serializers.CharField(source="interested_in.name", read_only=True)
    source_name = serializers.CharField(source="get_source_display", read_only=True)
    trail = EnquiryNoteSerializer(many=True, read_only=True)

    class Meta:
        model = Enquiry
        fields = [
            "id",
            "name",
            "phone",
            "email",
            "follow_up_on",
            "status",
            "source",
            "source_name",
            "interested_in",
            "interested_in_name",
            "assigned_to",
            "assigned_to_name",
            "converted_user",
            "converted_username",
            "notes",
            "last_contacted_on",
            "is_due",
            "is_converted",
            "days_overdue",
            "trail",
            "created_by",
            "created_by_name",
            "created_at",
        ]
        # Who this became is written by the conversion service, never claimed
        # by a request -- otherwise the conversion rate is just an opinion.
        read_only_fields = ["id", "created_by", "converted_user", "created_at"]

    def validate_phone(self, value):
        digits = [c for c in value if c.isdigit()]
        if len(digits) < 7:
            raise serializers.ValidationError("That doesn't look like a phone number.")
        return value.strip()


class RetentionPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = RetentionPolicy
        fields = ["id", "quiet_days", "cooling_days", "grace_days", "is_active", "updated_at"]
        read_only_fields = ["id", "is_active", "updated_at"]

    def validate(self, attrs):
        # Mirrors the database check so the desk gets a readable message rather
        # than an IntegrityError.
        quiet = attrs.get("quiet_days", getattr(self.instance, "quiet_days", 10))
        cooling = attrs.get("cooling_days", getattr(self.instance, "cooling_days", 5))
        if cooling >= quiet:
            raise serializers.ValidationError(
                {"cooling_days": "Must be fewer days than the quiet threshold."}
            )
        return attrs


class AtRiskMemberSerializer(serializers.Serializer):
    """A derived row -- there is no at-risk table behind this."""

    id = serializers.IntegerField()
    username = serializers.CharField()
    full_name = serializers.CharField()
    phone = serializers.CharField(allow_blank=True)
    email = serializers.CharField(allow_blank=True)
    trainer = serializers.CharField(allow_null=True)
    membership_status = serializers.CharField()
    last_visit = serializers.DateField(allow_null=True)
    days_since_visit = serializers.IntegerField()
    never_visited = serializers.BooleanField()
    band = serializers.CharField()
    expires_on = serializers.DateField(allow_null=True)
    days_left = serializers.IntegerField(allow_null=True)
