from django.contrib import admin

from .models import Availability, PTSession, Unavailable


@admin.register(Availability)
class AvailabilityAdmin(admin.ModelAdmin):
    list_display = ["trainer", "weekday", "start_time", "end_time", "is_active"]
    list_filter = ["weekday", "is_active"]


@admin.register(Unavailable)
class UnavailableAdmin(admin.ModelAdmin):
    list_display = ["trainer", "date", "reason"]


@admin.register(PTSession)
class PTSessionAdmin(admin.ModelAdmin):
    list_display = ["date", "start_time", "trainer", "member", "status", "price", "is_paid"]
    list_filter = ["status", "is_paid", "date"]
    date_hierarchy = "date"
