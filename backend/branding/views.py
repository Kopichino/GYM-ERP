from django.conf import settings
from django.db import transaction
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from core.permissions import IsAdmin

from .models import Branding
from .serializers import BrandingSerializer


class PublicBrandingView(APIView):
    """Who this gym is, for anyone at all.

    Unauthenticated on purpose: the login screen has to be branded before there
    is a session to read it with, and none of this is private -- it is the name
    on the door.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    # Its own bucket. Every page load asks for this, signed in or not; on the
    # shared anonymous bucket it used up the allowance sign-in refreshes needed.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public"

    def get(self, request):
        branding = Branding.current()
        if branding is None:
            # A fresh install still has to render as something, so the
            # environment supplies the fallback identity.
            return Response(
                {
                    "name": getattr(settings, "GYM_NAME", "IRONCORE"),
                    "tagline": "",
                    "logo": None,
                    "accent": "#ff3d5a",
                    "accent_2": "#ffb020",
                    "display_font": "Bebas Neue",
                    "phone": "",
                    "email": "",
                    "address": "",
                    "website": "",
                    "instagram": "",
                    "opening_hours": "",
                    "configured": False,
                }
            )
        data = BrandingSerializer(branding, context={"request": request}).data
        # The tax fields are for invoices, not for the browser.
        for private in ("gstin", "state"):
            data.pop(private, None)
        return Response({**data, "configured": True})


class BrandingViewSet(ModelViewSet):
    """Admin editing. Creating a new identity retires the previous one, so
    "who is this gym?" keeps a single answer."""

    serializer_class = BrandingSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        # Built per request, not at import: the scoped manager needs a
        # tenant in scope and a class attribute is evaluated on load.
        return Branding.objects.all()

    def perform_create(self, serializer):
        with transaction.atomic():
            Branding.objects.filter(is_active=True).update(is_active=False)
            serializer.save(is_active=True)
