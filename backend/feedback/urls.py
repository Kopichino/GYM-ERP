from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import NpsView, SurveyResponseViewSet, SurveyViewSet

router = DefaultRouter()
router.register("surveys", SurveyViewSet, basename="survey")
router.register("responses", SurveyResponseViewSet, basename="survey-response")

urlpatterns = [
    path("nps/", NpsView.as_view(), name="nps"),
] + router.urls
