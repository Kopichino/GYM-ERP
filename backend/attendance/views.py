from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from core.permissions import IsAdmin, IsOwnerOrAdmin, access

from .models import CheckInMethod, CheckInOut
from .qr import WINDOW_SECONDS, current_token, is_valid
from .serializers import CheckInOutSerializer
from .services import (
    AttendanceError,
    close_visit,
    open_visit,
    streaks,
    toggle_visit,
    visit_dates,
)


class CheckInOutViewSet(ReadOnlyModelViewSet):
    """Read-only list/retrieve of a member's own check-in history, plus two
    action endpoints (check_in / check_out) that drive the self-service
    button on the dashboard. Admins can see everyone's history; trainers see
    their assigned members' plus their own."""

    serializer_class = CheckInOutSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]
    throttle_scope = "checkinout"

    def get_queryset(self):
        user = self.request.user
        here = access(self.request)
        if here.is_admin:
            return CheckInOut.objects.all()
        if here.is_trainer:
            return CheckInOut.objects.filter(
                Q(user=user) | Q(user__profile__trainer=user)
            )
        return CheckInOut.objects.filter(user=user)

    @action(detail=False, methods=["get"])
    def current(self, request):
        """The member's currently-open check-in, if any (drives the
        dashboard's live "checked in since ..." status). 204 (not a JSON
        `null` body) when there is none -- DRF's JSONRenderer emits an
        empty body for `Response(None)`, so 204 is the honest signal."""
        open_record = CheckInOut.objects.filter(user=request.user, check_out_time__isnull=True).first()
        if not open_record:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(self.get_serializer(open_record).data)

    @action(detail=False, methods=["post"])
    def check_in(self, request):
        try:
            record = open_visit(request.user, method=CheckInMethod.TAP)
        except AttendanceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(record).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def check_out(self, request):
        try:
            record = close_visit(request.user)
        except AttendanceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(record).data)

    @action(detail=False, methods=["get"], permission_classes=[IsAdmin])
    def qr_token(self, request):
        """The code the front-desk screen should be displaying right now.

        Admin-only: whoever can read this code can hand out check-ins, so it
        belongs to the kiosk, not to the members scanning it.
        """
        token, expires_at = current_token()
        return Response(
            {
                "token": token,
                "expires_at": expires_at,
                "rotate_seconds": WINDOW_SECONDS,
            }
        )

    @action(detail=False, methods=["post"], url_path="qr-scan")
    def qr_scan(self, request):
        """What a member's phone posts after scanning the kiosk code.

        One scan in, the next scan out -- the member's open visit decides which,
        exactly as a turnstile does, so there is no way to end up with two open
        check-ins.
        """
        if not is_valid(request.data.get("token", "")):
            return Response(
                {"detail": "That code has expired. Scan the screen again."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            record, action_taken = toggle_visit(request.user, method=CheckInMethod.QR)
        except AttendanceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"action": action_taken, "record": self.get_serializer(record).data},
            status=status.HTTP_201_CREATED if action_taken == "in" else status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"])
    def calendar(self, request):
        """All-time visit dates (deduped, local calendar day) plus streak
        stats, for the consistency calendar. Deliberately unpaginated --
        a heatmap/streak needs the full history, not just the latest page
        of check-ins."""
        # The streak maths lives in services so the badge criteria measure the
        # same thing this calendar shows.
        dates = visit_dates(request.user)
        current_streak, longest_streak = streaks(request.user, dates)

        return Response(
            {
                "dates": [d.isoformat() for d in dates],
                "total_visits": len(dates),
                "current_streak": current_streak,
                "longest_streak": longest_streak,
            }
        )
