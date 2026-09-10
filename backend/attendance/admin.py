from django.contrib import admin

from .models import CheckInOut


@admin.register(CheckInOut)
class CheckInOutAdmin(admin.ModelAdmin):
    list_display = ["user", "check_in_time", "check_out_time"]
    list_filter = ["check_in_time"]
    search_fields = ["user__username", "user__email"]
