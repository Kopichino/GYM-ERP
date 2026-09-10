from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

from .models import Device, hash_key

HEADER = "HTTP_X_DEVICE_KEY"


class DeviceKeyAuthentication(BaseAuthentication):
    """Authenticates a terminal by its API key.

    Deliberately does not populate `request.user`: a device is not a person, and
    letting it masquerade as one would hand it every permission that member has.
    It is attached as `request.device` instead, and only the device endpoints
    accept it.
    """

    def authenticate(self, request):
        raw = request.META.get(HEADER)
        if not raw:
            return None

        device = Device.objects.filter(api_key_hash=hash_key(raw)).first()
        if device is None:
            raise AuthenticationFailed("Unknown device key.")
        if not device.is_active:
            raise AuthenticationFailed("This device has been deactivated.")

        device.last_seen_at = timezone.now()
        device.save(update_fields=["last_seen_at"])
        request.device = device
        # Returning None leaves the request anonymous; IsDevice below is what
        # actually authorises it.
        return None

    def authenticate_header(self, request):
        # Without this DRF turns every AuthenticationFailed into a 403, which
        # would tell a terminal with a bad key that it is forbidden rather than
        # unauthenticated -- and hide the fact that rotating the key fixes it.
        return "X-Device-Key"


class IsDevice(BasePermission):
    message = "A valid X-Device-Key header is required."

    def has_permission(self, request, view):
        return getattr(request, "device", None) is not None
