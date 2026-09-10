from rest_framework.routers import DefaultRouter

from .views import InstructorViewSet

router = DefaultRouter()
router.register("", InstructorViewSet, basename="instructor")

urlpatterns = router.urls
