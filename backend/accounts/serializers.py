from django.contrib.auth import password_validation
from rest_framework import serializers

from .models import MemberProfile, Role, User


class MemberProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = MemberProfile
        fields = [
            "phone",
            "date_of_birth",
            "height_cm",
            "join_date",
            "membership_status",
            "emergency_contact_name",
            "emergency_contact_phone",
            "photo",
        ]
        # join_date and membership_status are the gym's to set, not the
        # member's -- status in particular is derived from the payment ledger.
        read_only_fields = ["join_date", "membership_status"]


class UserSerializer(serializers.ModelSerializer):
    profile = MemberProfileSerializer()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "is_staff",
            "profile",
        ]
        read_only_fields = ["id", "role", "is_staff"]

    def update(self, instance, validated_data):
        """Nested write so a member can maintain their own details (height,
        phone, emergency contact) from /me/. `trainer` isn't a field on this
        serializer, so assignment stays an admin-only action."""
        profile_data = validated_data.pop("profile", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()

        if profile_data:
            profile, _ = MemberProfile.objects.get_or_create(user=instance)
            for field, value in profile_data.items():
                setattr(profile, field, value)
            profile.save()
        return instance


class TrainerMemberSerializer(serializers.ModelSerializer):
    """A trainer's view of one of their assigned members -- deliberately
    excludes billing/payment fields, which are admin-only."""

    phone = serializers.CharField(source="profile.phone", default="", read_only=True)
    join_date = serializers.DateField(source="profile.join_date", read_only=True)
    membership_status = serializers.CharField(
        source="profile.membership_status", default="", read_only=True
    )
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
        read_only_fields = fields

    def get_last_check_in(self, obj):
        record = obj.check_ins.order_by("-check_in_time").first()
        return record.check_in_time.isoformat() if record else None


class AdminMemberSerializer(serializers.ModelSerializer):
    """Used by both the admin member-list screen and the Excel export, so
    the two never drift out of sync."""

    phone = serializers.CharField(source="profile.phone", default="", read_only=True)
    join_date = serializers.DateField(source="profile.join_date", read_only=True)
    membership_status = serializers.CharField(source="profile.membership_status", default="", read_only=True)
    trainer = serializers.PrimaryKeyRelatedField(source="profile.trainer", read_only=True)
    trainer_name = serializers.SerializerMethodField()
    biometric_id = serializers.CharField(
        source="profile.biometric_id", default=None, read_only=True
    )
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
            "trainer",
            "trainer_name",
            "biometric_id",
            "last_check_in",
        ]

    def get_trainer_name(self, obj):
        trainer = getattr(obj.profile, "trainer", None) if hasattr(obj, "profile") else None
        return (trainer.get_full_name() or trainer.username) if trainer else None

    def get_last_check_in(self, obj):
        record = obj.check_ins.order_by("-check_in_time").first()
        # Return an ISO string, not a raw tz-aware datetime -- SerializerMethodField
        # skips normal field serialization, and openpyxl rejects tz-aware datetimes.
        return record.check_in_time.isoformat() if record else None


class SignupSerializer(serializers.ModelSerializer):
    """Public self-signup -- always creates a plain member. Role is not a
    field here on purpose: an account may only be promoted to trainer/admin
    by an existing admin."""

    password = serializers.CharField(write_only=True)
    # Optional, and deliberately not validated: someone joining is not the
    # person who mistyped the code, so a bad one must never block a signup.
    referral_code = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "password",
            "first_name",
            "last_name",
            "referral_code",
        ]

    def validate_password(self, value):
        password_validation.validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        referral_code = validated_data.pop("referral_code", "")
        user = User(**validated_data, role=Role.MEMBER)
        user.set_password(password)
        user.save()
        MemberProfile.objects.create(user=user)
        if referral_code:
            # Imported here: accounts is the lower-level app, and a module-level
            # import would make referrals a hard dependency of signing up.
            from referrals.services import claim

            claim(referral_code, user)
        return user


class AdminUserSerializer(serializers.ModelSerializer):
    """Admin-only account management: create trainers/admins, change a
    member's role, and assign a trainer to a member."""

    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    trainer = serializers.PrimaryKeyRelatedField(
        source="profile.trainer",
        queryset=User.objects.filter(role=Role.TRAINER),
        required=False,
        allow_null=True,
    )
    # Enrolling a member on the door terminal is an admin action -- members
    # must not be able to claim someone else's biometric id.
    biometric_id = serializers.CharField(
        source="profile.biometric_id", required=False, allow_null=True, allow_blank=True
    )

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "password",
            "trainer",
            "biometric_id",
        ]

    def validate_password(self, value):
        if value:
            password_validation.validate_password(value)
        return value

    def create(self, validated_data):
        profile_data = validated_data.pop("profile", {})
        password = validated_data.pop("password", "")
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        MemberProfile.objects.create(
            user=user,
            trainer=profile_data.get("trainer"),
            # Blank would collide with other un-enrolled members on the unique
            # index, so an absent id is stored as NULL.
            biometric_id=profile_data.get("biometric_id") or None,
        )
        return user

    def update(self, instance, validated_data):
        profile_data = validated_data.pop("profile", {})
        password = validated_data.pop("password", "")
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()

        if password:
            # A new password has to end the sessions the old one opened.
            # Refresh tokens live for a week and survive a password change on
            # their own, so resetting the password of an account you think is
            # compromised would otherwise leave the intruder signed in.
            from .tokens import revoke_refresh_tokens

            revoke_refresh_tokens(instance)

        if profile_data:
            profile, _ = MemberProfile.objects.get_or_create(user=instance)
            if "trainer" in profile_data:
                profile.trainer = profile_data["trainer"]
            if "biometric_id" in profile_data:
                profile.biometric_id = profile_data["biometric_id"] or None
            profile.save()
        return instance
