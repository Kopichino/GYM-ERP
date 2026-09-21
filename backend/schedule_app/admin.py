from django.contrib import admin

from .models import ClassSession


@admin.register(ClassSession)
class ClassSessionAdmin(admin.ModelAdmin):
    list_display = ["title", "trainer", "date", "start_time", "end_time"]
    list_filter = ["date"]
