from rest_framework.routers import DefaultRouter

from .views import CheckInOutViewSet

router = DefaultRouter()
router.register("", CheckInOutViewSet, basename="checkinout")

urlpatterns = router.urls
