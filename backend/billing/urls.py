from django.urls import path
from rest_framework.routers import DefaultRouter

from .online_views import (
    CreateOrderView,
    OnlinePaymentConfigView,
    RazorpayWebhookView,
    VerifyPaymentView,
)
from .daypass_views import DayPassViewSet
from .views import (
    AdminMemberBillingExportView,
    AdminMemberBillingListView,
    AdminPaymentViewSet,
    CheckoutQuoteView,
    CheckoutView,
    DiscountViewSet,
    MyPaymentListView,
    MySubscriptionView,
    PlanViewSet,
)

router = DefaultRouter()
router.register("plans", PlanViewSet, basename="plan")
router.register("admin/payments", AdminPaymentViewSet, basename="admin-payment")
router.register("discounts", DiscountViewSet, basename="discount")
router.register("day-passes", DayPassViewSet, basename="daypass")

urlpatterns = [
    path("my-subscription/", MySubscriptionView.as_view(), name="my-subscription"),
    path("my-payments/", MyPaymentListView.as_view(), name="my-payments"),
    path("admin/members/", AdminMemberBillingListView.as_view(), name="admin-billing-members"),
    path("admin/members/export/", AdminMemberBillingExportView.as_view(), name="admin-billing-export"),
    path("checkout/quote/", CheckoutQuoteView.as_view(), name="checkout-quote"),
    path("checkout/", CheckoutView.as_view(), name="checkout"),
    path("online/config/", OnlinePaymentConfigView.as_view(), name="online-config"),
    path("online/order/", CreateOrderView.as_view(), name="online-order"),
    path("online/verify/", VerifyPaymentView.as_view(), name="online-verify"),
    path("online/webhook/", RazorpayWebhookView.as_view(), name="online-webhook"),
] + router.urls
