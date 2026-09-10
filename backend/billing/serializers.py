from decimal import Decimal

from rest_framework import serializers

from accounts.models import User

from .models import DayPass, Discount, Payment, Plan
from .services import get_latest_completed_payment


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ["id", "name", "price", "duration_days", "description", "is_active"]


class AdminPaymentSerializer(serializers.ModelSerializer):
    """Used by the admin "record payment" form and the payments ledger."""

    plan_name = serializers.CharField(source="plan.name", read_only=True)
    member_username = serializers.CharField(source="member.username", read_only=True)
    discount_code = serializers.CharField(source="discount.code", read_only=True, default=None)
    gross_amount = serializers.SerializerMethodField()

    def get_gross_amount(self, obj):
        """What it would have cost without the offer -- derived, not stored."""
        return str(obj.amount + obj.discount_amount)

    class Meta:
        model = Payment
        fields = [
            "id",
            "member",
            "member_username",
            "plan",
            "plan_name",
            "amount",
            "discount",
            "discount_code",
            "discount_amount",
            "gross_amount",
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
        read_only_fields = [
            "period_start",
            "period_end",
            "recorded_by",
            "created_at",
            "discount_amount",
        ]


class MyPaymentSerializer(serializers.ModelSerializer):
    """Read-only payment history for a member's own Billing page."""

    plan_name = serializers.CharField(source="plan.name", read_only=True)
    discount_code = serializers.CharField(source="discount.code", read_only=True, default=None)

    class Meta:
        model = Payment
        fields = [
            "id",
            "plan_name",
            "amount",
            "discount_code",
            "discount_amount",
            "method",
            "status",
            "paid_date",
            "period_start",
            "period_end",
        ]
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


class DiscountSerializer(serializers.ModelSerializer):
    times_used = serializers.IntegerField(read_only=True)
    plan_names = serializers.SerializerMethodField()

    class Meta:
        model = Discount
        fields = [
            "id",
            "code",
            "description",
            "discount_type",
            "value",
            "plans",
            "plan_names",
            "valid_from",
            "valid_until",
            "max_uses",
            "max_uses_per_member",
            "is_active",
            "times_used",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_plan_names(self, obj):
        names = [p.name for p in obj.plans.all()]
        return names or ["All plans"]

    def validate(self, attrs):
        kind = attrs.get("discount_type", getattr(self.instance, "discount_type", None))
        value = attrs.get("value", getattr(self.instance, "value", None))
        if kind == "percent" and value is not None and value > 100:
            raise serializers.ValidationError({"value": "A percentage can't exceed 100."})

        start = attrs.get("valid_from", getattr(self.instance, "valid_from", None))
        end = attrs.get("valid_until", getattr(self.instance, "valid_until", None))
        if start and end and end < start:
            raise serializers.ValidationError({"valid_until": "End date is before the start date."})
        return attrs


class CheckoutSerializer(serializers.Serializer):
    """One sale at the counter. `code` is optional; everything else mirrors what
    the till needs to take payment."""

    member = serializers.IntegerField()
    plan = serializers.IntegerField()
    code = serializers.CharField(required=False, allow_blank=True)
    # What to actually charge. Left out, the plan price (less any code) is used.
    # Supplied, it wins -- gyms negotiate, part-pay and round off, and a till
    # that can only charge list price sends that business off the books.
    amount = serializers.DecimalField(
        max_digits=8, decimal_places=2, min_value=Decimal("0"), required=False, allow_null=True
    )
    method = serializers.CharField(required=False)
    paid_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class DayPassSerializer(serializers.ModelSerializer):
    issued_by_name = serializers.CharField(source="issued_by.username", read_only=True)
    is_valid_today = serializers.BooleanField(read_only=True)
    # Derived from the visit rows rather than a flag on the pass, so a guest
    # who is checked out again reads correctly without anything being reset.
    visit_count = serializers.SerializerMethodField()
    checked_in = serializers.SerializerMethodField()

    class Meta:
        model = DayPass
        fields = [
            "id",
            "name",
            "phone",
            "email",
            "valid_on",
            "amount",
            "method",
            "notes",
            "issued_by",
            "issued_by_name",
            "is_valid_today",
            "visit_count",
            "checked_in",
            "created_at",
        ]
        read_only_fields = ["id", "issued_by", "created_at"]

    def get_visit_count(self, obj):
        return obj.visits.count()

    def get_checked_in(self, obj):
        return obj.visits.filter(check_out_time__isnull=True).exists()
