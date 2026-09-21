"""The browser is never the authority on money.

`billing.tests_online` already pins that an order is priced server-side, that
a forged signature records nothing and that a replayed callback charges once.
These add what that suite did not cover.
"""

import hashlib
import hmac
import json
from decimal import Decimal

from django.test import override_settings
from rest_framework.test import APITestCase

from accounts.models import Role
from billing.models import OrderStatus, Payment, PaymentOrder, Plan

from .testing import OneGymTestCase

KEY_SECRET = "rzp_test_secret"
GATEWAY = {
    "RAZORPAY_KEY_ID": "rzp_test_key",
    "RAZORPAY_KEY_SECRET": KEY_SECRET,
    "RAZORPAY_WEBHOOK_SECRET": "hook_secret",
}


@override_settings(**GATEWAY)
class PaymentCallbackTests(OneGymTestCase):
    def setUp(self):
        super().setUp()
        self.member = self.person("payer")
        self.other = self.person("bystander")
        self.plan = Plan.objects.create(name="Yearly", price=Decimal("14000"), duration_days=365)
        self.order = PaymentOrder.objects.create(
            member=self.member, plan=self.plan, amount=Decimal("14000.00"), order_id="order_V1"
        )

    def verify(self, signature, payment_id="pay_V1"):
        return self.client.post(
            "/api/billing/online/verify/",
            {
                "razorpay_order_id": "order_V1",
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            },
        )

    def good_signature(self, payment_id="pay_V1"):
        message = f"order_V1|{payment_id}".encode()
        return hmac.new(KEY_SECRET.encode(), message, hashlib.sha256).hexdigest()

    def test_a_forged_callback_after_payment_does_not_mark_the_order_failed(self):
        """A bad signature used to flip any order to FAILED -- including one that
        had already been paid, leaving a settled order reporting a failure."""
        self.client.force_authenticate(self.member)
        self.assertEqual(self.verify(self.good_signature()).status_code, 201)
        self.assertEqual(self.verify("forged").status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PAID)
        self.assertIsNotNone(self.order.payment_id)

    def test_the_amount_recorded_is_the_orders_not_the_callbacks(self):
        self.client.force_authenticate(self.member)
        resp = self.client.post(
            "/api/billing/online/verify/",
            {
                "razorpay_order_id": "order_V1",
                "razorpay_payment_id": "pay_V1",
                "razorpay_signature": self.good_signature(),
                "amount": "1.00",
                "plan": self.plan.pk,
                "status": "completed",
            },
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Payment.objects.get(member=self.member).amount, Decimal("14000.00"))

    def test_another_members_order_cannot_be_settled_or_failed(self):
        self.client.force_authenticate(self.other)
        self.assertIn(self.verify("forged").status_code, (403, 404))
        self.assertIn(self.verify(self.good_signature()).status_code, (403, 404))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.CREATED)
        self.assertFalse(Payment.objects.exists())


class CounterCheckoutTests(OneGymTestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.person("desk", Role.ADMIN)
        self.member = self.person("walkin")
        self.plan = Plan.objects.create(name="Monthly", price=Decimal("1000"), duration_days=30)

    def test_a_retired_plan_cannot_be_sold(self):
        """The audit found a deactivated plan still offered and sold at the desk."""
        self.plan.is_active = False
        self.plan.save(update_fields=["is_active"])
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/billing/checkout/", {"member": self.member.pk, "plan": self.plan.pk}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("plan", resp.data)
        self.assertFalse(Payment.objects.exists())

    def test_a_member_cannot_ring_up_their_own_sale(self):
        self.client.force_authenticate(self.member)
        resp = self.client.post(
            "/api/billing/checkout/",
            {"member": self.member.pk, "plan": self.plan.pk, "amount": "1.00"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Payment.objects.exists())

    def test_an_unknown_payment_method_is_refused(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/billing/checkout/",
            {"member": self.member.pk, "plan": self.plan.pk, "method": "<script>"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Payment.objects.exists())


@override_settings(WHATSAPP_APP_SECRET="meta-secret", WHATSAPP_TOKEN="", WHATSAPP_PHONE_NUMBER_ID="")
class WhatsAppWebhookTests(APITestCase):
    def deliver(self, path, secret=b"meta-secret"):
        body = json.dumps(
            {
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "messages": [
                                        {
                                            "from": "919000000000",
                                            "id": "wamid.SECURITY1",
                                            "type": "text",
                                            "text": {"body": "when does my plan end?"},
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ]
            }
        )
        signature = "sha256=" + hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
        return self.client.post(
            path, data=body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=signature
        )

    def test_a_signed_delivery_on_the_shared_url_is_acknowledged_not_crashed(self):
        """No gym in the URL used to reach the scoped message log and raise a 500,
        which Meta retries indefinitely."""
        self.assertEqual(self.deliver("/api/whatsapp/webhook/").status_code, 200)

    def test_an_unsigned_delivery_is_refused(self):
        self.assertEqual(self.deliver("/api/whatsapp/webhook/", secret=b"wrong").status_code, 400)
