from django.contrib import admin

from .models import Message


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ["created_at", "direction", "phone", "user", "status", "is_automated"]
    list_filter = ["direction", "status", "is_automated"]
    search_fields = ["phone", "body"]
    readonly_fields = [f.name for f in Message._meta.fields]
