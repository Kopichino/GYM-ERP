"""Security events are recorded -- and never with the secret involved.

Each test performs the action for real and reads what reached the `security`
logger: that the event is there, named and attributed, and that the password,
code, token or signature involved is not.
"""

import io
import json
import logging
from datetime import timedelta

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import path
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import MfaDevice, Role
from core.security_log import security_event

from .testing import PASSWORD, TwoGymsTestCase, make_person


class SecurityEventHelperTests(SimpleTestCase):
    def test_fields_outside_the_allowlist_are_dropped(self):
        with self.assertLogs("security", level="INFO") as logs:
            security_event(
                "probe", user=7, password="hunter2-secret", token="eyJ.secret.part", code="482913"
            )
        line = logs.output[0]
        self.assertIn("security_event=probe", line)
        self.assertIn("user=7", line)
        for secret in ("hunter2-secret", "eyJ.secret.part", "482913"):
            self.assertNotIn(secret, line)

    def test_a_value_cannot_forge_a_second_log_line(self):
        with self.assertLogs("security", level="INFO") as logs:
            security_event("probe", username="mallory\nsecurity_event=login_succeeded user=1")
        self.assertEqual(len(logs.records), 1)
        self.assertNotIn("\n", logs.records[0].getMessage())


@override_settings(MFA_REQUIRED=False)
class AuthenticationEventTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = make_person("watched")

    def tearDown(self):
        cache.clear()

    def test_a_failed_login_is_recorded_without_the_password(self):
        with self.assertLogs("security", level="WARNING") as logs:
            resp = self.client.post(
                "/api/auth/login/", {"username": "watched", "password": "wrong-guess-7731"}
            )
        self.assertEqual(resp.status_code, 401)
        joined = "\n".join(logs.output)
        self.assertIn("security_event=login_failed", joined)
        self.assertIn("username=watched", joined)
        self.assertNotIn("wrong-guess-7731", joined)

    def test_a_wrong_authenticator_code_is_recorded_without_the_code(self):
        MfaDevice.objects.create(
            user=self.user, secret="JBSWY3DPEHPK3PXP", confirmed_at=timezone.now()
        )
        step = self.client.post("/api/auth/login/", {"username": "watched", "password": PASSWORD})
        pending = step.data["mfa_token"]
        with self.assertLogs("security", level="WARNING") as logs:
            resp = self.client.post(
                "/api/auth/mfa/login/verify/", {"mfa_token": pending, "code": "990011"}
            )
        self.assertEqual(resp.status_code, 400)
        joined = "\n".join(logs.output)
        self.assertIn("security_event=mfa_code_failed", joined)
        self.assertIn(f"user={self.user.pk}", joined)
        for secret in ("990011", "JBSWY3DPEHPK3PXP", pending):
            self.assertNotIn(secret, joined)

    def test_a_replayed_refresh_token_is_recorded_without_the_token(self):
        stolen = str(RefreshToken.for_user(self.user))
        self.client.cookies["refresh_token"] = stolen
        self.assertEqual(self.client.post("/api/auth/refresh/").status_code, 200)
        jti = RefreshToken(stolen, verify=False)["jti"]
        BlacklistedToken.objects.filter(token__jti=jti).update(
            blacklisted_at=timezone.now() - timedelta(minutes=10)
        )
        self.client.cookies["refresh_token"] = stolen
        with self.assertLogs("security", level="WARNING") as logs:
            self.assertEqual(self.client.post("/api/auth/refresh/").status_code, 401)
        joined = "\n".join(logs.output)
        self.assertIn("security_event=refresh_token_replayed", joined)
        self.assertNotIn(stolen, joined)


class AdminActionEventTests(TwoGymsTestCase):
    def test_an_admin_setting_a_password_is_recorded_without_it(self):
        admin = make_person("admin_a", gym=self.gym_a, role=Role.ADMIN)
        member = make_person("member_a", gym=self.gym_a)
        self.sign_in(admin)
        with self.assertLogs("security", level="INFO") as logs:
            resp = self.client.post(
                f"{self.at(self.gym_a)}/auth/admin/members/{member.pk}/set-password/",
                {"password": "a-brand-new-passphrase-99"},
            )
        self.assertEqual(resp.status_code, 200)
        joined = "\n".join(logs.output)
        self.assertIn("security_event=password_set_by_admin", joined)
        self.assertIn(f"target={member.pk}", joined)
        self.assertIn(f"tenant={self.gym_a.slug}", joined)
        self.assertNotIn("a-brand-new-passphrase-99", joined)


@override_settings(
    RAZORPAY_KEY_ID="rzp_test_key",
    RAZORPAY_KEY_SECRET="rzp_test_secret",
    RAZORPAY_WEBHOOK_SECRET="hook_secret_value",
)
class WebhookEventTests(APITestCase):
    def test_a_forged_webhook_is_recorded_without_the_signature_or_secret(self):
        body = json.dumps({"event": "payment.captured"})
        with self.assertLogs("security", level="WARNING") as logs:
            resp = self.client.post(
                "/api/billing/online/webhook/",
                data=body,
                content_type="application/json",
                HTTP_X_RAZORPAY_SIGNATURE="forged-signature-abc123",
            )
        self.assertEqual(resp.status_code, 400)
        joined = "\n".join(logs.output)
        self.assertIn("security_event=webhook_signature_invalid", joined)
        self.assertNotIn("forged-signature-abc123", joined)
        self.assertNotIn("hook_secret_value", joined)


def _fails(request):
    raise RuntimeError("request-error-probe")


urlpatterns = [path("fails/", _fails)]


@override_settings(ROOT_URLCONF=__name__)
class RequestErrorVisibilityTests(TestCase):
    """An unhandled 500 in production reaches the log stream.

    Django prints request errors only with DEBUG on and otherwise mails ADMINS,
    which is empty -- so without Sentry a production 500 left no trace at all.
    """

    def setUp(self):
        self.handler = next(
            h for h in logging.getLogger("django.request").handlers if h.name == "request_errors"
        )
        self.stream = io.StringIO()
        previous = self.handler.setStream(self.stream)
        self.addCleanup(self.handler.setStream, previous)
        self.client.raise_request_exception = False

    @override_settings(DEBUG=False)
    def test_an_unhandled_error_is_written_with_its_traceback(self):
        resp = self.client.get("/fails/?token=query-string-secret")
        self.assertEqual(resp.status_code, 500)
        written = self.stream.getvalue()
        self.assertIn("Internal Server Error: /fails/", written)
        self.assertIn("RuntimeError: request-error-probe", written)
        # The path is logged, never the query string.
        self.assertNotIn("query-string-secret", written)

    def test_nothing_is_added_while_debug_prints_it_already(self):
        record = logging.LogRecord(
            "django.request", logging.ERROR, __file__, 0, "Internal Server Error: /x/", None, None
        )
        with override_settings(DEBUG=True):
            self.assertFalse(self.handler.filter(record))
        with override_settings(DEBUG=False):
            self.assertTrue(self.handler.filter(record))

    @override_settings(DEBUG=False)
    def test_a_client_error_is_not_written(self):
        resp = self.client.get("/no-such-page/")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(self.stream.getvalue(), "")
