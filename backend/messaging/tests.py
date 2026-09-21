import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin, enrol

from accounts.models import MemberProfile, Role
from billing.models import PaymentMethod, Plan
from billing.services import record_payment

from .assistant import HELP, answer, member_for_phone
from .models import DeliveryStatus, Direction, Message, normalise_phone
from .services import handle_incoming, send
from .whatsapp import verify_signature, verify_subscription

User = get_user_model()

APP_SECRET = "meta_app_secret"
VERIFY_TOKEN = "chosen-by-us"

WHATSAPP_SETTINGS = {
    "WHATSAPP_TOKEN": "tok",
    "WHATSAPP_PHONE_NUMBER_ID": "123456",
    "WHATSAPP_APP_SECRET": APP_SECRET,
    "WHATSAPP_VERIFY_TOKEN": VERIFY_TOKEN,
    "ANTHROPIC_API_KEY": "",
}


def make_member(username, phone="+91 98200 11122"):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=Role.MEMBER
    )
    MemberProfile.objects.update_or_create(user=user, defaults={"phone": phone})
    enrol(user)
    return user


class PhoneMatchingTests(TenantAPIMixin, APITestCase):
    """A number written six ways still has to find one member."""

    def setUp(self):
        self.member = make_member("dialler", phone="+91 98200 11122")

    def test_digits_only(self):
        self.assertEqual(normalise_phone("+91 98200-11122"), "919820011122")

    def test_whatsapps_format_finds_the_member(self):
        self.assertEqual(member_for_phone("919820011122"), self.member)

    def test_a_local_format_finds_the_same_member(self):
        self.assertEqual(member_for_phone("98200 11122"), self.member)

    def test_a_different_number_finds_nobody(self):
        self.assertIsNone(member_for_phone("919999900000"))

    def test_too_few_digits_is_not_a_fuzzy_match(self):
        self.assertIsNone(member_for_phone("11122"))


@override_settings(**WHATSAPP_SETTINGS)
class AssistantTests(TenantAPIMixin, APITestCase):
    """Answers come from the same data the portal shows."""

    def setUp(self):
        self.member = make_member("asker")
        self.plan = Plan.objects.create(
            name="Monthly", price=Decimal("1500"), duration_days=30
        )

    def test_membership_question_quotes_the_ledger(self):
        record_payment(
            member=self.member,
            plan=self.plan,
            amount=self.plan.price,
            method=PaymentMethod.CASH,
        )
        reply = answer("when does my membership expire?", "919820011122")
        self.assertIn("Monthly", reply)
        self.assertIn("30 day", reply)

    def test_a_member_with_no_plan_is_told_plainly(self):
        reply = answer("is my membership active?", "919820011122")
        self.assertIn("don't have a plan on file", reply)

    def test_an_expired_membership_says_so(self):
        record_payment(
            member=self.member,
            plan=self.plan,
            amount=self.plan.price,
            method=PaymentMethod.CASH,
            paid_date=timezone.localdate() - timedelta(days=40),
        )
        reply = answer("has my plan expired", "919820011122")
        self.assertIn("ran out", reply)

    def test_split_question_reads_the_active_split(self):
        from workouts.models import SplitDay, WorkoutSplit

        split = WorkoutSplit.objects.create(user=self.member, name="PPL")
        SplitDay.objects.create(
            split=split, weekday=timezone.localdate().weekday(), label="Push"
        )
        reply = answer("what am I training today?", "919820011122")
        self.assertIn("Push", reply)

    def test_split_question_with_no_split_points_at_the_page(self):
        self.assertIn("My Split", answer("what's my split", "919820011122"))

    def test_referral_question_returns_their_code(self):
        reply = answer("what's my referral code", "919820011122")
        self.assertIn("referral code is", reply)

    def test_an_unknown_number_is_treated_as_an_enquiry(self):
        reply = answer("do you do personal training?", "919111100000")
        self.assertIn("couldn't find a membership", reply)

    def test_an_unrecognised_question_falls_back_to_help_without_a_model(self):
        """With no API key nothing is invented -- the member gets the menu."""
        self.assertEqual(answer("what colour is the ceiling", "919820011122"), HELP)

    def test_an_empty_message_gets_the_help_text(self):
        self.assertEqual(answer("   ", "919820011122"), HELP)

    @override_settings(ANTHROPIC_API_KEY="sk-test")
    @patch("messaging.assistant.requests.post")
    def test_the_model_is_given_facts_not_database_access(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {
            "content": [{"type": "text", "text": "Sure -- ask the desk about that."}]
        }
        reply = answer("can I bring my dog", "919820011122")
        self.assertEqual(reply, "Sure -- ask the desk about that.")

        body = post.call_args.kwargs["json"]
        # Everything it is allowed to say was fetched before it was asked.
        self.assertIn("membership", body["messages"][0]["content"])
        self.assertIn("Answer ONLY from the facts given", body["system"])

    @override_settings(ANTHROPIC_API_KEY="sk-test")
    @patch("messaging.assistant.requests.post")
    def test_a_model_outage_degrades_to_the_help_text(self, post):
        post.side_effect = Exception("boom")
        # requests exceptions are caught; anything else would propagate, so the
        # assistant must not be handed a bare Exception. Use the real class.
        import requests

        post.side_effect = requests.RequestException("down")
        self.assertEqual(answer("anything at all", "919820011122"), HELP)


@override_settings(**WHATSAPP_SETTINGS)
class WebhookTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.member = make_member("chatter")

    def hook_body(self, text="hi", phone="919820011122", message_id="wamid.1"):
        return {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": phone,
                                        "id": message_id,
                                        "type": "text",
                                        "text": {"body": text},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }

    def post_hook(self, body, secret=APP_SECRET):
        raw = json.dumps(body)
        signature = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
        return self.client.post(
            "/api/whatsapp/webhook/",
            data=raw,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=f"sha256={signature}",
        )

    def test_subscription_handshake_echoes_the_challenge(self):
        resp = self.client.get(
            "/api/whatsapp/webhook/",
            {
                "hub.mode": "subscribe",
                "hub.verify_token": VERIFY_TOKEN,
                "hub.challenge": "12345",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content.decode(), "12345")

    def test_a_wrong_verify_token_is_refused(self):
        resp = self.client.get(
            "/api/whatsapp/webhook/",
            {"hub.mode": "subscribe", "hub.verify_token": "guess", "hub.challenge": "1"},
        )
        self.assertEqual(resp.status_code, 403)

    @patch("messaging.services.send_text", return_value="wamid.out")
    def test_an_incoming_message_is_logged_and_answered(self, send_text):
        resp = self.post_hook(self.hook_body("when does my membership expire"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["handled"], 1)

        inbound = Message.objects.get(direction=Direction.INBOUND)
        self.assertEqual(inbound.user, self.member)
        outbound = Message.objects.get(direction=Direction.OUTBOUND)
        self.assertTrue(outbound.is_automated)
        self.assertEqual(outbound.status, DeliveryStatus.SENT)

    @patch("messaging.services.send_text", return_value="wamid.out")
    def test_a_redelivered_webhook_is_answered_once(self, send_text):
        """Meta retries anything it thinks we didn't acknowledge."""
        self.post_hook(self.hook_body(message_id="wamid.same"))
        self.post_hook(self.hook_body(message_id="wamid.same"))
        self.assertEqual(Message.objects.filter(direction=Direction.INBOUND).count(), 1)
        self.assertEqual(send_text.call_count, 1)

    def test_an_unsigned_body_never_reaches_the_assistant(self):
        raw = json.dumps(self.hook_body())
        resp = self.client.post(
            "/api/whatsapp/webhook/", data=raw, content_type="application/json"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Message.objects.exists())

    def test_a_body_signed_with_the_wrong_secret_is_refused(self):
        resp = self.post_hook(self.hook_body(), secret="not-it")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Message.objects.exists())

    @override_settings(WHATSAPP_APP_SECRET="")
    def test_without_an_app_secret_nothing_is_waved_through(self):
        self.assertFalse(verify_signature(b"{}", "sha256=anything"))

    @patch("messaging.services.send_text", return_value="wamid.out")
    def test_a_non_text_message_is_acknowledged_and_skipped(self, send_text):
        body = self.hook_body()
        body["entry"][0]["changes"][0]["value"]["messages"][0]["type"] = "image"
        resp = self.post_hook(body)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["handled"], 0)
        send_text.assert_not_called()

    def test_a_delivery_receipt_webhook_is_not_treated_as_a_message(self):
        resp = self.post_hook({"entry": [{"changes": [{"value": {"statuses": [{}]}}]}]})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Message.objects.exists())


class SendTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.member = make_member("recipient")

    def test_an_unconfigured_gym_records_the_failure_rather_than_pretending(self):
        message = send("919820011122", "hello")
        self.assertEqual(message.status, DeliveryStatus.FAILED)
        self.assertIn("isn't configured", message.error)

    @override_settings(**WHATSAPP_SETTINGS)
    @patch("messaging.services.send_text", side_effect=Exception("nope"))
    def test_an_unexpected_error_is_not_swallowed(self, send_text):
        """Only WhatsAppError is handled; anything else is a bug worth seeing."""
        with self.assertRaises(Exception):
            send("919820011122", "hello")

    @override_settings(**WHATSAPP_SETTINGS)
    @patch("messaging.services.send_text", return_value="wamid.x")
    def test_a_sent_message_is_linked_to_the_member(self, send_text):
        message = send("919820011122", "hello")
        self.assertEqual(message.user, self.member)
        self.assertEqual(message.status, DeliveryStatus.SENT)
        self.assertEqual(message.external_id, "wamid.x")


@override_settings(**WHATSAPP_SETTINGS)
class ReminderTests(TenantAPIMixin, APITestCase):
    """The WhatsApp sweep shares its log with the email one."""

    def setUp(self):
        self.member = make_member("nudgee")
        self.plan = Plan.objects.create(
            name="Monthly", price=Decimal("1500"), duration_days=30
        )
        record_payment(
            member=self.member,
            plan=self.plan,
            amount=self.plan.price,
            method=PaymentMethod.CASH,
            paid_date=timezone.localdate() - timedelta(days=29),  # ends tomorrow
        )

    @patch("messaging.services.send_template", return_value="wamid.t")
    def test_a_due_member_is_messaged_once(self, send_template):
        from .services import send_expiry_reminders

        sent, _ = send_expiry_reminders()
        self.assertEqual(sent, 1)
        send_template.assert_called_once()

        sent_again, skipped = send_expiry_reminders()
        self.assertEqual((sent_again, skipped), (0, 1))

    @patch("messaging.services.send_template", return_value="wamid.t")
    def test_whatsapp_claiming_a_nudge_stops_the_email_one(self, send_template):
        from notifications.services import send_expiry_reminders as email_sweep

        from .services import send_expiry_reminders as whatsapp_sweep

        whatsapp_sweep()
        # The email sweep sees the nudge as already sent for today.
        self.assertEqual(email_sweep()[0], 0)

    @patch("messaging.services.send_template", return_value="wamid.t")
    def test_a_member_with_no_number_is_skipped(self, send_template):
        from .services import send_expiry_reminders

        MemberProfile.objects.filter(user=self.member).update(phone="")
        sent, skipped = send_expiry_reminders()
        self.assertEqual((sent, skipped), (0, 1))
        send_template.assert_not_called()


class VerifySubscriptionTests(TenantAPIMixin, APITestCase):
    @override_settings(WHATSAPP_VERIFY_TOKEN=VERIFY_TOKEN)
    def test_the_right_token_returns_the_challenge(self):
        self.assertEqual(verify_subscription("subscribe", VERIFY_TOKEN, "abc"), "abc")

    @override_settings(WHATSAPP_VERIFY_TOKEN="")
    def test_an_unset_token_refuses_rather_than_matching_blank(self):
        self.assertIsNone(verify_subscription("subscribe", "", "abc"))


@override_settings(**WHATSAPP_SETTINGS)
class MessageLogApiTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="msgadmin", email="ma@example.com", password="pass12345", role=Role.ADMIN
        )
        self.member = make_member("logged")
        Message.objects.create(
            phone="919820011122", direction=Direction.INBOUND, body="hi", user=self.member
        )

    def test_members_cannot_read_the_log(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get("/api/whatsapp/messages/").status_code, 403)

    def test_an_admin_reads_the_log(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get("/api/whatsapp/messages/")
        self.assertEqual(resp.data["count"], 1)

    def test_the_log_can_be_filtered_to_one_number(self):
        Message.objects.create(phone="919000000000", direction=Direction.INBOUND, body="x")
        self.client.force_authenticate(self.admin)
        resp = self.client.get("/api/whatsapp/messages/?phone=98200 11122")
        self.assertEqual(resp.data["count"], 1)

    @patch("messaging.services.send_text", return_value="wamid.m")
    def test_the_desk_can_reply_by_hand(self, send_text):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/whatsapp/messages/send/", {"phone": "919820011122", "body": "See you at 7."}
        )
        self.assertEqual(resp.status_code, 201)
        self.assertFalse(resp.data["is_automated"])

    def test_status_says_whether_it_is_connected(self):
        self.client.force_authenticate(self.admin)
        self.assertTrue(self.client.get("/api/whatsapp/status/").data["enabled"])
