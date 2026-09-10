from django.contrib import admin

from .models import Shift


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ["staff", "date", "start_time", "end_time", "position"]
    list_filter = ["position", "date"]
    date_hierarchy = "date"
