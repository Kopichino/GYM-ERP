from rest_framework.routers import DefaultRouter

from .views import ClassSessionViewSet

router = DefaultRouter()
router.register("", ClassSessionViewSet, basename="class-session")

urlpatterns = router.urls
