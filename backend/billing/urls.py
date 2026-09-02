from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminMemberBillingExportView,
    AdminMemberBillingListView,
    AdminPaymentViewSet,
    MyPaymentListView,
    MySubscriptionView,
    PlanViewSet,
)

router = DefaultRouter()
router.register("plans", PlanViewSet, basename="plan")
router.register("admin/payments", AdminPaymentViewSet, basename="admin-payment")

urlpatterns = [
    path("my-subscription/", MySubscriptionView.as_view(), name="my-subscription"),
    path("my-payments/", MyPaymentListView.as_view(), name="my-payments"),
    path("admin/members/", AdminMemberBillingListView.as_view(), name="admin-billing-members"),
    path("admin/members/export/", AdminMemberBillingExportView.as_view(), name="admin-billing-export"),
] + router.urls
