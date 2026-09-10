from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import MemberProfile, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Role", {"fields": ("role",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Role", {"fields": ("role",)}),)
    list_display = ["username", "email", "first_name", "last_name", "role", "is_active"]
    list_filter = ["role", "is_active"]


@admin.register(MemberProfile)
class MemberProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "membership_status", "trainer", "join_date", "phone"]
    list_filter = ["membership_status"]
    search_fields = ["user__username", "user__email", "phone"]
