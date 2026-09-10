from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from accounts.models import User
from core.permissions import access
from core.scoping import may_write_for, visible_rows

from .models import BodyMeasurement, MemberGoal
from .serializers import BodyMeasurementSerializer, MemberGoalSerializer
from .services import refresh_goal_status, summary_for


class _MemberScopedViewSet(ModelViewSet):
    """Rows belong to a member. Without `?member=` you get your own; with it you
    get that member's, but only if you're their trainer or an admin."""

    permission_classes = [IsAuthenticated]
    model = None

    def _target_member(self):
        member_id = self.request.query_params.get("member") or self.request.data.get("user")
        if not member_id or str(member_id) == str(self.request.user.id):
            return self.request.user
        member = get_object_or_404(User, pk=member_id)
        if not may_write_for(access(self.request), member):
            raise PermissionDenied("Not one of your members.")
        return member

    def get_queryset(self):
        queryset = self.model.objects.select_related("user__profile")
        member_id = self.request.query_params.get("member")
        if member_id:
            return queryset.filter(visible_rows(access(self.request)), user_id=member_id)
        return queryset.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self._target_member())


class BodyMeasurementViewSet(_MemberScopedViewSet):
    serializer_class = BodyMeasurementSerializer
    model = BodyMeasurement

    def perform_create(self, serializer):
        member = self._target_member()
        recorded_on = serializer.validated_data.get("recorded_on")
        # One weigh-in per day is a database constraint, so a same-day re-entry
        # has to update rather than insert or it would 500 on the unique index.
        existing = BodyMeasurement.objects.filter(user=member, recorded_on=recorded_on).first()
        if existing:
            serializer.instance = existing
        serializer.save(
            user=member,
            recorded_by=self.request.user if self.request.user != member else None,
        )
        # A new weigh-in can complete a weight or body-fat goal.
        for goal in MemberGoal.objects.filter(user=member):
            refresh_goal_status(goal)


class MemberGoalViewSet(_MemberScopedViewSet):
    serializer_class = MemberGoalSerializer
    model = MemberGoal

    def perform_create(self, serializer):
        member = self._target_member()
        goal = serializer.save(user=member)
        refresh_goal_status(goal)

    def perform_update(self, serializer):
        refresh_goal_status(serializer.save())


class BodyStatsSummaryView(APIView):
    """Latest weight, height, BMI and its band, plus movement since the last
    weigh-in and since the very first one."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        member_id = request.query_params.get("member")
        member = request.user
        if member_id and str(member_id) != str(request.user.id):
            member = get_object_or_404(User, pk=member_id)
            if not may_write_for(access(request), member):
                raise PermissionDenied("Not one of your members.")
        return Response(summary_for(member))
