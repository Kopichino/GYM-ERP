from django.contrib import admin

from .models import Badge, GamificationProfile, MemberBadge, PersonalRecord


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ["name", "tier", "criterion", "threshold", "is_active"]
    list_filter = ["tier", "criterion", "is_active"]
    prepopulated_fields = {"code": ("name",)}


@admin.register(MemberBadge)
class MemberBadgeAdmin(admin.ModelAdmin):
    list_display = ["member", "badge", "awarded_on", "value_at_award"]
    list_filter = ["badge"]


@admin.register(PersonalRecord)
class PersonalRecordAdmin(admin.ModelAdmin):
    list_display = ["member", "exercise", "weight_kg", "bodyweight_kg", "achieved_on"]
    list_filter = ["exercise"]


@admin.register(GamificationProfile)
class GamificationProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "leaderboard_opt_in", "updated_at"]
    list_filter = ["leaderboard_opt_in"]
