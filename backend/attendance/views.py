from django.db import IntegrityError
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from core.permissions import IsOwnerOrAdmin

from .models import CheckInOut
from .serializers import CheckInOutSerializer


class CheckInOutViewSet(ReadOnlyModelViewSet):
    """Read-only list/retrieve of a member's own check-in history, plus two
    action endpoints (check_in / check_out) that drive the self-service
    button on the dashboard. Staff can see everyone's history."""

    serializer_class = CheckInOutSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]
    throttle_scope = "checkinout"

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return CheckInOut.objects.all()
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
        if CheckInOut.objects.filter(user=request.user, check_out_time__isnull=True).exists():
            return Response(
                {"detail": "Already checked in."}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            record = CheckInOut.objects.create(user=request.user)
        except IntegrityError:
            # Two rapid taps raced past the check above; the DB-level
            # constraint is the real source of truth here.
            return Response(
                {"detail": "Already checked in."}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(self.get_serializer(record).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def check_out(self, request):
        record = CheckInOut.objects.filter(user=request.user, check_out_time__isnull=True).first()
        if not record:
            return Response(
                {"detail": "No open check-in to close."}, status=status.HTTP_400_BAD_REQUEST
            )
        record.check_out_time = timezone.now()
        record.save(update_fields=["check_out_time"])
        return Response(self.get_serializer(record).data)

    @action(detail=False, methods=["get"])
    def calendar(self, request):
        """All-time visit dates (deduped, local calendar day) plus streak
        stats, for the consistency calendar. Deliberately unpaginated --
        a heatmap/streak needs the full history, not just the latest page
        of check-ins."""
        check_in_times = CheckInOut.objects.filter(user=request.user).values_list(
            "check_in_time", flat=True
        )
        dates = sorted({timezone.localtime(t).date() for t in check_in_times})

        current_streak = 0
        longest_streak = 0
        if dates:
            run = 1
            longest_streak = 1
            for previous_date, current_date in zip(dates, dates[1:]):
                run = run + 1 if (current_date - previous_date).days == 1 else 1
                longest_streak = max(longest_streak, run)

            gap_from_today = (timezone.localtime().date() - dates[-1]).days
            current_streak = run if gap_from_today <= 1 else 0

        return Response(
            {
                "dates": [d.isoformat() for d in dates],
                "total_visits": len(dates),
                "current_streak": current_streak,
                "longest_streak": longest_streak,
            }
        )
