from datetime import timedelta

import openpyxl
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from core.permissions import IsAdmin
from core.spreadsheets import neutralise_formulas

from . import kpis, services
from .builder import END_BEFORE_START, ReportError, check_window, run, schema
from .models import SavedReport


class SavedReportSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.username", read_only=True)

    class Meta:
        model = SavedReport
        fields = ["id", "name", "description", "definition", "owner", "owner_name", "created_at"]
        read_only_fields = ["id", "owner", "created_at"]

    def validate_definition(self, definition):
        # A saved report is re-run later; one whose window could never run is
        # refused now, rather than every time someone opens it.
        try:
            check_window(definition if isinstance(definition, dict) else {})
        except ReportError as exc:
            raise serializers.ValidationError(str(exc)) from None
        return definition


class ReportWindowForm(serializers.Serializer):
    """The date window a report is read over, parsed once at the edge.

    The services work in `date` objects. Handing them the raw query strings
    happened to work for the reports that pass the window straight to the ORM,
    which parses strings itself, and crashed churn, which compares dates in
    Python. A malformed date was a 500 either way.
    """

    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)

    def validate(self, attrs):
        start, end = attrs.get("start"), attrs.get("end")
        if start and end and end < start:
            raise serializers.ValidationError({"end": [END_BEFORE_START]})
        # A missing end means today, so a start after today with no end is a
        # backwards window in disguise -- answered with an empty report.
        if start and not end and start > timezone.localdate():
            raise serializers.ValidationError(
                {"start": ["The start date is after today. Choose an end date after it."]}
            )
        return attrs


class ChurnWindowForm(ReportWindowForm):
    # Bounded, because date arithmetic on an enormous value overflows.
    grace_days = serializers.IntegerField(required=False, default=7, min_value=0, max_value=365)


def _read_window(request, form_class=ReportWindowForm):
    """The validated window. A bad value is a 400 naming the field; a blank one
    means "use the default", as it always has."""
    form = form_class(
        data={key: value for key, value in request.query_params.items() if value != ""}
    )
    form.is_valid(raise_exception=True)
    return form.validated_data


def _dates(request):
    window = _read_window(request)
    return window.get("start"), window.get("end")


class _ReportView(APIView):
    """Reports read the whole gym's books, so they are admin-only."""

    permission_classes = [IsAdmin]
    report = None

    def get(self, request, *args, **kwargs):
        start, end = _dates(request)
        return Response(self.report(start, end))


class RevenueReportView(_ReportView):
    report = staticmethod(services.revenue)


class AttendanceReportView(_ReportView):
    report = staticmethod(services.attendance)


class ChurnReportView(_ReportView):
    permission_classes = [IsAdmin]

    def get(self, request, *args, **kwargs):
        window = _read_window(request, ChurnWindowForm)
        return Response(
            services.churn(window.get("start"), window.get("end"), grace_days=window["grace_days"])
        )


class PtPerformanceReportView(_ReportView):
    report = staticmethod(services.pt_performance)


class ReportSchemaView(APIView):
    """What the custom builder is allowed to ask for."""

    permission_classes = [IsAdmin]

    def get(self, request, *args, **kwargs):
        return Response(schema())


class RunCustomReportView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, *args, **kwargs):
        try:
            return Response(run(request.data))
        except ReportError as exc:
            return Response({"detail": str(exc)}, status=400)


class SavedReportViewSet(ModelViewSet):

    def get_queryset(self):
        # Built per request, not at import: the scoped manager needs a
        # tenant in scope and a class attribute is evaluated on load.
        return SavedReport.objects.select_related("owner")
    serializer_class = SavedReportSerializer
    permission_classes = [IsAdmin]

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=["get"])
    def run(self, request, pk=None):
        """Re-runs a saved definition against current data."""
        saved = self.get_object()
        try:
            return Response(run(saved.definition))
        except ReportError as exc:
            return Response({"detail": str(exc)}, status=400)


class ReportExportView(APIView):
    """Any report as .xlsx, so the numbers can go to an accountant."""

    permission_classes = [IsAdmin]

    def post(self, request, *args, **kwargs):
        try:
            result = run(request.data)
        except ReportError as exc:
            return Response({"detail": str(exc)}, status=400)

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Report"
        sheet.append(result["columns"])
        for row in result["rows"]:
            sheet.append([row.get(column) for column in result["columns"]])

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = "attachment; filename=ironcore_report.xlsx"
        neutralise_formulas(sheet)
        workbook.save(response)
        return response


class KpiView(APIView):
    """The owner dashboard's headline numbers, all derived on read."""

    permission_classes = [IsAdmin]

    def get(self, request, *args, **kwargs):
        # The same validated window as every other report. A malformed date was
        # a 500 here, and a backwards range quietly ran.
        window = _read_window(request)
        end = window.get("end") or timezone.localdate()
        start = window.get("start") or end - timedelta(days=29)
        return Response(kpis.summary(start, end))


class OccupancyView(APIView):
    """Visits by weekday and hour, for the heatmap.

    Lives here rather than on the attendance viewset because it reads the whole
    gym's footfall, which is an owner's question rather than a member's.
    """

    permission_classes = [IsAdmin]

    def get(self, request, *args, **kwargs):
        from attendance.services import occupancy

        window = _read_window(request)
        end = window.get("end") or timezone.localdate()
        start = window.get("start") or end - timedelta(days=55)
        return Response(occupancy(start, end))
