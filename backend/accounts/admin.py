from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import MemberProfile, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets
    list_display = ["username", "email", "first_name", "last_name", "is_staff", "is_active"]


@admin.register(MemberProfile)
class MemberProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "membership_status", "join_date", "phone"]
    list_filter = ["membership_status"]
    search_fields = ["user__username", "user__email", "phone"]
