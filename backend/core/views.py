from django.db import connection
from django.db.models import ProtectedError
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle


class RefuseProtectedDeleteMixin:
    """Answer a delete that a PROTECT foreign key blocks with a 400, not a 500.

    The model already refuses -- that is what PROTECT is for -- but the
    ProtectedError escaped the view uncaught. Caught around the delete rather
    than checked beforehand, so every protected reference the model has is
    covered, not just the ones a view remembers to list. Django raises it while
    collecting, before any row is deleted, so there is nothing to roll back.

    The message is fixed text per view: the exception's own wording names
    models and rows, which is not for the client.
    """

    protected_delete_message = "This is still in use, so it can't be deleted."

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise ValidationError({"detail": self.protected_delete_message})


@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([AnonRateThrottle])
def health_check(request):
    """Cheap endpoint the frontend can hit to detect/wait out a Render
    free-tier cold start ("waking up the server...") before showing real UI."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return Response({"status": "ok"})
