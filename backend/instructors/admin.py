from django.contrib import admin

from .models import Instructor


@admin.register(Instructor)
class InstructorAdmin(admin.ModelAdmin):
    list_display = ["name", "specialty", "active"]
    list_filter = ["active"]
