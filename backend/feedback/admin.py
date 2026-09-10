from django.contrib import admin

from .models import Survey, SurveyResponse


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    list_display = ["title", "trigger", "cooldown_days", "is_active"]
    list_filter = ["trigger", "is_active"]


@admin.register(SurveyResponse)
class SurveyResponseAdmin(admin.ModelAdmin):
    list_display = ["member", "survey", "score", "created_at"]
    list_filter = ["survey", "score"]
    search_fields = ["member__username", "comment"]
