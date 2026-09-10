from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BadgeViewSet,
    GamificationProfileView,
    LeaderboardView,
    MyAchievementsView,
    MyRecordsView,
    MyStandingView,
    PRCelebrationView,
)

router = DefaultRouter()
router.register("badges", BadgeViewSet, basename="badge")

urlpatterns = [
    path("me/", GamificationProfileView.as_view(), name="gamification-me"),
    path("achievements/", MyAchievementsView.as_view(), name="my-achievements"),
    path("records/", MyRecordsView.as_view(), name="my-records"),
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    path("leaderboard/me/", MyStandingView.as_view(), name="my-standing"),
    path("records/new/", PRCelebrationView.as_view(), name="pr-celebrations"),
] + router.urls
