from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core.views import health_check

# Mounted first so it still shadows nothing, but only when it is wanted at all.
# See DJANGO_ADMIN_ENABLED / DJANGO_ADMIN_URL in settings.
admin_patterns = (
    [path(settings.DJANGO_ADMIN_URL, admin.site.urls)]
    if settings.DJANGO_ADMIN_ENABLED
    else []
)

urlpatterns = admin_patterns + [
    path("api/health/", health_check, name="health-check"),
    path("api/auth/", include("accounts.urls")),
    path("api/attendance/", include("attendance.urls")),
    path("api/workouts/", include("workouts.urls")),
    path("api/announcements/", include("announcements.urls")),
    path("api/schedule/", include("schedule_app.urls")),
    path("api/gallery/", include("gallery.urls")),
    path("api/billing/", include("billing.urls")),
    path("api/import/", include("dataimport.urls")),
    path("api/bodystats/", include("bodystats.urls")),
    path("api/devices/", include("devices.urls")),
    path("api/crm/", include("crm.urls")),
    path("api/expenses/", include("expenses.urls")),
    path("api/invoices/", include("invoicing.urls")),
    path("api/reports/", include("reports.urls")),
    path("api/nutrition/", include("nutrition.urls")),
    path("api/referrals/", include("referrals.urls")),
    path("api/whatsapp/", include("messaging.urls")),
    path("api/branding/", include("branding.urls")),
    path("api/gamification/", include("gamification.urls")),
    path("api/shifts/", include("shifts.urls")),
    path("api/pt/", include("pt.urls")),
    path("api/tenancy/", include("tenancy.urls")),
    path("api/feedback/", include("feedback.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    if not settings.CLOUDINARY_CLOUD_NAME:
        urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
