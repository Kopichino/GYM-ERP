from django.http import HttpResponse
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet

from core.permissions import IsAdmin

from .models import Message
from .serializers import MessageSerializer
from .services import handle_incoming, send
from .whatsapp import is_configured, parse_incoming, verify_signature, verify_subscription


class WhatsAppStatusView(APIView):
    """Whether the gym has WhatsApp connected. The admin page reads this rather
    than offering a tab that would fail on first use."""

    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({"enabled": is_configured()})


class MessageViewSet(ReadOnlyModelViewSet):
    """The conversation log. Read-only: messages are written by the webhook and
    by `send`, never by editing a row."""

    serializer_class = MessageSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        queryset = Message.objects.select_related("user")
        phone = self.request.query_params.get("phone")
        if phone:
            queryset = queryset.filter(phone__endswith="".join(c for c in phone if c.isdigit()))
        return queryset

    @action(detail=False, methods=["post"])
    def send(self, request):
        """Lets the front desk reply by hand from the admin portal."""
        phone = request.data.get("phone", "")
        body = (request.data.get("body") or "").strip()
        if not (phone and body):
            return Response({"detail": "A phone number and a message are required."}, status=400)
        message = send(phone, body)
        return Response(MessageSerializer(message).data, status=201)


class WhatsAppWebhookView(APIView):
    """Meta's endpoint. Unauthenticated by necessity, verified twice.

    GET is the one-time subscription handshake; POST is every delivery, each
    carrying an HMAC of the raw body. An unverifiable POST is refused rather
    than processed, since anyone could otherwise make the assistant talk.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        challenge = verify_subscription(
            request.query_params.get("hub.mode"),
            request.query_params.get("hub.verify_token"),
            request.query_params.get("hub.challenge", ""),
        )
        if challenge is None:
            return HttpResponse("Verification failed.", status=403)
        # Meta expects the raw challenge back, not JSON.
        return HttpResponse(challenge, content_type="text/plain")

    def post(self, request):
        if not verify_signature(request.body, request.headers.get("X-Hub-Signature-256", "")):
            return Response({"detail": "Bad signature."}, status=400)

        handled = 0
        for phone, text, external_id in parse_incoming(request.data or {}):
            if handle_incoming(phone, text, external_id) is not None:
                handled += 1
        # Always 200: a non-200 makes Meta retry, and there is nothing here
        # worth retrying once the body has been read.
        return Response({"handled": handled})
