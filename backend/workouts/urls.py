from rest_framework.routers import DefaultRouter

from .views import (
    ExerciseViewSet,
    SplitDayViewSet,
    SplitExerciseViewSet,
    WorkoutLogViewSet,
    WorkoutSessionViewSet,
    WorkoutSplitViewSet,
)

router = DefaultRouter()
router.register("exercises", ExerciseViewSet, basename="exercise")
router.register("sessions", WorkoutSessionViewSet, basename="workout-session")
router.register("logs", WorkoutLogViewSet, basename="workout-log")
router.register("splits", WorkoutSplitViewSet, basename="workout-split")
router.register("split-days", SplitDayViewSet, basename="split-day")
router.register("split-exercises", SplitExerciseViewSet, basename="split-exercise")

urlpatterns = router.urls
