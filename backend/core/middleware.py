"""Request-level guards that have to run before a body is read."""

from django.conf import settings
from django.http import JsonResponse


class RequestSizeLimitMiddleware:
    """Refuse a request whose declared body is over the cap, with a 413.

    Before this a huge declared upload was answered only after authentication
    and parsing had begun. Refusing on the header costs nothing and never
    reads the body.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            declared = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            declared = 0
        if declared > settings.MAX_REQUEST_BYTES:
            return JsonResponse(
                {"detail": "That request is too large."},
                status=413,
            )
        return self.get_response(request)
