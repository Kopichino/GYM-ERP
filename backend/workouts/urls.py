from rest_framework.routers import DefaultRouter

from .views import ExerciseViewSet, WorkoutLogViewSet, WorkoutSessionViewSet

router = DefaultRouter()
router.register("exercises", ExerciseViewSet, basename="exercise")
router.register("sessions", WorkoutSessionViewSet, basename="workout-session")
router.register("logs", WorkoutLogViewSet, basename="workout-log")

urlpatterns = router.urls
