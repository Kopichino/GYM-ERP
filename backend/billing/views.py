from decimal import Decimal

import openpyxl
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from accounts.models import Role, User
from core.permissions import access, IsAdmin, IsAdminOrReadOnly

from .models import Discount, PaymentMethod, Payment, PaymentStatus, Plan
from .serializers import (
    AdminMemberBillingSerializer,
    AdminPaymentSerializer,
    CheckoutSerializer,
    DiscountSerializer,
    MyPaymentSerializer,
    PlanSerializer,
)
from .services import (
    DiscountError,
    compute_period,
    get_latest_completed_payment,
    price_with_discount,
    record_payment,
    sync_membership_status,
)


class PlanViewSet(ModelViewSet):
    serializer_class = PlanSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        if access(self.request).is_admin:
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
        User.objects.filter(role=Role.MEMBER)
        .select_related("profile")
        .prefetch_related("payments__plan")
        .order_by("username")
    )


class AdminMemberBillingListView(generics.ListAPIView):
    """Admin dashboard's billing list -- same queryset/serializer the Excel
    export below uses, so the download always matches what's on screen."""

    serializer_class = AdminMemberBillingSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        # Built per request, not at import: the scoped manager needs a
        # tenant in scope and a class attribute is evaluated on load.
        return _member_billing_queryset()


class AdminMemberBillingExportView(APIView):
    permission_classes = [IsAdmin]

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
    permission_classes = [IsAdmin]

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
        from commissions.services import accrue_for_payment

        payment = serializer.save()
        sync_membership_status(payment.member, respect_pause=False)
        # A payment flipped to refunded/failed must reverse its commission too,
        # or a trainer keeps credit for money the gym handed back.
        accrue_for_payment(payment)

    def perform_destroy(self, instance):
        from commissions.services import void_for_payment

        member = instance.member
        void_for_payment(instance)
        instance.delete()
        sync_membership_status(member, respect_pause=False)


class DiscountViewSet(ModelViewSet):
    """Offers the front desk can apply at checkout."""


    def get_queryset(self):
        # Built per request, not at import: the scoped manager needs a
        # tenant in scope and a class attribute is evaluated on load.
        return Discount.objects.prefetch_related("plans", "payments")
    serializer_class = DiscountSerializer
    permission_classes = [IsAdmin]


class _CheckoutBase(APIView):
    permission_classes = [IsAdmin]

    def _resolve(self, request):
        """Validates the request and prices it. Returns everything both the
        quote and the sale need, so the two can't drift apart."""
        form = CheckoutSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data

        member = get_object_or_404(User, pk=data["member"])
        plan = get_object_or_404(Plan, pk=data["plan"])
        paid_date = data.get("paid_date") or timezone.localdate()

        discount, amount_off, total = price_with_discount(
            plan, member, data.get("code"), on=paid_date
        )

        # An operator-entered amount overrides the computed one. Whatever the
        # gap to list price is gets booked as the discount, so gross always
        # reconciles to the plan's price whether the reduction came from a code,
        # a negotiation, or both.
        override = data.get("amount")
        custom = override is not None
        if custom:
            total = Decimal(override)
            amount_off = max(Decimal(plan.price) - total, Decimal("0.00"))

        period_start, period_end = compute_period(member, plan, paid_date)
        return {
            "form": data,
            "member": member,
            "plan": plan,
            "paid_date": paid_date,
            "discount": discount,
            "amount_off": amount_off,
            "total": total,
            "custom_amount": custom,
            "period_start": period_start,
            "period_end": period_end,
        }

    def _breakdown(self, priced):
        return {
            "member": priced["member"].id,
            "member_name": priced["member"].get_full_name() or priced["member"].username,
            "plan": priced["plan"].id,
            "plan_name": priced["plan"].name,
            "list_price": str(priced["plan"].price),
            "discount_code": priced["discount"].code if priced["discount"] else None,
            "discount_label": str(priced["discount"]) if priced["discount"] else None,
            "discount_amount": str(priced["amount_off"]),
            "total": str(priced["total"]),
            "custom_amount": priced["custom_amount"],
            "period_start": priced["period_start"],
            "period_end": priced["period_end"],
            # True when the member still has time left, so the new period is
            # stacked on the end rather than starting today.
            "extends_existing": priced["period_start"] != priced["paid_date"],
        }


class CheckoutQuoteView(_CheckoutBase):
    """Prices a sale without writing anything, so the counter can show a total
    (and reject a bad code) before taking any money."""

    def post(self, request, *args, **kwargs):
        try:
            priced = self._resolve(request)
        except DiscountError as exc:
            return Response({"detail": str(exc), "code_rejected": True}, status=400)
        return Response(self._breakdown(priced))


class CheckoutView(_CheckoutBase):
    """Takes the payment. Prices the sale exactly as the quote did, then hands
    off to record_payment -- which is what stacks the period and re-syncs the
    member's derived status."""

    def post(self, request, *args, **kwargs):
        try:
            priced = self._resolve(request)
        except DiscountError as exc:
            return Response({"detail": str(exc), "code_rejected": True}, status=400)

        payment = record_payment(
            member=priced["member"],
            plan=priced["plan"],
            amount=priced["total"],
            method=priced["form"].get("method") or PaymentMethod.CASH,
            paid_date=priced["paid_date"],
            notes=priced["form"].get("notes", ""),
            recorded_by=request.user,
            discount=priced["discount"],
            discount_amount=priced["amount_off"],
        )

        # Every completed sale gets its tax invoice straight away. Imported
        # locally so billing doesn't hard-depend on invoicing at module load.
        from invoicing.services import issue_invoice

        invoice = issue_invoice(payment)

        from commissions.services import accrue_for_payment

        accrue_for_payment(payment)

        return Response(
            {
                "payment": AdminPaymentSerializer(payment).data,
                "invoice": {"id": invoice.id, "number": invoice.number},
                **self._breakdown(priced),
            },
            status=201,
        )
