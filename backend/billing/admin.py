from django.contrib import admin

from .models import Payment, Plan


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ["name", "price", "duration_days", "is_active"]
    list_filter = ["is_active"]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["member", "plan", "amount", "method", "status", "paid_date", "period_end"]
    list_filter = ["status", "method", "plan"]
    search_fields = ["member__username", "member__email"]
    date_hierarchy = "paid_date"
