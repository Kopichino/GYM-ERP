from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AttendanceReportView,
    ChurnReportView,
    KpiView,
    OccupancyView,
    PtPerformanceReportView,
    ReportExportView,
    ReportSchemaView,
    RevenueReportView,
    RunCustomReportView,
    SavedReportViewSet,
)

router = DefaultRouter()
router.register("saved", SavedReportViewSet, basename="saved-report")

urlpatterns = [
    path("kpis/", KpiView.as_view(), name="report-kpis"),
    path("occupancy/", OccupancyView.as_view(), name="report-occupancy"),
    path("revenue/", RevenueReportView.as_view(), name="report-revenue"),
    path("attendance/", AttendanceReportView.as_view(), name="report-attendance"),
    path("churn/", ChurnReportView.as_view(), name="report-churn"),
    path("pt-performance/", PtPerformanceReportView.as_view(), name="report-pt"),
    path("schema/", ReportSchemaView.as_view(), name="report-schema"),
    path("custom/", RunCustomReportView.as_view(), name="report-custom"),
    path("export/", ReportExportView.as_view(), name="report-export"),
] + router.urls
