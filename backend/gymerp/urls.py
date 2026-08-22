from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core.views import health_check

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health_check, name="health-check"),
    path("api/auth/", include("accounts.urls")),
    path("api/attendance/", include("attendance.urls")),
    path("api/workouts/", include("workouts.urls")),
    path("api/announcements/", include("announcements.urls")),
    path("api/instructors/", include("instructors.urls")),
    path("api/schedule/", include("schedule_app.urls")),
    path("api/gallery/", include("gallery.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    if not settings.CLOUDINARY_CLOUD_NAME:
        urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
