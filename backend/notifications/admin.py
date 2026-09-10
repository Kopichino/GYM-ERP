from django.contrib import admin

from .models import NotificationLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ["to_email", "kind", "subject_date", "sent_at"]
    list_filter = ["kind"]
    search_fields = ["to_email", "subject"]
    readonly_fields = [f.name for f in NotificationLog._meta.fields]
