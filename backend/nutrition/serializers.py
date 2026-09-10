from rest_framework import serializers

from . import macros
from .models import DietDay, DietMeal, DietMealItem, DietPlan, FoodItem


class FoodItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = FoodItem
        fields = [
            "id",
            "name",
            "category",
            "category_name",
            "calories",
            "protein_g",
            "carbs_g",
            "fat_g",
            "serving_label",
            "serving_grams",
            "is_active",
        ]
        read_only_fields = ["id"]


class MacroField(serializers.Serializer):
    """The four numbers every level of a plan reports, all derived."""

    calories = serializers.DecimalField(max_digits=9, decimal_places=1)
    protein_g = serializers.DecimalField(max_digits=9, decimal_places=1)
    carbs_g = serializers.DecimalField(max_digits=9, decimal_places=1)
    fat_g = serializers.DecimalField(max_digits=9, decimal_places=1)


class DietMealItemSerializer(serializers.ModelSerializer):
    food_name = serializers.CharField(source="food.name", read_only=True)
    serving_label = serializers.CharField(source="food.serving_label", read_only=True)
    serving_grams = serializers.DecimalField(
        source="food.serving_grams", max_digits=6, decimal_places=2, read_only=True
    )
    # Worked out from the grams and the catalogue, never stored.
    macros = serializers.SerializerMethodField()

    class Meta:
        model = DietMealItem
        fields = [
            "id",
            "meal",
            "food",
            "food_name",
            "serving_label",
            "serving_grams",
            "quantity_g",
            "order",
            "macros",
        ]
        read_only_fields = ["id"]

    def get_macros(self, obj):
        return macros.for_portion(obj.food, obj.quantity_g)


class DietMealSerializer(serializers.ModelSerializer):
    items = DietMealItemSerializer(many=True, read_only=True)
    meal_type_name = serializers.CharField(source="get_meal_type_display", read_only=True)
    macros = serializers.SerializerMethodField()

    class Meta:
        model = DietMeal
        fields = ["id", "day", "meal_type", "meal_type_name", "order", "notes", "items", "macros"]
        read_only_fields = ["id"]

    def get_macros(self, obj):
        return macros.for_meal(obj)


class DietDaySerializer(serializers.ModelSerializer):
    meals = DietMealSerializer(many=True, read_only=True)
    weekday_name = serializers.CharField(source="get_weekday_display", read_only=True)
    display_label = serializers.CharField(read_only=True)
    macros = serializers.SerializerMethodField()

    class Meta:
        model = DietDay
        fields = [
            "id",
            "plan",
            "weekday",
            "weekday_name",
            "label",
            "display_label",
            "notes",
            "meals",
            "macros",
        ]
        read_only_fields = ["id"]

    def get_macros(self, obj):
        return macros.for_day(obj)


class DietPlanSerializer(serializers.ModelSerializer):
    days = DietDaySerializer(many=True, read_only=True)
    days_planned = serializers.IntegerField(read_only=True)
    goal_name = serializers.CharField(source="get_goal_display", read_only=True)
    created_by_name = serializers.CharField(source="created_by.username", read_only=True)
    # The plan's daily average, so it sits next to `target_calories` honestly.
    daily_macros = serializers.SerializerMethodField()

    class Meta:
        model = DietPlan
        fields = [
            "id",
            "user",
            "name",
            "goal",
            "goal_name",
            "target_calories",
            "target_protein_g",
            "notes",
            "created_by",
            "created_by_name",
            "is_active",
            "days_planned",
            "daily_macros",
            "days",
            "created_at",
        ]
        # `is_active` follows the workout split: a new plan is always the
        # current one and switching back goes through the `activate` action, so
        # a form-encoded POST that omits the field can't silently file the new
        # plan away as inactive.
        read_only_fields = ["id", "user", "created_by", "is_active", "created_at"]

    def get_daily_macros(self, obj):
        return macros.for_plan(obj)


class TodayDietSerializer(serializers.Serializer):
    """What the check-in screen needs: is there a plan for today, and what's on it."""

    has_plan = serializers.BooleanField()
    weekday_name = serializers.CharField()
    is_planned_day = serializers.BooleanField()
    day = DietDaySerializer(allow_null=True)
