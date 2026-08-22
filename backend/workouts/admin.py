from django.contrib import admin

from .models import Exercise, WorkoutLog, WorkoutSession


class WorkoutLogInline(admin.TabularInline):
    model = WorkoutLog
    extra = 1


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "muscle_group"]
    search_fields = ["name"]


@admin.register(WorkoutSession)
class WorkoutSessionAdmin(admin.ModelAdmin):
    list_display = ["user", "date"]
    inlines = [WorkoutLogInline]
