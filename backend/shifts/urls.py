from rest_framework.routers import DefaultRouter

from .views import ShiftViewSet

router = DefaultRouter()
router.register("", ShiftViewSet, basename="shift")

urlpatterns = router.urls
