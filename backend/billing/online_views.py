"""Member-facing online payment: open an order, then confirm it.

Kept apart from the counter checkout because the trust model is different. At
the counter an admin is asserting that money changed hands; here nobody is, so
every claim of payment has to carry Razorpay's signature before it is believed.
"""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .gateway import (
    GatewayError,
    is_configured,
    key_id,
    verify_payment_signature,
    verify_webhook_signature,
)
from .models import OrderStatus, PaymentOrder, Plan
from .serializers import AdminPaymentSerializer
from .services import DiscountError, open_online_order, settle_online_order
from core.permissions import access


class OnlinePaymentConfigView(APIView):
    """What the browser needs to decide whether to offer online payment at all.
    The publishable key id is safe to hand out; the secret never leaves here."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"enabled": is_configured(), "key_id": key_id()})


class CreateOrderView(APIView):
    """Opens an order for the signed-in member's own renewal."""

    permission_classes = [IsAuthenticated]
    throttle_scope = "checkout"

    def post(self, request):
        plan = get_object_or_404(Plan, pk=request.data.get("plan"), is_active=True)
        try:
            order = open_online_order(
                request.user, plan, code=request.data.get("code") or None
            )
        except DiscountError as exc:
            return Response({"detail": str(exc), "code_rejected": True}, status=400)
        except GatewayError as exc:
            return Response({"detail": str(exc)}, status=502)

        return Response(
            {
                "order_id": order.order_id,
                # Rupees for display; the widget is handed paise by Razorpay's
                # own order object, so there is nothing to keep in step here.
                "amount": str(order.amount),
                "discount_amount": str(order.discount_amount),
                "plan_name": plan.name,
                "key_id": key_id(),
                "member_name": request.user.get_full_name() or request.user.username,
                "email": request.user.email,
            },
            status=status.HTTP_201_CREATED,
        )


class VerifyPaymentView(APIView):
    """What the browser posts back when Razorpay's widget reports success.

    The signature is the whole point: without it this endpoint would let anyone
    who knows an order id mark it paid.
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = "checkout"

    def post(self, request):
        order_id = request.data.get("razorpay_order_id", "")
        payment_id = request.data.get("razorpay_payment_id", "")
        signature = request.data.get("razorpay_signature", "")

        order = get_object_or_404(PaymentOrder, order_id=order_id)
        # Someone else's order is not yours to settle, signature or not.
        if order.member_id != request.user.id and not access(request).is_admin:
            return Response({"detail": "That order isn't yours."}, status=403)

        if not verify_payment_signature(order_id, payment_id, signature):
            order.status = OrderStatus.FAILED
            order.save(update_fields=["status", "updated_at"])
            return Response(
                {"detail": "We couldn't verify that payment. Nothing has been charged to you."},
                status=400,
            )

        payment = settle_online_order(order, gateway_payment_id=payment_id)
        return Response(
            {"payment": AdminPaymentSerializer(payment).data},
            status=status.HTTP_201_CREATED,
        )


class RazorpayWebhookView(APIView):
    """Razorpay's own report that an order was captured.

    Unauthenticated by necessity -- Razorpay has no session with us -- so the
    body's signature is the only thing that makes it trustworthy. It exists
    because the browser callback can be lost: the member closes the tab, the
    network drops, and the money is taken anyway. This is what stops that
    becoming a member who paid and got nothing.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        signature = request.headers.get("X-Razorpay-Signature", "")
        if not verify_webhook_signature(request.body, signature):
            return Response({"detail": "Bad signature."}, status=400)

        payload = request.data or {}
        if payload.get("event") != "payment.captured":
            # Every other event is acknowledged and ignored; returning an error
            # would make Razorpay retry something we will never act on.
            return Response({"ignored": payload.get("event", "")})

        entity = (
            payload.get("payload", {}).get("payment", {}).get("entity", {})
        )
        order = PaymentOrder.objects.filter(order_id=entity.get("order_id", "")).first()
        if order is None:
            # Not an order of ours. Acknowledged so it isn't retried forever.
            return Response({"ignored": "unknown order"})

        settle_online_order(order, gateway_payment_id=entity.get("id", ""))
        return Response({"settled": order.order_id})
