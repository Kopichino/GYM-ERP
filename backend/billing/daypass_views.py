"""Walk-ins at the front desk.

A day pass is sold and used in the same breath, so the endpoint that creates
one and the one that checks the guest in sit next to each other rather than in
the members' attendance API -- a guest has no account to authenticate with, and
the desk is always the one acting on their behalf.
"""

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from attendance.serializers import CheckInOutSerializer
from attendance.services import AttendanceError, toggle_guest_visit
from core.permissions import IsAdmin

from .models import DayPass
from .serializers import DayPassSerializer


class DayPassViewSet(ModelViewSet):
    """Issued and used at the desk, so admin-only throughout."""

    serializer_class = DayPassSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        queryset = DayPass.objects.select_related("issued_by").prefetch_related("visits")
        params = self.request.query_params
        on = params.get("on")
        if on:
            queryset = queryset.filter(valid_on=on)
        start, end = params.get("from"), params.get("to")
        if start:
            queryset = queryset.filter(valid_on__gte=start)
        if end:
            queryset = queryset.filter(valid_on__lte=end)
        return queryset

    def perform_create(self, serializer):
        serializer.save(issued_by=self.request.user)

    @action(detail=True, methods=["post"])
    def check_in(self, request, pk=None):
        """One tap in, the next tap out -- the same shape as every other way
        into the gym, and subject to its own one-open-visit index."""
        day_pass = self.get_object()
        if not day_pass.is_valid_today:
            return Response(
                {"detail": f"That pass is for {day_pass.valid_on}, not today."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            record, action_taken = toggle_guest_visit(day_pass)
        except AttendanceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"action": action_taken, "record": CheckInOutSerializer(record).data},
            status=status.HTTP_201_CREATED if action_taken == "in" else status.HTTP_200_OK,
        )
