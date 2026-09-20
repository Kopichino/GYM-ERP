from django.contrib import admin

from .models import CommissionEntry, CommissionRule, Payout


class HistoryOnlyAdmin(admin.ModelAdmin):
    """Commission was removed. What was recorded stays readable, and nothing more:
    no new rules, no edits to past earnings, and no payouts from here."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CommissionRule)
class CommissionRuleAdmin(HistoryOnlyAdmin):
    list_display = ["__str__", "basis", "rate", "is_active"]
    list_filter = ["basis", "is_active"]


@admin.register(CommissionEntry)
class CommissionEntryAdmin(HistoryOnlyAdmin):
    list_display = ["trainer", "amount", "status", "earned_on"]
    list_filter = ["status", "earned_on"]


@admin.register(Payout)
class PayoutAdmin(HistoryOnlyAdmin):
    list_display = ["trainer", "period_start", "period_end", "total", "paid_on"]
