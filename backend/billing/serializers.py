from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

from accounts.models import User
from core.uniqueness import Rule, SaveConflictsAsValidationErrors, UniqueInScope

from .models import DayPass, Discount, Payment, PaymentMethod, Plan
from .services import get_latest_completed_payment


class PlanSerializer(SaveConflictsAsValidationErrors, serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ["id", "name", "price", "duration_days", "description", "is_active"]
        validators = [UniqueInScope(Rule("name", "A plan with this name already exists."))]


class PublicPlanSerializer(serializers.ModelSerializer):
    """What the public website's price list shows, and nothing more."""

    class Meta:
        model = Plan
        fields = ["id", "name", "price", "duration_days", "description"]
        read_only_fields = fields


def invoice_summary(payment):
    """The invoice issued for `payment` as a ledger row shows it, or None.

    Carried on the payment itself so every page of the ledger is complete on its
    own. The Billing pages used to fetch invoices as a separate list and match
    them up by id -- which only worked while both lists fitted on one page.
    """
    try:
        invoice = payment.invoice
    except ObjectDoesNotExist:
        return None
    return {"id": invoice.pk, "number": invoice.number}


class AdminPaymentSerializer(serializers.ModelSerializer):
    """Used by the admin "record payment" form and the payments ledger."""

    plan_name = serializers.CharField(source="plan.name", read_only=True)
    member_username = serializers.CharField(source="member.username", read_only=True)
    discount_code = serializers.CharField(source="discount.code", read_only=True, default=None)
    gross_amount = serializers.SerializerMethodField()
    invoice = serializers.SerializerMethodField()

    def get_gross_amount(self, obj):
        """What it would have cost without the offer -- derived, not stored."""
        return str(obj.amount + obj.discount_amount)

    def get_invoice(self, obj):
        return invoice_summary(obj)

    def validate_member(self, member):
        """A payment may only be recorded against a member of this gym.

        `member` is a plain id from the form and `User` spans every gym, so
        without this an admin could file a payment against somebody they have
        no standing over -- and the ledger row would land in this gym's books.
        """
        from tenancy.people import people_here

        if not people_here().filter(pk=member.pk).exists():
            raise serializers.ValidationError("That person is not a member of this gym.")
        return member

    def validate_plan(self, plan):
        """A new payment, or one moved to a different plan, needs a plan on sale.

        A payment that stays on the plan it was recorded against can still be
        corrected after that plan is retired -- that is history, not a sale.
        """
        from .services import NOT_ON_SALE, is_sellable

        unchanged = self.instance is not None and self.instance.plan_id == plan.pk
        if not unchanged and not is_sellable(plan):
            raise serializers.ValidationError(NOT_ON_SALE)
        return plan

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
            "invoice",
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
    invoice = serializers.SerializerMethodField()

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
            "invoice",
        ]
        read_only_fields = fields

    def get_invoice(self, obj):
        return invoice_summary(obj)


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


class DiscountSerializer(SaveConflictsAsValidationErrors, serializers.ModelSerializer):
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
        # Codes are stored upper-cased and matched at the till ignoring case, so
        # "save10" is the same code as "SAVE10" -- compare what will be stored.
        validators = [
            UniqueInScope(
                Rule(
                    "code",
                    "An offer with this code already exists.",
                    normalise={"code": lambda code: code.strip().upper()},
                )
            )
        ]

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
    # One of the known methods. Free text here reached the ledger and the
    # exports as whatever the browser sent.
    method = serializers.ChoiceField(choices=PaymentMethod.choices, required=False)
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
