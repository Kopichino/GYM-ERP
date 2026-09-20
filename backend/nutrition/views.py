from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from accounts.models import User
from core.permissions import access, IsPlatformStaffOrReadOnly, IsTenantMember
from core.views import RefuseProtectedDeleteMixin
from core.scoping import may_write_for
from tenancy.people import people_here_or_404
from workouts.models import Weekday

from .models import DietDay, DietMeal, DietMealItem, DietPlan, FoodItem
from .serializers import (
    DietDaySerializer,
    DietMealItemSerializer,
    DietMealSerializer,
    DietPlanSerializer,
    FoodItemSerializer,
    TodayDietSerializer,
)


class FoodItemViewSet(RefuseProtectedDeleteMixin, ModelViewSet):
    """The shared catalogue: one list for every gym on the platform. Anyone
    who belongs to the gym can read it while building a plan; only platform
    staff edit it, because a food's macros feed every gym's plans at once --
    neither a member's typo nor one gym's admin should be able to skew them.

    Unpaginated, like the exercise catalogue: the food picker offers the whole
    list, and a default page of 20 silently hid most of it -- a member looking
    for paneer simply couldn't find it.
    """

    serializer_class = FoodItemSerializer
    permission_classes = [IsPlatformStaffOrReadOnly]
    pagination_class = None
    protected_delete_message = (
        "This food is used in a diet plan, so it can't be deleted. Deactivate it instead."
    )

    def get_queryset(self):
        queryset = FoodItem.objects.all()
        if not access(self.request).is_admin:
            queryset = queryset.filter(is_active=True)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search)
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category=category)
        return queryset


class _OwnedPlanMixin:
    """Diet plans belong to a member. Without `?member=` you act on your own;
    with it, a trainer or admin may work on one of their people's -- the same
    rule the workout split uses."""

    # Standing at the gym in the URL, not just a signed-in account: without it a
    # person from another gym could read this gym's (empty) list for them and
    # file new rows under a gym they do not belong to.
    permission_classes = [IsTenantMember]

    def _target_member(self):
        member_id = self.request.query_params.get("member")
        if not member_id or str(member_id) == str(self.request.user.id):
            return self.request.user
        member = people_here_or_404(member_id)
        if not may_write_for(access(self.request), member):
            raise PermissionDenied("Not one of your members.")
        return member


PLAN_PREFETCH = ("days__meals__items__food",)


class DietPlanViewSet(_OwnedPlanMixin, ModelViewSet):
    serializer_class = DietPlanSerializer

    def get_queryset(self):
        return DietPlan.objects.filter(user=self._target_member()).prefetch_related(*PLAN_PREFETCH)

    def _make_current(self, plan):
        """Exactly one plan is current, enforced by a partial unique index --
        so the previous one is retired in the same transaction."""
        with transaction.atomic():
            DietPlan.objects.filter(user=plan.user, is_active=True).exclude(pk=plan.pk).update(
                is_active=False
            )
            if not plan.is_active:
                plan.is_active = True
                plan.save(update_fields=["is_active", "updated_at"])
        return plan

    def perform_create(self, serializer):
        member = self._target_member()
        with transaction.atomic():
            DietPlan.objects.filter(user=member, is_active=True).update(is_active=False)
            # `created_by` records who wrote it -- a trainer's plan reads
            # differently to one the member typed themselves.
            serializer.save(user=member, created_by=self.request.user, is_active=True)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Switch back to an older plan."""
        return Response(DietPlanSerializer(self._make_current(self.get_object())).data)

    @action(detail=False, methods=["get"])
    def today(self, request):
        """Drives the "what am I eating today?" panel on the check-in screen."""
        member = self._target_member()
        weekday = timezone.localdate().weekday()
        plan = (
            DietPlan.objects.filter(user=member, is_active=True)
            .prefetch_related(*PLAN_PREFETCH)
            .first()
        )
        day = plan.days.filter(weekday=weekday).first() if plan else None
        return Response(
            TodayDietSerializer(
                {
                    "has_plan": plan is not None,
                    "weekday_name": Weekday(weekday).label,
                    "is_planned_day": day is not None,
                    "day": day,
                }
            ).data
        )


class DietDayViewSet(_OwnedPlanMixin, ModelViewSet):
    serializer_class = DietDaySerializer

    def get_queryset(self):
        return DietDay.objects.filter(
            plan__user=self._target_member()
        ).prefetch_related("meals__items__food")

    def _check_owns(self, plan):
        if plan.user != self._target_member():
            raise PermissionDenied("That diet plan isn't yours.")

    def perform_create(self, serializer):
        self._check_owns(serializer.validated_data["plan"])
        serializer.save()

    def perform_update(self, serializer):
        # The row as it stands is already this member's -- the queryset says so.
        # The parent named in the body has to be as well, or a PATCH moves the
        # row into somebody else's plan.
        self._check_owns(serializer.validated_data.get("plan", serializer.instance.plan))
        serializer.save()


class DietMealViewSet(_OwnedPlanMixin, ModelViewSet):
    serializer_class = DietMealSerializer

    def get_queryset(self):
        return DietMeal.objects.filter(
            day__plan__user=self._target_member()
        ).prefetch_related("items__food")

    def _check_owns(self, day):
        if day.plan.user != self._target_member():
            raise PermissionDenied("That diet plan isn't yours.")

    def perform_create(self, serializer):
        day = serializer.validated_data["day"]
        self._check_owns(day)
        # Append unless the client asked for a position.
        if not serializer.validated_data.get("order"):
            last = day.meals.order_by("-order").first()
            serializer.validated_data["order"] = (last.order + 1) if last else 1
        serializer.save()

    def perform_update(self, serializer):
        # The row as it stands is already this member's -- the queryset says so.
        # The parent named in the body has to be as well, or a PATCH moves the
        # row into somebody else's plan.
        self._check_owns(serializer.validated_data.get("day", serializer.instance.day))
        serializer.save()


class DietMealItemViewSet(_OwnedPlanMixin, ModelViewSet):
    serializer_class = DietMealItemSerializer

    def get_queryset(self):
        return DietMealItem.objects.filter(
            meal__day__plan__user=self._target_member()
        ).select_related("food", "meal")

    def _check_owns(self, meal):
        if meal.day.plan.user != self._target_member():
            raise PermissionDenied("That diet plan isn't yours.")

    def perform_create(self, serializer):
        meal = serializer.validated_data["meal"]
        self._check_owns(meal)
        if not serializer.validated_data.get("order"):
            last = meal.items.order_by("-order").first()
            serializer.validated_data["order"] = (last.order + 1) if last else 1
        serializer.save()

    def perform_update(self, serializer):
        # The row as it stands is already this member's -- the queryset says so.
        # The parent named in the body has to be as well, or a PATCH moves the
        # row into somebody else's plan.
        self._check_owns(serializer.validated_data.get("meal", serializer.instance.meal))
        serializer.save()
