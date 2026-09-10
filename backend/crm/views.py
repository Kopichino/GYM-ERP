from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import serializers, status as http
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from core.permissions import IsAdmin, IsTrainerOrAdmin

from . import retention
from .models import Enquiry, EnquiryNote, EnquirySource, EnquiryStatus, RetentionPolicy
from .serializers import (
    AtRiskMemberSerializer,
    EnquiryNoteSerializer,
    EnquirySerializer,
    RetentionPolicySerializer,
)
from .services import ConversionError, convert, suggest_username


class EnquiryViewSet(ModelViewSet):
    """Front-desk enquiries and their callbacks. Admin-only -- these are
    prospects, not members, so no member-facing endpoint exposes them."""

    serializer_class = EnquirySerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        queryset = Enquiry.objects.select_related(
            "created_by", "assigned_to", "converted_user", "interested_in"
        ).prefetch_related("trail__author")
        params = self.request.query_params
        for field in ("status", "source"):
            value = params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})
        assigned = params.get("assigned_to")
        if assigned:
            queryset = queryset.filter(assigned_to_id=assigned)
        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=["get"])
    def due(self, request):
        """Everyone worth calling right now: today's callbacks plus anything
        already missed. This is what the reminder reads from."""
        today = timezone.localdate()
        due = self.get_queryset().filter(
            status=EnquiryStatus.OPEN, follow_up_on__lte=today
        )
        return Response(
            {
                "date": today,
                "count": due.count(),
                "overdue_count": due.filter(follow_up_on__lt=today).count(),
                "results": EnquirySerializer(due, many=True).data,
            }
        )

    @action(detail=False, methods=["get"])
    def pipeline(self, request):
        """Counts by stage and by source, plus how each channel actually
        converts. Every number is a live count -- nothing is tallied and
        stored, so a lead that moves stage moves the report with it."""
        queryset = Enquiry.objects.all()
        total = queryset.count()
        converted = queryset.filter(converted_user__isnull=False).count()

        by_status = dict(
            queryset.values_list("status").annotate(n=Count("id")).values_list("status", "n")
        )
        by_source = list(
            queryset.values("source")
            .annotate(
                total=Count("id"),
                joined=Count("id", filter=Q(converted_user__isnull=False)),
            )
            .order_by("-total")
        )
        labels = dict(EnquirySource.choices)
        for row in by_source:
            row["source_name"] = labels.get(row["source"], row["source"])
            row["conversion_rate"] = (
                round(row["joined"] * 100 / row["total"], 1) if row["total"] else 0.0
            )

        return Response(
            {
                "total": total,
                "converted": converted,
                "conversion_rate": round(converted * 100 / total, 1) if total else 0.0,
                "by_status": [
                    {"status": value, "status_name": label, "count": by_status.get(value, 0)}
                    for value, label in EnquiryStatus.choices
                ],
                "by_source": by_source,
            }
        )

    @action(detail=True, methods=["post"])
    def note(self, request, pk=None):
        """Adds an entry to the lead's trail. Kept separate from `notes` on the
        enquiry itself so an appended line can never overwrite the last one."""
        enquiry = self.get_object()
        body = (request.data.get("body") or "").strip()
        if not body:
            return Response({"body": ["This field is required."]}, status=http.HTTP_400_BAD_REQUEST)
        note = EnquiryNote.objects.create(enquiry=enquiry, body=body, author=request.user)
        return Response(EnquiryNoteSerializer(note).data, status=http.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def suggested_username(self, request, pk=None):
        """What `convert` would pick, so the desk can see it before committing."""
        return Response({"username": suggest_username(self.get_object().name)})

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        """Turns the lead into a member account and closes the loop on any
        referral that produced it."""
        enquiry = self.get_object()
        try:
            user = convert(
                enquiry,
                username=request.data.get("username"),
                email=request.data.get("email"),
                password=request.data.get("password"),
                converted_by=request.user,
            )
        except ConversionError as exc:
            return Response({"detail": str(exc)}, status=http.HTTP_400_BAD_REQUEST)
        enquiry.refresh_from_db()
        return Response(
            {"user_id": user.id, "username": user.username,
             "enquiry": self.get_serializer(enquiry).data},
            status=http.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def mark_called(self, request, pk=None):
        """Log the call. An optional `follow_up_on` schedules the next one and
        keeps the enquiry open; without it the enquiry moves to contacted."""
        enquiry = self.get_object()
        enquiry.last_contacted_on = timezone.localdate()

        raw_next = request.data.get("follow_up_on")
        if raw_next:
            # Parse through a DateField rather than assigning the raw string:
            # the unsaved instance is handed straight to the serializer, whose
            # `is_due` compares this against today's date, and a string there
            # raises instead of rescheduling. It rejects nonsense dates too.
            try:
                enquiry.follow_up_on = serializers.DateField().to_internal_value(raw_next)
            except serializers.ValidationError as exc:
                return Response({"follow_up_on": exc.detail}, status=400)
            enquiry.status = EnquiryStatus.OPEN
        else:
            enquiry.status = EnquiryStatus.CONTACTED

        enquiry.save()
        return Response(self.get_serializer(enquiry).data)


class RetentionPolicyViewSet(ModelViewSet):
    """What counts as 'gone quiet'. Admin-only, one active row at a time."""

    serializer_class = RetentionPolicySerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        # Built per request, not at import: the scoped manager needs a
        # tenant in scope and a class attribute is evaluated on load.
        return RetentionPolicy.objects.all()

    def perform_create(self, serializer):
        with transaction.atomic():
            RetentionPolicy.objects.filter(is_active=True).update(is_active=False)
            serializer.save(is_active=True)


class AtRiskView(APIView):
    """Members who have stopped turning up.

    Trainers get their own roster and admins get the gym -- the same scoping
    every other per-member list uses, so a trainer can work their people
    without seeing everyone else's.
    """

    permission_classes = [IsTrainerOrAdmin]

    def get(self, request):
        data = retention.summary(for_access=request.access)
        return Response(
            {
                "quiet_days": data["quiet_days"],
                "cooling_days": data["cooling_days"],
                "grace_days": data["grace_days"],
                "quiet_count": data["quiet_count"],
                "cooling_count": data["cooling_count"],
                "results": AtRiskMemberSerializer(data["results"], many=True).data,
            }
        )
