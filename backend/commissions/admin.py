from django.contrib import admin

from .models import CommissionEntry, CommissionRule, Payout


@admin.register(CommissionRule)
class CommissionRuleAdmin(admin.ModelAdmin):
    list_display = ["__str__", "basis", "rate", "is_active"]
    list_filter = ["basis", "is_active"]


@admin.register(CommissionEntry)
class CommissionEntryAdmin(admin.ModelAdmin):
    list_display = ["trainer", "amount", "status", "earned_on"]
    list_filter = ["status", "earned_on"]


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ["trainer", "period_start", "period_end", "total", "paid_on"]
