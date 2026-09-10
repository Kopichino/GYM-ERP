from rest_framework.routers import DefaultRouter

from .views import CommissionEntryViewSet, CommissionRuleViewSet, MyEarningsView, PayoutViewSet

router = DefaultRouter()
router.register("rules", CommissionRuleViewSet, basename="commission-rule")
router.register("entries", CommissionEntryViewSet, basename="commission-entry")
router.register("payouts", PayoutViewSet, basename="payout")
router.register("my-earnings", MyEarningsView, basename="my-earnings")

urlpatterns = router.urls
