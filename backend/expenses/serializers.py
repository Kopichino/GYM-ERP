from rest_framework import serializers

from core.uniqueness import Rule, SaveConflictsAsValidationErrors, UniqueInScope
from core.uploads import validate_receipt

from .models import Expense, ExpenseCategory


class ExpenseCategorySerializer(SaveConflictsAsValidationErrors, serializers.ModelSerializer):
    expense_count = serializers.SerializerMethodField()

    class Meta:
        model = ExpenseCategory
        fields = ["id", "name", "description", "is_active", "expense_count"]
        validators = [UniqueInScope(Rule("name", "A category with this name already exists."))]

    def get_expense_count(self, obj):
        return obj.expenses.count()


class ExpenseSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    recorded_by_name = serializers.CharField(source="recorded_by.username", read_only=True)
    # A bare FileField accepts anything at any size -- unlike the ImageFields
    # elsewhere, which Django verifies through Pillow on the way in.
    receipt = serializers.FileField(
        required=False, allow_null=True, validators=[validate_receipt]
    )

    class Meta:
        model = Expense
        fields = [
            "id",
            "category",
            "category_name",
            "amount",
            "spent_on",
            "vendor",
            "reference",
            "notes",
            "receipt",
            "recorded_by",
            "recorded_by_name",
            "created_at",
        ]
        read_only_fields = ["id", "recorded_by", "created_at"]
