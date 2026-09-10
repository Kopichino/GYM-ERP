from rest_framework import serializers

from .models import CommissionEntry, CommissionRule, Payout


class CommissionRuleSerializer(serializers.ModelSerializer):
    trainer_name = serializers.CharField(source="trainer.username", read_only=True, default=None)
    plan_name = serializers.CharField(source="plan.name", read_only=True, default=None)
    label = serializers.SerializerMethodField()

    class Meta:
        model = CommissionRule
        fields = [
            "id",
            "trainer",
            "trainer_name",
            "plan",
            "plan_name",
            "basis",
            "rate",
            "is_active",
            "label",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_label(self, obj):
        return str(obj)


class CommissionEntrySerializer(serializers.ModelSerializer):
    trainer_name = serializers.CharField(source="trainer.username", read_only=True)
    member_name = serializers.CharField(source="payment.member.username", read_only=True)
    plan_name = serializers.CharField(source="payment.plan.name", read_only=True)
    payment_amount = serializers.DecimalField(
        source="payment.amount", max_digits=10, decimal_places=2, read_only=True
    )

    class Meta:
        model = CommissionEntry
        fields = [
            "id",
            "trainer",
            "trainer_name",
            "payment",
            "member_name",
            "plan_name",
            "payment_amount",
            "basis",
            "rate_applied",
            "amount",
            "status",
            "payout",
            "earned_on",
        ]
        read_only_fields = fields


class PayoutSerializer(serializers.ModelSerializer):
    trainer_name = serializers.CharField(source="trainer.username", read_only=True)
    entry_count = serializers.SerializerMethodField()

    class Meta:
        model = Payout
        fields = [
            "id",
            "trainer",
            "trainer_name",
            "period_start",
            "period_end",
            "total",
            "paid_on",
            "notes",
            "entry_count",
            "created_at",
        ]
        read_only_fields = ["id", "total", "created_at"]

    def get_entry_count(self, obj):
        return obj.entries.count()
