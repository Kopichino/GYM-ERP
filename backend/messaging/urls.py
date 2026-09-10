from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import MessageViewSet, WhatsAppStatusView, WhatsAppWebhookView

router = DefaultRouter()
router.register("messages", MessageViewSet, basename="message")

urlpatterns = [
    path("status/", WhatsAppStatusView.as_view(), name="whatsapp-status"),
    path("webhook/", WhatsAppWebhookView.as_view(), name="whatsapp-webhook"),
] + router.urls
