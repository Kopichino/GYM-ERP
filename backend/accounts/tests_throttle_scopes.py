"""Throttle buckets for signed-out traffic, kept apart by what they protect.

Before: the refresh endpoint, the public branding and the public price list all
drew on DRF's one anonymous bucket -- 100 requests an hour per IP -- and a
signed-out page load spent three refreshes plus the branding and plans from it.
A gym's members share one internet connection, so a busy hour of people opening
the website emptied the bucket. Every refresh after that was a 429, and a
signed-in member who reloaded the page was sent back to the login screen.
"""

from http.cookies import SimpleCookie
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework.settings import api_settings
from rest_framework.test import APITestCase
from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from billing.views import PublicPlanListView
from branding.views import PublicBrandingView
from core.testing import TenantAPIMixin

from .models import MemberProfile, Role
from .views import RefreshView

User = get_user_model()

#: Everybody at the gym shares the gym's connection.
GYM_WIFI = "203.0.113.50"


def rates(**overrides):
    """Shrink named rates for one test. DRF reads the table off the class."""
    return mock.patch.object(
        SimpleRateThrottle,
        "THROTTLE_RATES",
        {**api_settings.DEFAULT_THROTTLE_RATES, **overrides},
    )


@override_settings(MFA_REQUIRED=False)
class SignedOutTrafficTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        cache.clear()
        self.member = self._member("regular")
        self.other_member = self._member("another")

    def tearDown(self):
        cache.clear()

    def _member(self, username):
        user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password="pass12345"
        )
        MemberProfile.objects.get_or_create(user=user)
        self.member_for(user, Role.MEMBER)
        return user

    def signed_out_page_load(self):
        """What the website sends before anyone is known: one refresh attempt,
        the branding, and the price list."""
        self.client.cookies = SimpleCookie()
        return [
            self.client.post("/api/auth/refresh/", REMOTE_ADDR=GYM_WIFI).status_code,
            self.client.get("/api/branding/", REMOTE_ADDR=GYM_WIFI).status_code,
            self.client.get("/api/billing/public/plans/", REMOTE_ADDR=GYM_WIFI).status_code,
        ]

    def refresh_with_session(self, user):
        self.client.cookies = SimpleCookie()
        self.client.cookies["refresh_token"] = str(RefreshToken.for_user(user))
        return self.client.post("/api/auth/refresh/", REMOTE_ADDR=GYM_WIFI)

    def wrong_login(self, username="nobody"):
        return self.client.post(
            "/api/auth/login/",
            {"username": username, "password": "wrong-password"},
            REMOTE_ADDR=GYM_WIFI,
        )

    # -- the audit's failure

    def test_a_busy_hour_of_signed_out_visitors_does_not_sign_members_out(self):
        for _ in range(50):
            statuses = self.signed_out_page_load()
            self.assertNotIn(429, statuses[1:], "public branding/plans were throttled")
        resp = self.refresh_with_session(self.member)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIn("access", resp.data)

    # -- abuse is still throttled, each kind in its own bucket

    def test_refresh_attempts_without_a_session_are_throttled(self):
        self.client.cookies = SimpleCookie()
        statuses = {
            self.client.post("/api/auth/refresh/", REMOTE_ADDR=GYM_WIFI).status_code
            for _ in range(40)
        }
        self.assertEqual(statuses, {401, 429})

    def test_one_session_hammering_refresh_is_throttled_without_touching_others(self):
        with rates(refresh="3/min"):
            self.client.cookies = SimpleCookie()
            self.client.cookies["refresh_token"] = str(RefreshToken.for_user(self.member))
            # The cookie is rotated on each success; the client keeps the new one.
            statuses = [
                self.client.post("/api/auth/refresh/", REMOTE_ADDR=GYM_WIFI).status_code
                for _ in range(4)
            ]
            self.assertEqual(statuses, [200, 200, 200, 429])
            self.assertEqual(self.refresh_with_session(self.other_member).status_code, 200)

    def test_login_brute_force_is_still_throttled_after_heavy_public_traffic(self):
        for _ in range(50):
            self.signed_out_page_load()
        statuses = [self.wrong_login(f"guess{n}").status_code for n in range(12)]
        self.assertIn(429, statuses)

    def test_public_traffic_cannot_spend_the_login_or_refresh_allowance(self):
        with rates(public="2/min"):
            statuses = [self.client.get("/api/branding/", REMOTE_ADDR=GYM_WIFI).status_code for _ in range(3)]
            self.assertEqual(statuses, [200, 200, 429])
            self.assertEqual(
                self.client.get("/api/billing/public/plans/", REMOTE_ADDR=GYM_WIFI).status_code, 429
            )
            self.assertEqual(self.wrong_login().status_code, 401)
            self.assertEqual(self.refresh_with_session(self.member).status_code, 200)

    def test_refresh_traffic_cannot_spend_the_public_or_login_allowance(self):
        with rates(refresh_anonymous="2/min"):
            self.client.cookies = SimpleCookie()
            statuses = [
                self.client.post("/api/auth/refresh/", REMOTE_ADDR=GYM_WIFI).status_code
                for _ in range(3)
            ]
            self.assertEqual(statuses, [401, 401, 429])
            self.assertEqual(self.client.get("/api/branding/", REMOTE_ADDR=GYM_WIFI).status_code, 200)
            self.assertEqual(
                self.client.get("/api/billing/public/plans/", REMOTE_ADDR=GYM_WIFI).status_code, 200
            )
            self.assertEqual(self.wrong_login().status_code, 401)

    def test_switching_between_password_endpoints_shares_one_allowance(self):
        """Moving from login to signup must not buy a fresh budget."""
        with rates(login="3/min", login_attempt="100/min"):
            self.wrong_login("first")
            self.wrong_login("second")
            self.client.post(
                "/api/auth/signup/", {"username": "x", "password": "short"}, REMOTE_ADDR=GYM_WIFI
            )
            self.assertEqual(self.wrong_login("third").status_code, 429)

    def test_signed_in_requests_do_not_depend_on_the_signed_out_buckets(self):
        with rates(public="1/min", refresh_anonymous="1/min", anon="1/min"):
            for _ in range(2):
                self.client.get("/api/branding/", REMOTE_ADDR=GYM_WIFI)
                self.client.cookies = SimpleCookie()
                self.client.post("/api/auth/refresh/", REMOTE_ADDR=GYM_WIFI)
            access = RefreshToken.for_user(self.member).access_token
            resp = self.client.get(
                "/api/auth/me/", HTTP_AUTHORIZATION=f"Bearer {access}", REMOTE_ADDR=GYM_WIFI
            )
            self.assertEqual(resp.status_code, 200)


class ThrottleConfigurationTests(APITestCase):
    def test_signed_out_endpoints_are_not_on_the_shared_anonymous_bucket(self):
        for view in (RefreshView, PublicBrandingView, PublicPlanListView):
            with self.subTest(view=view.__name__):
                classes = view().get_throttles()
                self.assertFalse(any(isinstance(t, AnonRateThrottle) for t in classes))

    def test_each_signed_out_bucket_has_its_own_rate(self):
        configured = api_settings.DEFAULT_THROTTLE_RATES
        for scope in ("refresh", "refresh_anonymous", "public", "login", "login_attempt", "mfa"):
            with self.subTest(scope=scope):
                self.assertTrue(configured.get(scope))
