"""Razorpay, spoken to directly over its REST API.

Two things are needed from a payment gateway and neither justifies an SDK: one
authenticated POST to open an order, and an HMAC to check that what came back is
genuinely from Razorpay. Both are below, so the only dependency is `requests`.

Nothing here decides what anything costs. Prices come from
`billing.services.price_with_discount` before an order is opened, and the amount
that is finally recorded is read back off our own order row -- never off the
callback. A browser that edits the amount it posts changes nothing.
"""

import hashlib
import hmac
from decimal import Decimal

import requests
from django.conf import settings
from django.utils.crypto import constant_time_compare

API_ROOT = "https://api.razorpay.com/v1"
TIMEOUT = 15


class GatewayError(Exception):
    """A gateway call that failed, with something worth showing the member."""


def key_id():
    return getattr(settings, "RAZORPAY_KEY_ID", "")


def _key_secret():
    return getattr(settings, "RAZORPAY_KEY_SECRET", "")


def is_configured():
    return bool(key_id() and _key_secret())


def to_paise(amount):
    """Razorpay works in the smallest currency unit; rupees are not accepted."""
    return int((Decimal(amount) * 100).quantize(Decimal("1")))


def create_order(amount, receipt, notes=None):
    """Opens an order and returns Razorpay's JSON for it."""
    if not is_configured():
        raise GatewayError("Online payment isn't set up for this gym yet.")

    try:
        response = requests.post(
            f"{API_ROOT}/orders",
            auth=(key_id(), _key_secret()),
            json={
                "amount": to_paise(amount),
                "currency": getattr(settings, "RAZORPAY_CURRENCY", "INR"),
                "receipt": receipt[:40],
                "notes": notes or {},
            },
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise GatewayError("Could not reach the payment gateway.") from exc

    if response.status_code >= 400:
        # Razorpay's own wording is more useful at the counter than ours.
        detail = ""
        try:
            detail = response.json().get("error", {}).get("description", "")
        except ValueError:
            pass
        raise GatewayError(detail or "The payment gateway rejected that order.")

    return response.json()


def _sign(payload):
    return hmac.new(
        _key_secret().encode(), payload.encode(), hashlib.sha256
    ).hexdigest()


def verify_payment_signature(order_id, payment_id, signature):
    """Whether this callback really came from Razorpay for this order.

    Razorpay signs "<order_id>|<payment_id>" with the key secret. Without this
    check, anyone who knows an order id could claim it was paid.
    """
    if not (order_id and payment_id and signature and _key_secret()):
        return False
    return constant_time_compare(signature, _sign(f"{order_id}|{payment_id}"))


def verify_webhook_signature(raw_body, signature):
    """Whether a webhook body is genuine. Signed with the webhook secret, which
    is a different secret from the API key -- Razorpay issues it per endpoint."""
    secret = getattr(settings, "RAZORPAY_WEBHOOK_SECRET", "")
    if not (secret and signature):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return constant_time_compare(signature, expected)
