from django.db.models import Max, Sum
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from core.permissions import IsAdminOrReadOnly, IsOwnerOrAdmin

from .models import Exercise, WorkoutLog, WorkoutSession
from .serializers import ExerciseSerializer, WorkoutLogSerializer, WorkoutSessionSerializer


class ExerciseViewSet(ModelViewSet):
    """Admin-managed catalog; members have read-only access to pick from
    when logging a workout. Unpaginated -- the workout logger dropdown and
    the muscle-group library both need the full catalog, not one page of it."""

    queryset = Exercise.objects.all()
    serializer_class = ExerciseSerializer
    permission_classes = [IsAdminOrReadOnly]
    pagination_class = None


class WorkoutSessionViewSet(ModelViewSet):
    serializer_class = WorkoutSessionSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]

    def get_queryset(self):
        user = self.request.user
        qs = WorkoutSession.objects.prefetch_related("logs__exercise")
        return qs if user.is_staff else qs.filter(user=user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=["get"])
    def progress(self, request):
        """Per-exercise progress over time for the current member: for each
        session, the heaviest set and total reps logged for that exercise --
        the data the frontend's Recharts trend line plots against."""
        exercise_id = request.query_params.get("exercise")
        if not exercise_id:
            return Response({"detail": "exercise query param is required."}, status=400)

        logs = (
            WorkoutLog.objects.filter(
                session__user=request.user, exercise_id=exercise_id
            )
            .values("session__date")
            .annotate(max_weight=Max("weight"), total_reps=Sum("reps"))
            .order_by("session__date")
        )
        return Response(list(logs))


class WorkoutLogViewSet(ModelViewSet):
    serializer_class = WorkoutLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = WorkoutLog.objects.select_related("exercise", "session")
        return qs if user.is_staff else qs.filter(session__user=user)

    def perform_create(self, serializer):
        session = serializer.validated_data["session"]
        if session.user != self.request.user and not self.request.user.is_staff:
            raise PermissionDenied("Cannot log to another member's session.")
        serializer.save()
