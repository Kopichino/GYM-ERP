from django.db import IntegrityError
from rest_framework import status as http
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from core.dates import read_window
from core.permissions import access, IsAdmin, IsTenantMember

from . import nps
from .models import DETRACTOR_TO, Survey, SurveyResponse, Trigger
from .serializers import (
    PendingPromptSerializer,
    SurveyResponseSerializer,
    SurveySerializer,
)


class SurveyViewSet(ModelViewSet):
    """The questions. Owners write them; members only ever read their own
    pending prompt through the action below."""


    def get_queryset(self):
        # Built per request, not at import: the scoped manager needs a
        # tenant in scope and a class attribute is evaluated on load.
        return Survey.objects.all()
    serializer_class = SurveySerializer
    permission_classes = [IsAdmin]

    def get_permissions(self):
        if self.action == "pending":
            return [IsAuthenticated()]
        return super().get_permissions()

    def _clash(self, form, instance=None):
        """Turn the one-active-per-trigger index into a sentence.

        Falls back to the instance's trigger and then the model default, so a
        payload that simply omits `trigger` is still checked -- otherwise the
        second manual survey would slip past this and reach the database as a
        500.
        """
        data = form.validated_data
        trigger = data.get("trigger")
        if trigger is None:
            trigger = getattr(instance, "trigger", None) or Trigger.MANUAL
        if not data.get("is_active", True):
            return None

        existing = Survey.objects.filter(is_active=True, trigger=trigger)
        if instance is not None:
            existing = existing.exclude(pk=instance.pk)
        existing = existing.first()
        if existing is None:
            return None
        return Response(
            {
                "detail": (
                    f'"{existing.title}" is already the live survey for '
                    f"{Trigger(trigger).label.lower()}. Switch that one off first."
                )
            },
            status=http.HTTP_400_BAD_REQUEST,
        )

    def create(self, request, *args, **kwargs):
        form = self.get_serializer(data=request.data)
        form.is_valid(raise_exception=True)
        clash = self._clash(form)
        if clash:
            return clash
        form.save()
        return Response(form.data, status=http.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        form = self.get_serializer(
            instance, data=request.data, partial=kwargs.pop("partial", False)
        )
        form.is_valid(raise_exception=True)
        clash = self._clash(form, instance)
        if clash:
            return clash
        form.save()
        return Response(form.data)

    @action(detail=False, methods=["get"])
    def pending(self, request):
        """What this member is being asked right now -- usually nothing."""
        prompts = nps.pending(request.user)
        return Response(PendingPromptSerializer(prompts, many=True).data)


class SurveyResponseViewSet(ModelViewSet):
    """Answers. A member writes their own and reads their own; an owner reads
    everyone's and writes none."""

    serializer_class = SurveyResponseSerializer
    # Standing at the gym in the URL, not just a signed-in account: without it a
    # person from another gym could read this gym's (empty) list for them and
    # file new rows under a gym they do not belong to.
    permission_classes = [IsTenantMember]
    # No PATCH or DELETE: an answer that can be edited afterwards is not a
    # measurement of anything.
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = SurveyResponse.objects.select_related("member", "survey")
        if not access(self.request).is_admin:
            queryset = queryset.filter(member=self.request.user)
        params = self.request.query_params
        if params.get("survey"):
            queryset = queryset.filter(survey=params["survey"])
        if params.get("band") == "detractor":
            queryset = queryset.filter(score__lte=DETRACTOR_TO)
        return queryset

    def perform_create(self, serializer):
        # Always the signed-in member, never whoever the payload names -- an
        # answer attributed to someone else is worse than a missing one.
        serializer.save(member=self.request.user)

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except IntegrityError:
            # The one-response-per-occasion index, reached by a double-tapped
            # Send. Not a failure worth showing the member as one.
            return Response(
                {"detail": "You have already answered this one — thanks!"},
                status=http.HTTP_409_CONFLICT,
            )


class NpsView(APIView):
    """The owner's read: score, bands, trend, and what detractors said."""

    permission_classes = [IsAdmin]

    def get(self, request):
        # A malformed date is a 400 on its parameter and a `to` before `from`
        # is refused -- the way every report reads its window -- rather than
        # a 500 or an empty summary.
        start, end = read_window(request.query_params)
        survey = request.query_params.get("survey") or None
        result = nps.summary(start, end, survey)
        result["trend"] = nps.trend(6, survey)
        return Response(result)
