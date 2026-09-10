from django.contrib import admin

from .models import Enquiry, RetentionPolicy


@admin.register(Enquiry)
class EnquiryAdmin(admin.ModelAdmin):
    list_display = ["name", "phone", "follow_up_on", "status", "last_contacted_on"]
    list_filter = ["status", "follow_up_on"]
    search_fields = ["name", "phone", "notes"]
    date_hierarchy = "follow_up_on"


@admin.register(RetentionPolicy)
class RetentionPolicyAdmin(admin.ModelAdmin):
    list_display = ["quiet_days", "cooling_days", "grace_days", "is_active", "updated_at"]
