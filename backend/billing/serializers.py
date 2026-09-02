from rest_framework import serializers

from accounts.models import User

from .models import Payment, Plan
from .services import get_latest_completed_payment


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ["id", "name", "price", "duration_days", "description", "is_active"]


class AdminPaymentSerializer(serializers.ModelSerializer):
    """Used by the admin "record payment" form and the payments ledger."""

    plan_name = serializers.CharField(source="plan.name", read_only=True)
    member_username = serializers.CharField(source="member.username", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "member",
            "member_username",
            "plan",
            "plan_name",
            "amount",
            "method",
            "status",
            "paid_date",
            "period_start",
            "period_end",
            "notes",
            "recorded_by",
            "external_reference",
            "gateway",
            "created_at",
        ]
        read_only_fields = ["period_start", "period_end", "recorded_by", "created_at"]


class MyPaymentSerializer(serializers.ModelSerializer):
    """Read-only payment history for a member's own Billing page."""

    plan_name = serializers.CharField(source="plan.name", read_only=True)

    class Meta:
        model = Payment
        fields = ["id", "plan_name", "amount", "method", "status", "paid_date", "period_start", "period_end"]
        read_only_fields = fields


class AdminMemberBillingSerializer(serializers.ModelSerializer):
    """Admin billing list + Excel export -- same queryset/serializer for
    both, so the download always matches what's on screen (mirrors
    accounts.AdminMemberSerializer)."""

    membership_status = serializers.CharField(source="profile.membership_status", default="", read_only=True)
    current_plan_name = serializers.SerializerMethodField()
    current_period_end = serializers.SerializerMethodField()
    last_payment_date = serializers.SerializerMethodField()
    last_payment_amount = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "membership_status",
            "current_plan_name",
            "current_period_end",
            "last_payment_date",
            "last_payment_amount",
        ]

    def _last_payment(self, obj):
        return obj.payments.order_by("-paid_date", "-id").first()

    def get_current_plan_name(self, obj):
        payment = get_latest_completed_payment(obj)
        return payment.plan.name if payment else None

    def get_current_period_end(self, obj):
        payment = get_latest_completed_payment(obj)
        return payment.period_end.isoformat() if payment else None

    def get_last_payment_date(self, obj):
        payment = self._last_payment(obj)
        return payment.paid_date.isoformat() if payment else None

    def get_last_payment_amount(self, obj):
        payment = self._last_payment(obj)
        return str(payment.amount) if payment else None
