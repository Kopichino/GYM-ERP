import openpyxl
from django.http import HttpResponse
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from core.permissions import IsAdmin

from . import kpis, services
from .builder import ReportError, run, schema
from .models import SavedReport


class SavedReportSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.username", read_only=True)

    class Meta:
        model = SavedReport
        fields = ["id", "name", "description", "definition", "owner", "owner_name", "created_at"]
        read_only_fields = ["id", "owner", "created_at"]


def _dates(request):
    return request.query_params.get("start") or None, request.query_params.get("end") or None


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
        start, end = _dates(request)
        grace = int(request.query_params.get("grace_days", 7))
        return Response(services.churn(start, end, grace_days=grace))


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
        workbook.save(response)
        return response


class KpiView(APIView):
    """The owner dashboard's headline numbers, all derived on read."""

    permission_classes = [IsAdmin]

    def get(self, request, *args, **kwargs):
        from datetime import date as date_cls, timedelta

        from django.utils import timezone

        today = timezone.localdate()
        start = request.query_params.get("start")
        end = request.query_params.get("end")
        start = date_cls.fromisoformat(start) if start else today - timedelta(days=29)
        end = date_cls.fromisoformat(end) if end else today
        return Response(kpis.summary(start, end))


class OccupancyView(APIView):
    """Visits by weekday and hour, for the heatmap.

    Lives here rather than on the attendance viewset because it reads the whole
    gym's footfall, which is an owner's question rather than a member's.
    """

    permission_classes = [IsAdmin]

    def get(self, request, *args, **kwargs):
        from datetime import date as date_cls, timedelta

        from django.utils import timezone

        from attendance.services import occupancy

        today = timezone.localdate()
        start = request.query_params.get("start")
        end = request.query_params.get("end")
        start = date_cls.fromisoformat(start) if start else today - timedelta(days=55)
        end = date_cls.fromisoformat(end) if end else today
        return Response(occupancy(start, end))
