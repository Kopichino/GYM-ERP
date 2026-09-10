from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from core.permissions import IsAdminOrReadOnly

from .models import Shift
from .serializers import PositionSerializer, ShiftSerializer
from .services import ShiftError, save_shift


class ShiftViewSet(ModelViewSet):
    """The staff rota.

    Readable by anyone signed in -- a trainer needs to know who else is on, and
    a member asking "is anyone on the floor?" is a fair question. Only an admin
    writes it.
    """

    serializer_class = ShiftSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        queryset = Shift.objects.select_related("staff")
        params = self.request.query_params
        # A rota is read a week at a time; without a window this returns the
        # whole history the moment the gym has been open a year.
        start = params.get("from")
        end = params.get("to")
        if start:
            queryset = queryset.filter(date__gte=start)
        if end:
            queryset = queryset.filter(date__lte=end)
        staff = params.get("staff")
        if staff:
            queryset = queryset.filter(staff_id=staff)
        position = params.get("position")
        if position:
            queryset = queryset.filter(position=position)
        return queryset

    def _save(self, serializer, instance=None):
        data = serializer.validated_data
        try:
            return save_shift(
                staff=data["staff"],
                date=data["date"],
                start_time=data["start_time"],
                end_time=data["end_time"],
                position=data.get("position", "floor"),
                notes=data.get("notes", ""),
                created_by=self.request.user,
                instance=instance,
            )
        except ShiftError as exc:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"detail": str(exc)})

    def perform_create(self, serializer):
        serializer.instance = self._save(serializer)

    def perform_update(self, serializer):
        serializer.instance = self._save(serializer, instance=serializer.instance)

    @action(detail=False, methods=["get"])
    def mine(self, request):
        """A staff member's own upcoming shifts."""
        today = timezone.localdate()
        rota = Shift.objects.filter(staff=request.user, date__gte=today).select_related("staff")
        return Response(ShiftSerializer(rota, many=True).data)

    @action(detail=False, methods=["get"])
    def on_floor(self, request):
        """Who is rostered at this moment -- derived from the rota, not a flag."""
        from .services import on_floor

        now = timezone.localtime()
        rota = on_floor(now)
        return Response(
            {
                "at": now,
                "count": rota.count(),
                "results": ShiftSerializer(rota, many=True).data,
            }
        )

    @action(detail=False, methods=["get"])
    def positions(self, request):
        return Response(PositionSerializer.all())
