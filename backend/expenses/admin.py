from django.contrib import admin

from .models import Expense, ExpenseCategory


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active"]


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ["spent_on", "category", "amount", "vendor", "recorded_by"]
    list_filter = ["category", "spent_on"]
    search_fields = ["vendor", "reference", "notes"]
    date_hierarchy = "spent_on"
