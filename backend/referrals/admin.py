from django.contrib import admin

from .models import Referral, ReferralProgram, ReferralReward


@admin.register(ReferralProgram)
class ReferralProgramAdmin(admin.ModelAdmin):
    list_display = ["reward_days", "blurb", "is_active", "updated_at"]


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ["referrer", "name", "phone", "referred_user", "created_at"]
    search_fields = ["name", "phone", "referrer__username"]


@admin.register(ReferralReward)
class ReferralRewardAdmin(admin.ModelAdmin):
    list_display = ["referral", "days_granted", "granted_on", "granted_by"]
