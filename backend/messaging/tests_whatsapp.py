"""The WhatsApp client, on the paths where Meta says no.

`tests.py` fakes `send_text`/`send_template`, which is right for testing the
reminder sweep but leaves the client below them untested -- the timeout, the
4xx, the error body that is not JSON. A send that fails has to end up recorded
against the message with a readable reason, because that failure is invisible
otherwise: nobody is watching, and the member simply never hears from the gym.
"""

import hashlib
import hmac
import json
from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from accounts.models import MemberProfile, Role

from . import whatsapp
from .models import DeliveryStatus, Message
from .services import send
from .whatsapp import WhatsAppError, send_template, send_text

User = get_user_model()

WA_SETTINGS = {
    "WHATSAPP_TOKEN": "tok_test",
    "WHATSAPP_PHONE_NUMBER_ID": "123456",
    "WHATSAPP_APP_SECRET": "app_secret",
}


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no JSON object could be decoded")
        return self._payload


def sent_ok(wamid="wamid.OK1"):
    return FakeResponse(200, {"messages": [{"id": wamid}]})


@override_settings(**WA_SETTINGS)
class WhatsAppClientTests(TenantAPIMixin, APITestCase):
    @patch("messaging.whatsapp.requests.post")
    def test_a_successful_send_returns_metas_message_id(self, post):
        post.return_value = sent_ok("wamid.ABC")
        self.assertEqual(send_text("919000000000", "hello"), "wamid.ABC")

    @patch("messaging.whatsapp.requests.post")
    def test_a_timeout_becomes_a_readable_error(self, post):
        post.side_effect = requests.Timeout("timed out")
        with self.assertRaises(WhatsAppError) as caught:
            send_text("919000000000", "hello")
        self.assertIn("Could not reach WhatsApp", str(caught.exception))

    @patch("messaging.whatsapp.requests.post")
    def test_metas_own_wording_is_surfaced_on_a_rejection(self, post):
        # "Re-engagement message outside the 24 hour window" is actionable;
        # "WhatsApp rejected that message" is not.
        post.return_value = FakeResponse(
            400, {"error": {"message": "Re-engagement message outside window"}}
        )
        with self.assertRaises(WhatsAppError) as caught:
            send_text("919000000000", "hello")
        self.assertEqual(str(caught.exception), "Re-engagement message outside window")

    @patch("messaging.whatsapp.requests.post")
    def test_a_rejection_with_no_readable_body_still_fails_cleanly(self, post):
        post.return_value = FakeResponse(500, payload=None)
        with self.assertRaises(WhatsAppError) as caught:
            send_text("919000000000", "hello")
        self.assertEqual(str(caught.exception), "WhatsApp rejected that message.")

    @patch("messaging.whatsapp.requests.post")
    def test_a_success_with_no_message_id_is_not_a_crash(self, post):
        # Meta has answered 200 with an empty body before; an IndexError here
        # would turn a delivered message into a 500.
        post.return_value = FakeResponse(200, {})
        self.assertEqual(send_text("919000000000", "hello"), "")

    @override_settings(WHATSAPP_TOKEN="", WHATSAPP_PHONE_NUMBER_ID="")
    @patch("messaging.whatsapp.requests.post")
    def test_an_unconfigured_gym_never_calls_out(self, post):
        with self.assertRaises(WhatsAppError):
            send_text("919000000000", "hello")
        post.assert_not_called()

    @patch("messaging.whatsapp.requests.post")
    def test_a_long_body_is_trimmed_to_metas_limit(self, post):
        post.return_value = sent_ok()
        send_text("919000000000", "x" * 6000)
        self.assertEqual(len(post.call_args.kwargs["json"]["text"]["body"]), 4096)

    @patch("messaging.whatsapp.requests.post")
    def test_the_call_carries_a_timeout_and_the_token(self, post):
        post.return_value = sent_ok()
        send_text("919000000000", "hello")

        self.assertEqual(post.call_args.kwargs["timeout"], whatsapp.TIMEOUT)
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"], "Bearer tok_test"
        )

    @patch("messaging.whatsapp.requests.post")
    def test_a_template_send_carries_its_name_and_parameters(self, post):
        post.return_value = sent_ok("wamid.T")
        send_template("919000000000", "expiry_reminder", parameters=["Asha", "3"])

        body = post.call_args.kwargs["json"]
        self.assertEqual(body["type"], "template")
        self.assertEqual(body["template"]["name"], "expiry_reminder")
        self.assertEqual(
            [p["text"] for p in body["template"]["components"][0]["parameters"]],
            ["Asha", "3"],
        )

    @patch("messaging.whatsapp.requests.post")
    def test_a_template_with_no_parameters_omits_components_entirely(self, post):
        # Omitted, not sent as an empty list: Meta rejects `components: []`,
        # so a template with no placeholders must leave the key out.
        post.return_value = sent_ok()
        send_template("919000000000", "plain_notice")
        self.assertNotIn("components", post.call_args.kwargs["json"]["template"])

    @patch("messaging.whatsapp.requests.post")
    def test_a_template_failure_reports_metas_reason(self, post):
        post.return_value = FakeResponse(
            400, {"error": {"message": "Template name does not exist"}}
        )
        with self.assertRaises(WhatsAppError) as caught:
            send_template("919000000000", "no_such_template")
        self.assertEqual(str(caught.exception), "Template name does not exist")


@override_settings(**WA_SETTINGS)
class SendRecordsTheFailureTests(TenantAPIMixin, APITestCase):
    """A failed send has to leave a trace, since nobody is watching it happen."""

    def setUp(self):
        self.member = User.objects.create_user(
            username="wa_member",
            email="wa@example.com",
            password="pass12345",
            role=Role.MEMBER,
        )
        MemberProfile.objects.get_or_create(user=self.member)
        MemberProfile.objects.filter(user=self.member).update(phone="919000000000")

    @patch("messaging.whatsapp.requests.post")
    def test_a_rejected_send_is_logged_as_failed_with_the_reason(self, post):
        post.return_value = FakeResponse(
            400, {"error": {"message": "Recipient not on WhatsApp"}}
        )
        message = send("919000000000", "Your membership expires soon")

        self.assertEqual(message.status, DeliveryStatus.FAILED)
        self.assertEqual(message.error, "Recipient not on WhatsApp")
        # Still recorded, so the front desk can see it was attempted.
        self.assertTrue(Message.objects.filter(pk=message.pk).exists())

    @patch("messaging.whatsapp.requests.post")
    def test_an_unreachable_meta_is_logged_as_failed(self, post):
        post.side_effect = requests.ConnectionError("no route to host")
        message = send("919000000000", "Your membership expires soon")

        self.assertEqual(message.status, DeliveryStatus.FAILED)
        self.assertIn("Could not reach WhatsApp", message.error)

    @patch("messaging.whatsapp.requests.post")
    def test_a_successful_send_records_the_external_id(self, post):
        post.return_value = sent_ok("wamid.SENT")
        message = send("919000000000", "hello")

        self.assertEqual(message.status, DeliveryStatus.SENT)
        self.assertEqual(message.external_id, "wamid.SENT")
        self.assertEqual(message.error, "")

    @patch("messaging.whatsapp.requests.post")
    def test_a_very_long_error_is_truncated_rather_than_overflowing(self, post):
        # `error` is a 300-char column; an unbounded upstream message would
        # turn a failed send into a database error on top of it.
        post.return_value = FakeResponse(400, {"error": {"message": "e" * 800}})
        message = send("919000000000", "hello")

        self.assertEqual(message.status, DeliveryStatus.FAILED)
        self.assertLessEqual(len(message.error), 300)

    @override_settings(WHATSAPP_TOKEN="", WHATSAPP_PHONE_NUMBER_ID="")
    @patch("messaging.whatsapp.requests.post")
    def test_an_unconfigured_gym_records_the_failure_without_calling_out(self, post):
        message = send("919000000000", "hello")

        self.assertEqual(message.status, DeliveryStatus.FAILED)
        self.assertIn("configured", message.error)
        post.assert_not_called()


@override_settings(**WA_SETTINGS)
class DeliveryStatusCallbackTests(TenantAPIMixin, APITestCase):
    """Meta's asynchronous delivery receipts, which nothing currently reads.

    KNOWN GAP, pinned here rather than left silent. `parse_incoming` yields
    only `messages[]`; the `statuses[]` array arriving on the same endpoint --
    carrying delivered / read / failed with an error code -- is walked past.

    So `Message.status` reflects whether Meta *accepted* the send, not whether
    it was delivered. A number that is not on WhatsApp, a member who blocked
    the business, or a template rejected after acceptance all leave the row
    reading "sent" for ever, and the reminder looks like it worked.

    These tests assert the behaviour as it stands. If the statuses array is
    ever wired up they will fail, which is the point: they are a marker, not
    an endorsement.
    """

    def setUp(self):
        self.member = User.objects.create_user(
            username="cb_member", email="cb@example.com", password="pass12345", role=Role.MEMBER
        )
        MemberProfile.objects.get_or_create(user=self.member)

    def _post_hook(self, body):
        raw = json.dumps(body).encode()
        signature = hmac.new(
            WA_SETTINGS["WHATSAPP_APP_SECRET"].encode(), raw, hashlib.sha256
        ).hexdigest()
        return self.client.post(
            "/api/whatsapp/webhook/",
            data=raw,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=f"sha256={signature}",
        )

    @patch("messaging.whatsapp.requests.post")
    def _sent_message(self, post):
        post.return_value = sent_ok("wamid.TRACKED")
        return send("919000000000", "Your membership expires soon")

    def test_a_failed_delivery_receipt_does_not_reach_the_message(self):
        message = self._sent_message()
        self.assertEqual(message.status, DeliveryStatus.SENT)

        resp = self._post_hook(
            {
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "statuses": [
                                        {
                                            "id": "wamid.TRACKED",
                                            "status": "failed",
                                            "errors": [{"title": "Recipient not on WhatsApp"}],
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ]
            }
        )

        self.assertEqual(resp.status_code, 200)
        message.refresh_from_db()
        # Still "sent". Wiring up statuses[] would make this "failed".
        self.assertEqual(message.status, DeliveryStatus.SENT)
        self.assertEqual(message.error, "")

    def test_a_status_callback_is_acknowledged_so_meta_stops_retrying(self):
        # The one thing that is right today: answering 200 rather than an
        # error, so Meta does not redeliver a receipt for ever.
        resp = self._post_hook(
            {"entry": [{"changes": [{"value": {"statuses": [{"status": "delivered"}]}}]}]}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["handled"], 0)

    def test_an_unsigned_status_callback_is_still_refused(self):
        # The signature check runs before any of this, so a forged receipt
        # cannot reach the handler even once statuses are wired up.
        resp = self.client.post(
            "/api/whatsapp/webhook/",
            data=json.dumps({"entry": []}).encode(),
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256="sha256=forged",
        )
        self.assertEqual(resp.status_code, 400)
