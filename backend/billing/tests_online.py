import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from accounts.models import MemberProfile, MembershipStatus, Role

from .models import (
    Discount,
    DiscountType,
    OrderStatus,
    PaymentGateway,
    PaymentOrder,
    PaymentStatus,
    Plan,
)

User = get_user_model()

KEY_ID = "rzp_test_key"
KEY_SECRET = "rzp_test_secret"
WEBHOOK_SECRET = "hook_secret"

GATEWAY_SETTINGS = {
    "RAZORPAY_KEY_ID": KEY_ID,
    "RAZORPAY_KEY_SECRET": KEY_SECRET,
    "RAZORPAY_WEBHOOK_SECRET": WEBHOOK_SECRET,
}


def sign(payload, secret=KEY_SECRET):
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def make_member(username):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=Role.MEMBER
    )
    MemberProfile.objects.get_or_create(user=user)
    return user


@override_settings(**GATEWAY_SETTINGS)
class OnlineOrderTests(TenantAPIMixin, APITestCase):
    """Opening an order. The price is decided here, never by the browser."""

    def setUp(self):
        self.member = make_member("payer")
        self.plan = Plan.objects.create(
            name="Yearly", price=Decimal("14000"), duration_days=365
        )
        self.client.force_authenticate(self.member)

    def order_response(self, order_id="order_TEST1"):
        return {"id": order_id, "amount": 1400000, "currency": "INR", "status": "created"}

    @patch("billing.gateway.create_order")
    def test_order_is_priced_server_side(self, create_order):
        create_order.return_value = self.order_response()
        # The client tries to name its own price; nothing reads it.
        resp = self.client.post(
            "/api/billing/online/order/", {"plan": self.plan.id, "amount": "1"}
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["amount"], "14000.00")

        order = PaymentOrder.objects.get()
        self.assertEqual(order.amount, Decimal("14000.00"))
        self.assertEqual(order.member, self.member)
        self.assertEqual(order.status, OrderStatus.CREATED)

    @patch("billing.gateway.create_order")
    def test_a_valid_code_reduces_the_order(self, create_order):
        create_order.return_value = self.order_response()
        Discount.objects.create(
            code="SAVE10", discount_type=DiscountType.PERCENT, value=Decimal("10")
        )
        resp = self.client.post(
            "/api/billing/online/order/", {"plan": self.plan.id, "code": "SAVE10"}
        )
        self.assertEqual(resp.data["amount"], "12600.00")
        self.assertEqual(resp.data["discount_amount"], "1400.00")

    @patch("billing.gateway.create_order")
    def test_a_bad_code_is_refused_before_any_order_is_opened(self, create_order):
        resp = self.client.post(
            "/api/billing/online/order/", {"plan": self.plan.id, "code": "NOPE"}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(resp.data["code_rejected"])
        create_order.assert_not_called()
        self.assertFalse(PaymentOrder.objects.exists())

    def test_config_tells_the_browser_whether_to_offer_it(self):
        resp = self.client.get("/api/billing/online/config/")
        self.assertTrue(resp.data["enabled"])
        self.assertEqual(resp.data["key_id"], KEY_ID)

    @override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
    def test_config_is_honest_when_the_gateway_is_not_set_up(self):
        resp = self.client.get("/api/billing/online/config/")
        self.assertFalse(resp.data["enabled"])

    @override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
    def test_ordering_without_a_gateway_fails_loudly(self):
        resp = self.client.post("/api/billing/online/order/", {"plan": self.plan.id})
        self.assertEqual(resp.status_code, 502)


@override_settings(**GATEWAY_SETTINGS)
class VerifyPaymentTests(TenantAPIMixin, APITestCase):
    """Settling an order. Nothing is believed without Razorpay's signature."""

    def setUp(self):
        self.member = make_member("verifier")
        self.plan = Plan.objects.create(
            name="Monthly", price=Decimal("1500"), duration_days=30
        )
        self.order = PaymentOrder.objects.create(
            member=self.member,
            plan=self.plan,
            amount=Decimal("1500.00"),
            order_id="order_V1",
            gateway=PaymentGateway.RAZORPAY,
        )
        self.client.force_authenticate(self.member)

    def verify(self, payment_id="pay_V1", signature=None, order_id=None):
        order_id = order_id or self.order.order_id
        return self.client.post(
            "/api/billing/online/verify/",
            {
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature
                if signature is not None
                else sign(f"{order_id}|{payment_id}"),
            },
        )

    def test_a_signed_callback_records_the_payment(self):
        resp = self.verify()
        self.assertEqual(resp.status_code, 201)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PAID)
        payment = self.order.payment
        self.assertEqual(payment.amount, Decimal("1500.00"))
        self.assertEqual(payment.status, PaymentStatus.COMPLETED)
        self.assertEqual(payment.gateway, PaymentGateway.RAZORPAY)
        self.assertEqual(payment.external_reference, "pay_V1")

    def test_settling_syncs_the_derived_membership_status(self):
        self.verify()
        self.member.profile.refresh_from_db()
        self.assertEqual(self.member.profile.membership_status, MembershipStatus.ACTIVE)

    def test_an_invoice_and_commission_follow_the_same_as_a_counter_sale(self):
        from invoicing.models import Invoice

        self.verify()
        self.order.refresh_from_db()
        self.assertTrue(Invoice.objects.filter(payment=self.order.payment).exists())

    def test_a_forged_signature_records_nothing(self):
        resp = self.verify(signature="deadbeef")
        self.assertEqual(resp.status_code, 400)
        self.order.refresh_from_db()
        self.assertIsNone(self.order.payment)
        self.assertEqual(self.order.status, OrderStatus.FAILED)

    def test_a_replayed_callback_does_not_charge_twice(self):
        self.verify()
        self.order.refresh_from_db()
        first = self.order.payment_id

        resp = self.verify()
        self.assertEqual(resp.status_code, 201)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_id, first)
        self.assertEqual(self.member.payments.count(), 1)

    def test_someone_elses_order_cannot_be_settled(self):
        intruder = make_member("intruder")
        self.client.force_authenticate(intruder)
        resp = self.verify()
        self.assertEqual(resp.status_code, 403)
        self.order.refresh_from_db()
        self.assertIsNone(self.order.payment)

    def test_an_unknown_order_is_a_404_not_a_new_payment(self):
        resp = self.verify(order_id="order_NOPE")
        self.assertEqual(resp.status_code, 404)


@override_settings(**GATEWAY_SETTINGS)
class WebhookTests(TenantAPIMixin, APITestCase):
    """The safety net for a browser callback that never arrives."""

    def setUp(self):
        self.member = make_member("hooked")
        self.plan = Plan.objects.create(
            name="Monthly", price=Decimal("1500"), duration_days=30
        )
        self.order = PaymentOrder.objects.create(
            member=self.member,
            plan=self.plan,
            amount=Decimal("1500.00"),
            order_id="order_W1",
        )

    def post_hook(self, body, secret=WEBHOOK_SECRET):
        raw = json.dumps(body)
        return self.client.post(
            "/api/billing/online/webhook/",
            data=raw,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=hmac.new(
                secret.encode(), raw.encode(), hashlib.sha256
            ).hexdigest(),
        )

    def captured(self, order_id="order_W1", payment_id="pay_W1"):
        return {
            "event": "payment.captured",
            "payload": {"payment": {"entity": {"id": payment_id, "order_id": order_id}}},
        }

    def test_a_signed_capture_settles_the_order(self):
        resp = self.post_hook(self.captured())
        self.assertEqual(resp.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PAID)
        self.assertEqual(self.order.payment.amount, Decimal("1500.00"))

    def test_an_unsigned_body_is_refused(self):
        raw = json.dumps(self.captured())
        resp = self.client.post(
            "/api/billing/online/webhook/", data=raw, content_type="application/json"
        )
        self.assertEqual(resp.status_code, 400)
        self.order.refresh_from_db()
        self.assertIsNone(self.order.payment)

    def test_a_body_signed_with_the_wrong_secret_is_refused(self):
        resp = self.post_hook(self.captured(), secret="not-the-secret")
        self.assertEqual(resp.status_code, 400)
        self.order.refresh_from_db()
        self.assertIsNone(self.order.payment)

    def test_other_events_are_acknowledged_and_ignored(self):
        resp = self.post_hook({"event": "payment.failed", "payload": {}})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("ignored", resp.data)
        self.order.refresh_from_db()
        self.assertIsNone(self.order.payment)

    def test_an_unknown_order_is_acknowledged_rather_than_retried_forever(self):
        resp = self.post_hook(self.captured(order_id="order_SOMEONE_ELSE"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["ignored"], "unknown order")

    def test_webhook_and_callback_together_still_charge_once(self):
        """The pair race in production; the order's one-to-one settles it."""
        self.post_hook(self.captured())
        self.client.force_authenticate(self.member)
        self.client.post(
            "/api/billing/online/verify/",
            {
                "razorpay_order_id": "order_W1",
                "razorpay_payment_id": "pay_W1",
                "razorpay_signature": sign("order_W1|pay_W1"),
            },
        )
        self.assertEqual(self.member.payments.count(), 1)


class SignatureTests(TenantAPIMixin, APITestCase):
    """The HMAC itself, independent of any endpoint."""

    @override_settings(**GATEWAY_SETTINGS)
    def test_a_genuine_signature_verifies(self):
        from .gateway import verify_payment_signature

        self.assertTrue(
            verify_payment_signature("order_1", "pay_1", sign("order_1|pay_1"))
        )

    @override_settings(**GATEWAY_SETTINGS)
    def test_swapped_ids_do_not_verify(self):
        from .gateway import verify_payment_signature

        self.assertFalse(
            verify_payment_signature("pay_1", "order_1", sign("order_1|pay_1"))
        )

    @override_settings(RAZORPAY_KEY_SECRET="")
    def test_nothing_verifies_without_a_secret(self):
        from .gateway import verify_payment_signature

        self.assertFalse(verify_payment_signature("order_1", "pay_1", "anything"))

    def test_rupees_convert_to_paise_without_float_drift(self):
        from .gateway import to_paise

        self.assertEqual(to_paise(Decimal("14000.00")), 1400000)
        self.assertEqual(to_paise(Decimal("1234.56")), 123456)
        self.assertEqual(to_paise(Decimal("0.10")), 10)
