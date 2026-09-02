import openpyxl
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import generics
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from accounts.models import User
from core.permissions import IsAdminOrReadOnly

from .models import Payment, PaymentStatus, Plan
from .serializers import (
    AdminMemberBillingSerializer,
    AdminPaymentSerializer,
    MyPaymentSerializer,
    PlanSerializer,
)
from .services import get_latest_completed_payment, record_payment, sync_membership_status


class PlanViewSet(ModelViewSet):
    serializer_class = PlanSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        if self.request.user.is_staff:
            return Plan.objects.all()
        return Plan.objects.filter(is_active=True)


class MySubscriptionView(APIView):
    """A member's own current plan/status/expiry -- derived, not stored."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        payment = get_latest_completed_payment(request.user)
        if not payment:
            return Response(
                {
                    "plan": None,
                    "status": request.user.profile.membership_status,
                    "period_start": None,
                    "period_end": None,
                    "days_remaining": None,
                }
            )
        days_remaining = max((payment.period_end - timezone.localdate()).days, 0)
        return Response(
            {
                "plan": {"id": payment.plan_id, "name": payment.plan.name, "price": str(payment.plan.price)},
                "status": request.user.profile.membership_status,
                "period_start": payment.period_start,
                "period_end": payment.period_end,
                "days_remaining": days_remaining,
            }
        )


class MyPaymentListView(generics.ListAPIView):
    serializer_class = MyPaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Payment.objects.filter(member=self.request.user).select_related("plan")


def _member_billing_queryset():
    return (
        User.objects.filter(is_staff=False)
        .select_related("profile")
        .prefetch_related("payments__plan")
        .order_by("username")
    )


class AdminMemberBillingListView(generics.ListAPIView):
    """Admin dashboard's billing list -- same queryset/serializer the Excel
    export below uses, so the download always matches what's on screen."""

    serializer_class = AdminMemberBillingSerializer
    permission_classes = [IsAdminUser]
    queryset = _member_billing_queryset()


class AdminMemberBillingExportView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, *args, **kwargs):
        members = AdminMemberBillingSerializer(_member_billing_queryset(), many=True).data

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Billing"
        headers = [
            "Username",
            "Email",
            "Status",
            "Current plan",
            "Expiry",
            "Last payment date",
            "Last payment amount",
        ]
        sheet.append(headers)
        for member in members:
            sheet.append(
                [
                    member["username"],
                    member["email"],
                    member["membership_status"],
                    member["current_plan_name"],
                    member["current_period_end"],
                    member["last_payment_date"],
                    member["last_payment_amount"],
                ]
            )

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = "attachment; filename=gym_billing.xlsx"
        workbook.save(response)
        return response


class AdminPaymentViewSet(ModelViewSet):
    """Full CRUD on payments. Creating one is how a payment gets "recorded";
    editing/deleting one (a correction/void) must also re-sync the member's
    membership_status, since it can just as easily change whether they're
    currently active as creating one does."""

    serializer_class = AdminPaymentSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        queryset = Payment.objects.select_related("plan", "member").order_by("-paid_date", "-id")
        member_id = self.request.query_params.get("member")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        return queryset

    def perform_create(self, serializer):
        payment = record_payment(
            member=serializer.validated_data["member"],
            plan=serializer.validated_data["plan"],
            amount=serializer.validated_data["amount"],
            method=serializer.validated_data["method"],
            paid_date=serializer.validated_data.get("paid_date") or timezone.localdate(),
            notes=serializer.validated_data.get("notes", ""),
            recorded_by=self.request.user,
            status=serializer.validated_data.get("status", PaymentStatus.COMPLETED),
            external_reference=serializer.validated_data.get("external_reference", ""),
            gateway=serializer.validated_data.get("gateway"),
        )
        serializer.instance = payment

    def perform_update(self, serializer):
        payment = serializer.save()
        sync_membership_status(payment.member, respect_pause=False)

    def perform_destroy(self, instance):
        member = instance.member
        instance.delete()
        sync_membership_status(member, respect_pause=False)
