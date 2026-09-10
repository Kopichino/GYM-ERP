from django.db import transaction
from django.db.models import Max, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from accounts.models import User
from core.permissions import access, IsAdminOrReadOnly, IsOwnerOrAdmin
from core.scoping import may_write_for, visible_rows

from .models import (
    Exercise,
    SplitDay,
    SplitExercise,
    Weekday,
    WorkoutLog,
    WorkoutSession,
    WorkoutSplit,
)
from .serializers import (
    ExerciseSerializer,
    SplitDaySerializer,
    SplitExerciseSerializer,
    TodaySplitSerializer,
    WorkoutLogSerializer,
    WorkoutSessionSerializer,
    WorkoutSplitSerializer,
)


class ExerciseViewSet(ModelViewSet):
    """Admin-managed catalog; members have read-only access to pick from
    when logging a workout. Unpaginated -- the workout logger dropdown and
    the muscle-group library both need the full catalog, not one page of it."""


    def get_queryset(self):
        # Built per request, not at import: the scoped manager needs a
        # tenant in scope and a class attribute is evaluated on load.
        return Exercise.objects.all()
    serializer_class = ExerciseSerializer
    permission_classes = [IsAdminOrReadOnly]
    pagination_class = None


def _visible_to(caller):
    """Whose sessions `caller` may read -- see core.scoping.visible_rows.

    Takes an `Access` (what the caller is at this gym), not a `User`.
    """
    return visible_rows(caller)


class WorkoutSessionViewSet(ModelViewSet):
    serializer_class = WorkoutSessionSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]

    def get_queryset(self):
        qs = WorkoutSession.objects.prefetch_related("logs__exercise")
        member_id = self.request.query_params.get("member")
        if member_id:
            # Trainer/admin charting someone else; _visible_to gates who that
            # may be. Members get an empty set for anyone but themselves.
            return qs.filter(_visible_to(access(self.request)), user_id=member_id)
        # No ?member= always means "my own logger" -- including for staff, who
        # previously saw every member's sessions here while the progress
        # endpoint only ever returned their own, so the two screens disagreed.
        return qs.filter(user=self.request.user)

    def perform_create(self, serializer):
        # A trainer may open a session on behalf of an assigned member.
        member = serializer.validated_data.get("user") or self.request.user
        if member != self.request.user and not self._may_write_for(member):
            raise PermissionDenied("Cannot create a session for this member.")
        serializer.save(user=member)

    def _may_write_for(self, member):
        return may_write_for(access(self.request), member)

    @action(detail=False, methods=["get"])
    def progress(self, request):
        """Per-exercise progress over time: for each session, the heaviest set
        and total reps logged for that exercise -- the data the frontend's
        Recharts trend line plots against. Defaults to the caller's own logs;
        `?member=` lets a trainer/admin chart an assigned member instead."""
        exercise_id = request.query_params.get("exercise")
        if not exercise_id:
            return Response({"detail": "exercise query param is required."}, status=400)

        member_id = request.query_params.get("member")
        if member_id and str(member_id) != str(request.user.id):
            if not (access(request).is_admin or access(request).is_trainer):
                raise PermissionDenied("Cannot view another member's progress.")
            sessions = WorkoutSession.objects.filter(_visible_to(access(request)), user_id=member_id)
            if not sessions.exists() and not access(request).is_admin:
                raise PermissionDenied("Cannot view another member's progress.")
            log_filter = Q(session__user_id=member_id)
        else:
            log_filter = Q(session__user=request.user)

        rows = (
            WorkoutLog.objects.filter(log_filter, exercise_id=exercise_id)
            .values("session__date", "weight_unit")
            .annotate(max_weight=Max("weight"), total_reps=Sum("reps"))
            .order_by("session__date")
        )

        # Grouping by unit as well as date is what makes `weight_unit` available
        # to label the chart's axis. It also splits a day where someone logged
        # both kg and lb, so fold those back into one point per date, keeping the
        # unit of that day's heaviest set.
        by_date = {}
        for row in rows:
            point = by_date.get(row["session__date"])
            if point is None:
                by_date[row["session__date"]] = dict(row)
                continue
            point["total_reps"] += row["total_reps"]
            if row["max_weight"] > point["max_weight"]:
                point["max_weight"] = row["max_weight"]
                point["weight_unit"] = row["weight_unit"]

        return Response(sorted(by_date.values(), key=lambda p: p["session__date"]))


class WorkoutLogViewSet(ModelViewSet):
    serializer_class = WorkoutLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        here = access(self.request)
        qs = WorkoutLog.objects.select_related("exercise", "session")
        if here.is_admin:
            return qs
        if here.is_trainer:
            return qs.filter(
                Q(session__user=user) | Q(session__user__profile__trainer=user)
            )
        return qs.filter(session__user=user)

    def perform_create(self, serializer):
        session = serializer.validated_data["session"]
        user = self.request.user
        if not may_write_for(access(request), session.user):
            raise PermissionDenied("Cannot log to another member's session.")
        serializer.save()


class _OwnedSplitMixin:
    """Splits belong to a member. Without `?member=` you act on your own;
    with it, a trainer or admin may read one of their people's."""

    permission_classes = [IsAuthenticated]

    def _target_member(self):
        member_id = self.request.query_params.get("member")
        if not member_id or str(member_id) == str(self.request.user.id):
            return self.request.user
        member = get_object_or_404(User, pk=member_id)
        if not may_write_for(access(self.request), member):
            raise PermissionDenied("Not one of your members.")
        return member


class WorkoutSplitViewSet(_OwnedSplitMixin, ModelViewSet):
    serializer_class = WorkoutSplitSerializer

    def get_queryset(self):
        return (
            WorkoutSplit.objects.filter(user=self._target_member())
            .prefetch_related("days__exercises__exercise__videos")
        )

    def _make_current(self, split):
        """Exactly one plan is current, enforced by a partial unique index --
        so the previous one has to be retired in the same transaction."""
        with transaction.atomic():
            WorkoutSplit.objects.filter(user=split.user, is_active=True).exclude(
                pk=split.pk
            ).update(is_active=False)
            if not split.is_active:
                split.is_active = True
                split.save(update_fields=["is_active", "updated_at"])
        return split

    def perform_create(self, serializer):
        member = self._target_member()
        with transaction.atomic():
            WorkoutSplit.objects.filter(user=member, is_active=True).update(is_active=False)
            serializer.save(user=member, is_active=True)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Switch back to an older plan."""
        return Response(WorkoutSplitSerializer(self._make_current(self.get_object())).data)

    @action(detail=False, methods=["get"])
    def today(self, request):
        """Drives the "what am I training today?" line on the check-in screen."""
        member = self._target_member()
        weekday = timezone.localdate().weekday()
        split = WorkoutSplit.objects.filter(user=member, is_active=True).first()
        day = (
            split.days.filter(weekday=weekday)
            .prefetch_related("exercises__exercise__videos")
            .first()
            if split
            else None
        )
        return Response(
            TodaySplitSerializer(
                {
                    "is_training_day": day is not None,
                    "weekday_name": Weekday(weekday).label,
                    "has_split": split is not None,
                    "day": day,
                }
            ).data
        )


class SplitDayViewSet(_OwnedSplitMixin, ModelViewSet):
    serializer_class = SplitDaySerializer

    def get_queryset(self):
        return SplitDay.objects.filter(
            split__user=self._target_member()
        ).prefetch_related("exercises__exercise__videos")

    def _check_owns(self, split):
        if split.user != self._target_member():
            raise PermissionDenied("That split isn't yours.")

    def perform_create(self, serializer):
        self._check_owns(serializer.validated_data["split"])
        serializer.save()

    def perform_update(self, serializer):
        self._check_owns(serializer.instance.split)
        serializer.save()


class SplitExerciseViewSet(_OwnedSplitMixin, ModelViewSet):
    serializer_class = SplitExerciseSerializer

    def get_queryset(self):
        return SplitExercise.objects.filter(
            day__split__user=self._target_member()
        ).select_related("exercise", "day")

    def _check_owns(self, day):
        if day.split.user != self._target_member():
            raise PermissionDenied("That split isn't yours.")

    def perform_create(self, serializer):
        day = serializer.validated_data["day"]
        self._check_owns(day)
        # Append to the end unless the client asked for a position.
        if not serializer.validated_data.get("order"):
            last = day.exercises.order_by("-order").first()
            serializer.validated_data["order"] = (last.order + 1) if last else 1
        serializer.save()

    def perform_update(self, serializer):
        self._check_owns(serializer.instance.day)
        serializer.save()
