from django.contrib import admin

from .models import BodyMeasurement, MemberGoal


@admin.register(BodyMeasurement)
class BodyMeasurementAdmin(admin.ModelAdmin):
    list_display = ["user", "recorded_on", "weight_kg", "body_fat_pct", "recorded_by"]
    list_filter = ["recorded_on"]
    search_fields = ["user__username", "user__email"]
    date_hierarchy = "recorded_on"


@admin.register(MemberGoal)
class MemberGoalAdmin(admin.ModelAdmin):
    list_display = ["user", "goal_type", "target_value", "target_date", "status"]
    list_filter = ["goal_type", "status"]
    search_fields = ["user__username", "user__email", "title"]
