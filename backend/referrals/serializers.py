from rest_framework import serializers

from .models import Referral, ReferralProgram, ReferralReward


class ReferralProgramSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReferralProgram
        fields = ["id", "reward_days", "blurb", "is_active", "updated_at"]
        read_only_fields = ["id", "updated_at"]


class ReferralRewardSerializer(serializers.ModelSerializer):
    granted_by_name = serializers.CharField(source="granted_by.username", read_only=True)

    class Meta:
        model = ReferralReward
        fields = ["id", "referral", "days_granted", "payment", "granted_by", "granted_by_name",
                  "granted_on", "notes"]
        read_only_fields = fields


class ReferralSerializer(serializers.ModelSerializer):
    referrer_name = serializers.CharField(source="referrer.username", read_only=True)
    referred_username = serializers.CharField(source="referred_user.username", read_only=True)
    # Read off the ledger every time, so a refund moves it back on its own.
    status = serializers.CharField(read_only=True)
    is_rewardable = serializers.BooleanField(read_only=True)
    reward = ReferralRewardSerializer(read_only=True)

    class Meta:
        model = Referral
        fields = [
            "id",
            "referrer",
            "referrer_name",
            "name",
            "phone",
            "email",
            "referred_user",
            "referred_username",
            "enquiry",
            "status",
            "is_rewardable",
            "reward",
            "notes",
            "created_at",
        ]
        # A member names who they are referring; who that turns out to be, and
        # whether they paid, is not theirs to assert.
        read_only_fields = ["id", "referrer", "referred_user", "enquiry", "created_at"]


class MyReferralsSerializer(serializers.Serializer):
    """The member-facing summary: their code, the offer, and how they're doing."""

    code = serializers.CharField()
    blurb = serializers.CharField(allow_blank=True)
    reward_days = serializers.IntegerField()
    program_active = serializers.BooleanField()
    total_referred = serializers.IntegerField()
    joined_count = serializers.IntegerField()
    days_earned = serializers.IntegerField()
    referrals = ReferralSerializer(many=True)
