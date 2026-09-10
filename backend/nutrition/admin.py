from django.contrib import admin

from .models import DietDay, DietMeal, DietMealItem, DietPlan, FoodItem


@admin.register(FoodItem)
class FoodItemAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "calories", "protein_g", "carbs_g", "fat_g", "is_active"]
    list_filter = ["category", "is_active"]
    search_fields = ["name"]


class DietMealItemInline(admin.TabularInline):
    model = DietMealItem
    extra = 0


@admin.register(DietMeal)
class DietMealAdmin(admin.ModelAdmin):
    list_display = ["day", "meal_type", "order"]
    inlines = [DietMealItemInline]


class DietDayInline(admin.TabularInline):
    model = DietDay
    extra = 0


@admin.register(DietPlan)
class DietPlanAdmin(admin.ModelAdmin):
    list_display = ["user", "name", "goal", "is_active", "updated_at"]
    list_filter = ["goal", "is_active"]
    inlines = [DietDayInline]
