from rest_framework import serializers

from .models import Invoice


class InvoiceSerializer(serializers.ModelSerializer):
    member_name = serializers.SerializerMethodField()
    plan_name = serializers.CharField(source="payment.plan.name", read_only=True)
    amount_paid = serializers.DecimalField(
        source="payment.amount", max_digits=10, decimal_places=2, read_only=True
    )
    is_interstate = serializers.BooleanField(read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "number",
            "financial_year",
            "sequence",
            "issued_on",
            "payment",
            "member_name",
            "plan_name",
            "amount_paid",
            "seller_gstin",
            "buyer_gstin",
            "place_of_supply",
            "taxable_value",
            "cgst",
            "sgst",
            "igst",
            "total",
            "tax_rate",
            "is_interstate",
        ]
        read_only_fields = fields

    def get_member_name(self, obj):
        member = obj.payment.member
        return member.get_full_name() or member.username
