from django.contrib.auth import password_validation
from rest_framework import serializers

from .models import MemberProfile, User


class MemberProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = MemberProfile
        fields = [
            "phone",
            "date_of_birth",
            "join_date",
            "membership_status",
            "emergency_contact_name",
            "emergency_contact_phone",
            "photo",
        ]
        read_only_fields = ["join_date", "membership_status"]


class UserSerializer(serializers.ModelSerializer):
    profile = MemberProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "is_staff", "profile"]
        read_only_fields = ["id", "is_staff"]


class AdminMemberSerializer(serializers.ModelSerializer):
    """Used by both the admin member-list screen and the Excel export, so
    the two never drift out of sync."""

    phone = serializers.CharField(source="profile.phone", default="", read_only=True)
    join_date = serializers.DateField(source="profile.join_date", read_only=True)
    membership_status = serializers.CharField(source="profile.membership_status", default="", read_only=True)
    last_check_in = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "phone",
            "join_date",
            "membership_status",
            "last_check_in",
        ]

    def get_last_check_in(self, obj):
        record = obj.check_ins.order_by("-check_in_time").first()
        # Return an ISO string, not a raw tz-aware datetime -- SerializerMethodField
        # skips normal field serialization, and openpyxl rejects tz-aware datetimes.
        return record.check_in_time.isoformat() if record else None


class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["username", "email", "password", "first_name", "last_name"]

    def validate_password(self, value):
        password_validation.validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        MemberProfile.objects.create(user=user)
        return user
