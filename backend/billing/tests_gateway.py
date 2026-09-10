"""The Razorpay client itself, on the paths where the call goes wrong.

`tests_online.py` covers the flow above this by faking `create_order`, which is
the right level for testing checkout but leaves the client untested: the
timeout, the 4xx, the error body that is not JSON. Those are the branches that
run on the day Razorpay has an incident, and the difference between a member
seeing "could not reach the payment gateway" and seeing a 500 is decided here.

So these mock `requests.post` rather than the gateway function.
"""

from decimal import Decimal
from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from accounts.models import MemberProfile, Role

from . import gateway
from .gateway import GatewayError, create_order, to_paise
from .models import PaymentOrder, Plan

User = get_user_model()

GATEWAY_SETTINGS = {
    "RAZORPAY_KEY_ID": "rzp_test_key",
    "RAZORPAY_KEY_SECRET": "rzp_test_secret",
    "RAZORPAY_WEBHOOK_SECRET": "hook_secret",
}


class FakeResponse:
    """Just enough of `requests.Response` for the client to read.

    `payload=None` makes `.json()` raise the way a proxy's HTML error page
    does, which is the case the client has a bare `except ValueError` for.
    """

    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no JSON object could be decoded")
        return self._payload


def make_member(username):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=Role.MEMBER
    )
    MemberProfile.objects.get_or_create(user=user)
    return user


@override_settings(**GATEWAY_SETTINGS)
class CreateOrderFailureTests(TenantAPIMixin, APITestCase):
    ORDER = {"id": "order_OK1", "amount": 140000, "currency": "INR", "status": "created"}

    @patch("billing.gateway.requests.post")
    def test_a_successful_call_returns_razorpays_json(self, post):
        post.return_value = FakeResponse(200, self.ORDER)
        self.assertEqual(create_order(Decimal("1400"), "rcpt-1"), self.ORDER)

    @patch("billing.gateway.requests.post")
    def test_a_timeout_becomes_a_readable_error(self, post):
        post.side_effect = requests.Timeout("timed out")
        with self.assertRaises(GatewayError) as caught:
            create_order(Decimal("1400"), "rcpt-1")
        self.assertIn("Could not reach the payment gateway", str(caught.exception))

    @patch("billing.gateway.requests.post")
    def test_a_connection_failure_becomes_the_same_error(self, post):
        post.side_effect = requests.ConnectionError("no route to host")
        with self.assertRaises(GatewayError):
            create_order(Decimal("1400"), "rcpt-1")

    @patch("billing.gateway.requests.post")
    def test_the_original_failure_is_kept_as_the_cause(self, post):
        # Chained rather than swallowed, so Sentry shows what actually broke
        # instead of just "could not reach the payment gateway".
        original = requests.Timeout("timed out")
        post.side_effect = original
        with self.assertRaises(GatewayError) as caught:
            create_order(Decimal("1400"), "rcpt-1")
        self.assertIs(caught.exception.__cause__, original)

    @patch("billing.gateway.requests.post")
    def test_razorpays_own_wording_is_preferred_on_a_rejection(self, post):
        # Their description is more useful at the counter than anything we
        # could write, so it is surfaced verbatim.
        post.return_value = FakeResponse(
            400, {"error": {"description": "Receipt already used"}}
        )
        with self.assertRaises(GatewayError) as caught:
            create_order(Decimal("1400"), "rcpt-dupe")
        self.assertEqual(str(caught.exception), "Receipt already used")

    @patch("billing.gateway.requests.post")
    def test_a_rejection_with_no_readable_body_still_fails_cleanly(self, post):
        # A gateway or proxy answering 502 with an HTML page: `.json()` raises,
        # and the client must not raise ValueError out of a payment call.
        post.return_value = FakeResponse(502, payload=None)
        with self.assertRaises(GatewayError) as caught:
            create_order(Decimal("1400"), "rcpt-1")
        self.assertEqual(str(caught.exception), "The payment gateway rejected that order.")

    @patch("billing.gateway.requests.post")
    def test_a_rejection_with_json_but_no_description_falls_back(self, post):
        post.return_value = FakeResponse(400, {"error": {}})
        with self.assertRaises(GatewayError):
            create_order(Decimal("1400"), "rcpt-1")

    @override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
    @patch("billing.gateway.requests.post")
    def test_an_unconfigured_gym_never_calls_out(self, post):
        with self.assertRaises(GatewayError):
            create_order(Decimal("1400"), "rcpt-1")
        post.assert_not_called()

    @patch("billing.gateway.requests.post")
    def test_the_amount_is_sent_in_paise(self, post):
        post.return_value = FakeResponse(200, self.ORDER)
        create_order(Decimal("1499.50"), "rcpt-1")

        sent = post.call_args.kwargs["json"]
        # Worked out here rather than read back: rupees would be silently
        # charged at a hundredth of the price.
        self.assertEqual(sent["amount"], 149950)
        self.assertEqual(sent["amount"], to_paise(Decimal("1499.50")))

    @patch("billing.gateway.requests.post")
    def test_a_long_receipt_is_trimmed_to_what_razorpay_accepts(self, post):
        post.return_value = FakeResponse(200, self.ORDER)
        create_order(Decimal("1400"), "r" * 100)
        self.assertEqual(len(post.call_args.kwargs["json"]["receipt"]), 40)

    @patch("billing.gateway.requests.post")
    def test_the_call_carries_a_timeout(self, post):
        # Without one a hung gateway holds the worker until it is killed.
        post.return_value = FakeResponse(200, self.ORDER)
        create_order(Decimal("1400"), "rcpt-1")
        self.assertEqual(post.call_args.kwargs["timeout"], gateway.TIMEOUT)


@override_settings(**GATEWAY_SETTINGS)
class OrderEndpointFailureTests(TenantAPIMixin, APITestCase):
    """What the member's browser gets when the gateway is down."""

    def setUp(self):
        self.member = make_member("gw_member")
        self.plan = Plan.objects.create(
            name="Yearly", price=Decimal("14000"), duration_days=365
        )
        self.client.force_authenticate(self.member)

    @patch("billing.gateway.requests.post")
    def test_an_unreachable_gateway_is_a_502_not_a_500(self, post):
        post.side_effect = requests.Timeout("timed out")
        resp = self.client.post("/api/billing/online/order/", {"plan": self.plan.id})

        self.assertEqual(resp.status_code, 502)
        self.assertIn("Could not reach", resp.data["detail"])

    @patch("billing.gateway.requests.post")
    def test_no_order_row_is_left_behind_when_the_gateway_fails(self, post):
        # A local order with no gateway order behind it can never be settled,
        # and would sit in the ledger looking like an abandoned checkout.
        post.side_effect = requests.Timeout("timed out")
        self.client.post("/api/billing/online/order/", {"plan": self.plan.id})
        self.assertFalse(PaymentOrder.objects.exists())

    @patch("billing.gateway.requests.post")
    def test_a_rejection_reaches_the_member_in_razorpays_words(self, post):
        post.return_value = FakeResponse(
            400, {"error": {"description": "Amount exceeds maximum"}}
        )
        resp = self.client.post("/api/billing/online/order/", {"plan": self.plan.id})

        self.assertEqual(resp.status_code, 502)
        self.assertIn("Amount exceeds maximum", resp.data["detail"])
