from rest_framework.routers import DefaultRouter

from .views import ReferralProgramViewSet, ReferralViewSet

router = DefaultRouter()
router.register("programs", ReferralProgramViewSet, basename="referralprogram")
router.register("", ReferralViewSet, basename="referral")

urlpatterns = router.urls
