from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import BrandingViewSet, PublicBrandingView

router = DefaultRouter()
router.register("admin", BrandingViewSet, basename="branding")

urlpatterns = [
    path("", PublicBrandingView.as_view(), name="public-branding"),
] + router.urls
