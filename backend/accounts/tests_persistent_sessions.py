"""Staying signed in: normal, "remember me" and "trust this device" sessions.

The browser holds one httpOnly cookie, the refresh token. Everything here is a
question about that one mechanism -- how long it lasts, what is written down
about it on the server, and what ends it -- not a second way of signing in.

Three kinds of session, each with a hard ceiling counted from the moment of
login. Using a session does *not* extend it: a rotation hands out a new token
that expires at the same instant as the last, so an open tab left running cannot
keep a stolen session alive for ever.

    normal    AUTH_SESSION_MAX_AGE          7 days
    remember  AUTH_REMEMBER_ME_MAX_AGE      30 days
    trusted   AUTH_TRUSTED_DEVICE_MAX_AGE   90 days

Time is faked by moving both clocks the code reads (Django's and SimpleJWT's)
rather than by editing rows, so a test that says "31 days later" really has.
"""

import hashlib
from contextlib import contextmanager
from datetime import timedelta
from importlib import reload
from unittest import mock

from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.state import token_backend
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from accounts import mfa
from accounts.models import MfaDevice
from security.testing import PASSWORD, make_person

DAY = 24 * 60 * 60
CHROME_WIN = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
SAFARI_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
FIREFOX_LINUX = "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0"
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
COOKIE = settings.JWT_REFRESH_COOKIE_NAME


@contextmanager
def time_travel(**delta):
    """Everything that reads the clock sees `delta` later than it really is."""
    from rest_framework_simplejwt import utils

    shift = timedelta(**delta)
    real_now, real_utc = timezone.now, utils.aware_utcnow
    with (
        mock.patch("django.utils.timezone.now", lambda: real_now() + shift),
        mock.patch("rest_framework_simplejwt.tokens.aware_utcnow", lambda: real_utc() + shift),
    ):
        yield


def claims(raw):
    """A refresh token's claims, signature and expiry deliberately unchecked."""
    return token_backend.decode(raw, verify=False)


def auth_session_model():
    # Looked up lazily so that, before the feature exists, only the tests that
    # need it fail -- not every test in this module at import time.
    return apps.get_model("accounts", "AuthSession")


class SessionBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = make_person("sam")

    # -- doing things ---------------------------------------------------------

    def login(self, client=None, *, remember=None, trust=None, ua=CHROME_WIN, username="sam", password=PASSWORD):
        client = client or self.client
        body = {"username": username, "password": password}
        if remember is not None:
            body["remember_me"] = remember
        if trust is not None:
            body["trust_device"] = trust
        return client.post("/api/auth/login/", body, format="json", HTTP_USER_AGENT=ua)

    def refresh(self, client=None):
        client = client or self.client
        client.credentials()          # a refresh is made with the cookie alone
        return client.post("/api/auth/refresh/")

    def bearer(self, client, response):
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def logout(self, client, access):
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        return client.post("/api/auth/logout/")

    def reopen(self, client):
        """A browser quit and started again: only persistent cookies come back."""
        fresh = APIClient()
        for name, morsel in client.cookies.items():
            max_age = morsel["max-age"] or morsel["expires"]
            if max_age not in ("", None, 0, "0") and morsel.value:
                fresh.cookies[name] = morsel.value
        return fresh

    def raw_cookie(self, client_or_response):
        jar = getattr(client_or_response, "cookies")
        return jar[COOKIE].value

    # -- looking at things -----------------------------------------------------

    def rows(self, user=None):
        return list(auth_session_model().objects.filter(user=user or self.user).order_by("id"))

    def max_age(self, response):
        return int(response.cookies[COOKIE]["max-age"])

    def assertAbout(self, value, expected, tolerance=120):
        self.assertLess(abs(value - expected), tolerance, f"{value} is not within {tolerance} of {expected}")

    def age_blacklist(self, raw, seconds=600):
        """Pretend this refresh token was rotated long enough ago to be a theft, not a race."""
        jti = RefreshToken(raw, verify=False)["jti"]
        BlacklistedToken.objects.filter(token__jti=jti).update(blacklisted_at=timezone.now() - timedelta(seconds=seconds))


# =============================================================== configuration


class LifetimeConfigurationTests(TestCase):
    """The three ceilings are settings, validated, and never silently unlimited."""

    def test_the_defaults(self):
        self.assertEqual(settings.AUTH_SESSION_MAX_AGE, timedelta(days=7))
        self.assertEqual(settings.AUTH_REMEMBER_ME_MAX_AGE, timedelta(days=30))
        self.assertEqual(settings.AUTH_TRUSTED_DEVICE_MAX_AGE, timedelta(days=90))

    def test_trusted_outlasts_remembered_outlasts_normal(self):
        self.assertLess(settings.AUTH_SESSION_MAX_AGE, settings.AUTH_REMEMBER_ME_MAX_AGE)
        self.assertLess(settings.AUTH_REMEMBER_ME_MAX_AGE, settings.AUTH_TRUSTED_DEVICE_MAX_AGE)

    def test_the_access_token_is_not_made_long_lived(self):
        self.assertEqual(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"], timedelta(minutes=15))

    def test_the_library_default_follows_the_normal_ceiling(self):
        self.assertEqual(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"], settings.AUTH_SESSION_MAX_AGE)

    def test_a_sensible_set_is_accepted(self):
        from accounts.session_policy import validate_lifetimes

        validate_lifetimes(timedelta(days=1), timedelta(days=2), timedelta(days=3))
        validate_lifetimes(timedelta(days=7), timedelta(days=7), timedelta(days=7))

    def test_unsafe_sets_are_refused_rather_than_made_permanent(self):
        from accounts.session_policy import validate_lifetimes

        day = timedelta(days=1)
        unsafe = {
            "zero": (timedelta(0), day, day),
            "negative": (-day, day, day),
            "shorter than the access token's own purpose": (timedelta(minutes=5), day, day),
            "a remembered session shorter than a normal one": (day * 5, day * 2, day * 9),
            "a trusted device shorter than a remembered session": (day, day * 9, day * 2),
            "effectively permanent": (day, day * 30, day * 4000),
            "just over a year": (day, day * 30, day * 366),
            "not a duration": (7 * DAY, day, day),
            "None": (None, day, day),
        }
        for label, values in unsafe.items():
            with self.subTest(label):
                with self.assertRaises(ImproperlyConfigured):
                    validate_lifetimes(*values)

    def test_exactly_a_year_is_the_ceiling(self):
        from accounts.session_policy import validate_lifetimes

        validate_lifetimes(timedelta(days=7), timedelta(days=30), timedelta(days=365))

    def test_the_lifetime_for_a_kind_follows_the_current_setting(self):
        from accounts.session_policy import max_age_for

        self.assertEqual(max_age_for("normal"), timedelta(days=7))
        with override_settings(AUTH_REMEMBER_ME_MAX_AGE=timedelta(days=10)):
            self.assertEqual(max_age_for("remember"), timedelta(days=10))
        with override_settings(AUTH_TRUSTED_DEVICE_MAX_AGE=timedelta(days=45)):
            self.assertEqual(max_age_for("trusted"), timedelta(days=45))

    def test_an_unsafe_setting_is_refused_when_a_session_is_opened(self):
        from accounts.session_policy import max_age_for

        with override_settings(AUTH_TRUSTED_DEVICE_MAX_AGE=timedelta(days=4000)):
            with self.assertRaises(ImproperlyConfigured):
                max_age_for("trusted")
        with override_settings(AUTH_SESSION_MAX_AGE=timedelta(0)):
            with self.assertRaises(ImproperlyConfigured):
                max_age_for("normal")

    def test_an_unknown_kind_is_not_given_a_lifetime(self):
        from accounts.session_policy import max_age_for

        with self.assertRaises(ValueError):
            max_age_for("forever")

    def test_the_settings_module_refuses_an_unsafe_environment_at_boot(self):
        import gymerp.settings as settings_module

        for name, value in (
            ("AUTH_SESSION_MAX_AGE", "0"),
            ("AUTH_REMEMBER_ME_MAX_AGE", str(400 * DAY)),
            ("AUTH_TRUSTED_DEVICE_MAX_AGE", str(60)),
        ):
            with self.subTest(name):
                with self.assertRaises(ImproperlyConfigured):
                    self._reload_with(settings_module, **{name: value})

    def test_the_environment_can_change_the_defaults(self):
        import gymerp.settings as settings_module

        seen = self._reload_with(
            settings_module,
            read=("AUTH_REMEMBER_ME_MAX_AGE",),
            AUTH_REMEMBER_ME_MAX_AGE=str(14 * DAY),
        )
        self.assertEqual(seen["AUTH_REMEMBER_ME_MAX_AGE"], timedelta(days=14))

    def _reload_with(self, settings_module, read=(), **env):
        import os

        previous = {key: os.environ.get(key) for key in env}
        os.environ.update(env)
        try:
            reload(settings_module)
            return {name: getattr(settings_module, name) for name in read}
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            reload(settings_module)


# ============================================================== normal session


@override_settings(MFA_REQUIRED=False)
class NormalSessionTests(SessionBase):
    def test_login_without_either_option_succeeds(self):
        resp = self.login()
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIn("access", resp.data)
        self.assertNotIn("refresh", resp.data)
        self.assertIn(COOKIE, resp.cookies)

    def test_the_cookie_outlives_the_browser_for_the_normal_period(self):
        resp = self.login()
        self.assertAbout(self.max_age(resp), 7 * DAY)

    def test_it_is_recorded_as_a_normal_session_ending_at_the_ceiling(self):
        before = timezone.now()
        self.login()
        (row,) = self.rows()
        self.assertEqual(row.kind, "normal")
        self.assertAbout((row.expires_at - before).total_seconds(), 7 * DAY)
        self.assertIsNone(row.revoked_at)

    def test_it_survives_the_browser_restarting(self):
        self.login()
        reopened = self.reopen(self.client)
        resp = self.refresh(reopened)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIn("access", resp.data)

    def test_rotating_hands_out_a_new_token_that_ends_at_the_same_instant(self):
        first = self.login()
        (row,) = self.rows()
        ends = int(row.expires_at.timestamp())
        self.assertEqual(claims(self.raw_cookie(first))["exp"], ends)

        second = self.refresh(self.client)
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(self.raw_cookie(second), self.raw_cookie(first))
        self.assertEqual(claims(self.raw_cookie(second))["exp"], ends)
        row.refresh_from_db()
        self.assertEqual(int(row.expires_at.timestamp()), ends)

    def test_using_a_session_does_not_extend_it(self):
        self.login()
        with time_travel(days=3):
            resp = self.refresh(self.client)
        self.assertEqual(resp.status_code, 200)
        self.assertAbout(self.max_age(resp), 4 * DAY)          # not another seven

    def test_it_expires_once_its_maximum_age_has_passed(self):
        self.login()
        with time_travel(days=7, minutes=2):
            resp = self.refresh(self.client)
        self.assertEqual(resp.status_code, 401)

    def test_it_is_still_good_just_before_the_ceiling(self):
        self.login()
        with time_travel(days=6, hours=23):
            self.assertEqual(self.refresh(self.client).status_code, 200)

    def test_a_cookie_that_outlives_its_session_is_removed(self):
        self.login()
        (row,) = self.rows()
        auth_session_model().objects.filter(pk=row.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        resp = self.refresh(self.client)
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(int(resp.cookies[COOKIE]["max-age"]), 0)

    def test_the_cookie_expires_in_the_browser_at_the_same_instant_as_the_session(self):
        """So an expired token never needs removing: the browser has already dropped it."""
        resp = self.login()
        (row,) = self.rows()
        self.assertAbout(self.max_age(resp), (row.expires_at - timezone.now()).total_seconds(), 5)

    def test_the_server_enforces_the_ceiling_whatever_the_token_says(self):
        self.login()
        (row,) = self.rows()
        auth_session_model().objects.filter(pk=row.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        resp = self.refresh(self.client)
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.data.get("reason"), "session_expired")

    def test_after_expiry_signing_in_again_works(self):
        self.login()
        with time_travel(days=8):
            self.assertEqual(self.refresh(self.client).status_code, 401)
            again = self.login(APIClient())
        self.assertEqual(again.status_code, 200)

    def test_changing_the_setting_changes_how_long_a_session_lasts(self):
        with override_settings(AUTH_SESSION_MAX_AGE=timedelta(days=2)):
            resp = self.login()
            self.assertAbout(self.max_age(resp), 2 * DAY)
            with time_travel(days=2, minutes=2):
                self.assertEqual(self.refresh(self.client).status_code, 401)

    def test_a_stale_cookie_for_a_closed_account_gets_nothing(self):
        self.login()
        type(self.user).objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.refresh(self.client).status_code, 401)


# ================================================================= remember me


@override_settings(MFA_REQUIRED=False)
class RememberMeTests(SessionBase):
    def test_the_option_is_accepted(self):
        resp = self.login(remember=True)
        self.assertEqual(resp.status_code, 200, resp.content)
        (row,) = self.rows()
        self.assertEqual(row.kind, "remember")

    def test_the_option_is_read_strictly(self):
        for value, kind in (
            (True, "remember"), ("true", "remember"), ("1", "remember"), (1, "remember"),
            (False, "normal"), ("false", "normal"), ("0", "normal"), (0, "normal"),
            ("banana", "normal"), ("", "normal"), (None, "normal"), ([], "normal"),
        ):
            with self.subTest(value=value):
                auth_session_model().objects.all().delete()
                cache.clear()                    # twelve sign-ins would trip the login throttle
                self.login(APIClient(), remember=value)
                self.assertEqual([r.kind for r in self.rows()], [kind])

    def test_leaving_it_unticked_is_a_normal_session(self):
        self.login(remember=False)
        self.assertEqual(self.rows()[0].kind, "normal")

    def test_it_lasts_longer_than_a_normal_session(self):
        normal = self.login(APIClient())
        remembered = self.login(APIClient(), remember=True)
        self.assertAbout(self.max_age(remembered), 30 * DAY)
        self.assertGreater(self.max_age(remembered), self.max_age(normal) * 4)
        row = [r for r in self.rows() if r.kind == "remember"][0]
        self.assertAbout((row.expires_at - timezone.now()).total_seconds(), 30 * DAY)

    def test_it_survives_the_browser_restarting_and_a_long_absence(self):
        self.login(remember=True)
        reopened = self.reopen(self.client)
        with time_travel(days=20):
            self.assertEqual(self.refresh(reopened).status_code, 200)

    def test_it_ends_at_its_own_ceiling(self):
        self.login(remember=True)
        with time_travel(days=29, hours=23):
            self.assertEqual(self.refresh(self.client).status_code, 200)
        with time_travel(days=30, minutes=5):
            self.assertEqual(self.refresh(self.client).status_code, 401)

    def test_rotation_still_works_and_does_not_extend_it(self):
        first = self.login(remember=True)
        with time_travel(days=10):
            second = self.refresh(self.client)
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(self.raw_cookie(second), self.raw_cookie(first))
        self.assertAbout(self.max_age(second), 20 * DAY)

    def test_replaying_a_rotated_token_still_ends_every_session(self):
        first = self.login(remember=True)
        stolen = self.raw_cookie(first)
        newer = self.raw_cookie(self.refresh(self.client))
        self.age_blacklist(stolen)

        thief = APIClient()
        thief.cookies[COOKIE] = stolen
        self.assertEqual(self.refresh(thief).status_code, 401)
        owner = APIClient()
        owner.cookies[COOKIE] = newer
        self.assertEqual(self.refresh(owner).status_code, 401)
        self.assertTrue(all(r.revoked_at for r in self.rows()))

    def test_a_second_use_within_seconds_is_still_a_race_not_a_theft(self):
        first = self.login(remember=True)
        original = self.raw_cookie(first)
        newer = self.raw_cookie(self.refresh(self.client))
        late = APIClient()
        late.cookies[COOKIE] = original
        self.assertEqual(self.refresh(late).status_code, 401)
        survivor = APIClient()
        survivor.cookies[COOKIE] = newer
        self.assertEqual(self.refresh(survivor).status_code, 200)

    def test_it_can_be_revoked(self):
        self.login(remember=True)
        (row,) = self.rows()
        row.revoked_at = timezone.now()
        row.save(update_fields=["revoked_at"])
        resp = self.refresh(self.client)
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.data.get("reason"), "session_ended")

    def test_logging_out_invalidates_it(self):
        resp = self.login(remember=True)
        raw = self.raw_cookie(resp)
        out = self.logout(self.client, resp.data["access"])
        self.assertEqual(out.status_code, 204)
        (row,) = self.rows()
        self.assertIsNotNone(row.revoked_at)
        # The browser is told to drop it, and the server would refuse it anyway.
        self.assertEqual(int(out.cookies[COOKIE]["max-age"]), 0)
        stale = APIClient()
        stale.cookies[COOKIE] = raw
        self.assertEqual(self.refresh(stale).status_code, 401)

    def test_changing_the_setting_changes_the_remembered_period(self):
        with override_settings(AUTH_REMEMBER_ME_MAX_AGE=timedelta(days=12)):
            resp = self.login(remember=True)
            self.assertAbout(self.max_age(resp), 12 * DAY)


# ============================================================== trusted device


@override_settings(MFA_REQUIRED=False)
class TrustedDeviceTests(SessionBase):
    def test_trusting_a_device_records_a_device_session(self):
        resp = self.login(trust=True)
        self.assertEqual(resp.status_code, 200, resp.content)
        (row,) = self.rows()
        self.assertEqual(row.kind, "trusted")
        self.assertEqual(row.user, self.user)
        self.assertIsNone(row.revoked_at)
        self.assertEqual(row.label, "Chrome on Windows")
        self.assertIsNotNone(row.last_seen_at)
        self.assertAbout((row.expires_at - timezone.now()).total_seconds(), 90 * DAY)

    def test_only_a_hash_of_the_secret_is_kept(self):
        resp = self.login(trust=True)
        sid = claims(self.raw_cookie(resp))["sid"]
        (row,) = self.rows()
        self.assertEqual(row.secret_hash, hashlib.sha256(sid.encode()).hexdigest())
        self.assertNotEqual(row.secret_hash, sid)
        for field in row._meta.concrete_fields:
            self.assertNotIn(sid, str(getattr(row, field.attname)), field.name)

    def test_the_secret_is_long_random_and_different_every_time(self):
        a = claims(self.raw_cookie(self.login(APIClient(), trust=True)))["sid"]
        b = claims(self.raw_cookie(self.login(APIClient(), trust=True)))["sid"]
        self.assertNotEqual(a, b)
        self.assertGreaterEqual(len(a), 40)

    def test_nothing_identifying_is_stored_about_the_device_beyond_a_label(self):
        self.login(trust=True, ua=CHROME_WIN)
        names = {f.name for f in auth_session_model()._meta.concrete_fields}
        self.assertFalse({"ip", "ip_address", "user_agent", "raw_user_agent"} & names)
        (row,) = self.rows()
        self.assertNotIn("Mozilla", row.label)
        self.assertNotIn("120", row.label)

    def test_the_cookie_is_the_longest_of_the_three(self):
        trusted = self.login(APIClient(), trust=True)
        remembered = self.login(APIClient(), remember=True)
        normal = self.login(APIClient())
        self.assertAbout(self.max_age(trusted), 90 * DAY)
        self.assertGreater(self.max_age(trusted), self.max_age(remembered))
        self.assertGreater(self.max_age(remembered), self.max_age(normal))

    def test_it_survives_the_browser_restarting(self):
        self.login(trust=True)
        reopened = self.reopen(self.client)
        with time_travel(days=45):
            self.assertEqual(self.refresh(reopened).status_code, 200)

    def test_it_expires_at_the_configured_lifetime(self):
        self.login(trust=True)
        with time_travel(days=89, hours=23):
            self.assertEqual(self.refresh(self.client).status_code, 200)
        with time_travel(days=90, minutes=5):
            self.assertEqual(self.refresh(self.client).status_code, 401)

    def test_changing_the_setting_changes_the_trusted_lifetime(self):
        with override_settings(AUTH_TRUSTED_DEVICE_MAX_AGE=timedelta(days=40)):
            resp = self.login(trust=True)
            self.assertAbout(self.max_age(resp), 40 * DAY)
            with time_travel(days=40, minutes=5):
                self.assertEqual(self.refresh(self.client).status_code, 401)

    def test_ticking_both_boxes_gives_the_device_session(self):
        self.login(remember=True, trust=True)
        self.assertEqual(self.rows()[0].kind, "trusted")

    def test_rotation_keeps_the_device_identity_and_records_use(self):
        first = self.login(trust=True)
        sid = claims(self.raw_cookie(first))["sid"]
        (row,) = self.rows()
        with time_travel(days=1):
            second = self.refresh(self.client)
        self.assertEqual(claims(self.raw_cookie(second))["sid"], sid)
        row.refresh_from_db()
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(row.current_jti, claims(self.raw_cookie(second))["jti"])
        self.assertGreater(row.last_seen_at, timezone.now() + timedelta(hours=12))

    def test_it_can_be_revoked_on_its_own(self):
        self.login(trust=True)
        (row,) = self.rows()
        row.revoked_at = timezone.now()
        row.save(update_fields=["revoked_at"])
        self.assertEqual(self.refresh(self.client).status_code, 401)

    def test_two_devices_coexist_independently(self):
        laptop, phone = APIClient(), APIClient()
        self.login(laptop, trust=True, ua=CHROME_WIN)
        self.login(phone, trust=True, ua=SAFARI_IPHONE)
        self.assertEqual(sorted(r.label for r in self.rows()), ["Chrome on Windows", "Safari on iOS"])
        self.assertEqual(len({r.secret_hash for r in self.rows()}), 2)

        laptop_row = [r for r in self.rows() if r.label.startswith("Chrome")][0]
        laptop_row.revoked_at = timezone.now()
        laptop_row.save(update_fields=["revoked_at"])
        self.assertEqual(self.refresh(laptop).status_code, 401)
        self.assertEqual(self.refresh(phone).status_code, 200)

    def test_logging_in_on_a_new_device_does_not_end_the_others(self):
        old = APIClient()
        self.login(old, trust=True)
        self.login(APIClient(), trust=True)
        self.login(APIClient())
        self.assertEqual(self.refresh(old).status_code, 200)
        self.assertEqual(len([r for r in self.rows() if not r.revoked_at]), 3)

    def test_logging_one_device_out_leaves_the_other_and_does_not_revive_itself(self):
        laptop, phone = APIClient(), APIClient()
        l = self.login(laptop, trust=True)
        self.login(phone, trust=True, ua=SAFARI_IPHONE)
        raw = self.raw_cookie(l)
        self.assertEqual(self.logout(laptop, l.data["access"]).status_code, 204)

        self.assertEqual(self.refresh(phone).status_code, 200)
        revived = APIClient()
        revived.cookies[COOKIE] = raw
        self.assertEqual(self.refresh(revived).status_code, 401)
        # The laptop's own jar was told to forget it, so it cannot even ask.
        self.assertEqual(self.refresh(laptop).status_code, 401)
        self.assertEqual(len([r for r in self.rows() if r.revoked_at]), 1)

    def test_trusting_a_device_never_skips_the_password(self):
        resp = self.login(trust=True, password="not-the-password")
        self.assertEqual(resp.status_code, 401)
        self.assertNotIn(COOKIE, resp.cookies)
        self.assertEqual(self.rows(), [])

    def test_a_trusted_cookie_does_not_sign_in_without_a_password(self):
        self.login(trust=True)
        reopened = self.reopen(self.client)
        resp = self.login(reopened, password="wrong")        # a fresh login still needs it
        self.assertEqual(resp.status_code, 401)

    def test_the_login_throttle_still_applies_to_trusting_attempts(self):
        codes = [self.login(APIClient(), trust=True, password="wrong-%d" % i).status_code for i in range(16)]
        self.assertIn(429, codes)
        self.assertEqual(self.rows(), [])

    def test_a_wrong_password_with_any_combination_of_options_opens_nothing(self):
        for options in ({}, {"remember": True}, {"trust": True}, {"remember": True, "trust": True}):
            with self.subTest(options=options):
                cache.clear()
                resp = self.login(password="not-the-password", **options)
                self.assertEqual(resp.status_code, 401)
                self.assertNotIn(COOKIE, resp.cookies)
                self.assertNotIn("access", resp.data)
        self.assertEqual(self.rows(), [])
        self.assertFalse(OutstandingToken.objects.filter(user=self.user).exists())

    def test_the_four_combinations_each_give_the_expected_kind(self):
        expected = [
            ({}, "normal"),
            ({"remember": True}, "remember"),
            ({"trust": True}, "trusted"),
            ({"remember": True, "trust": True}, "trusted"),     # trust wins, defensively
            ({"remember": False, "trust": False}, "normal"),    # what the form sends when neither is ticked
            ({"remember": True, "trust": False}, "remember"),
            ({"remember": False, "trust": True}, "trusted"),
        ]
        for options, kind in expected:
            with self.subTest(options=options):
                cache.clear()
                self.assertEqual(self.login(**options).status_code, 200)
                self.assertEqual(self.rows()[-1].kind, kind)

    def test_an_unknown_user_with_the_option_gets_the_ordinary_refusal(self):
        resp = self.login(trust=True, username="nobody")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(auth_session_model().objects.count(), 0)


# =========================================================================== MFA


@override_settings(MFA_REQUIRED=True)
class TwoStepSignInTests(SessionBase):
    """The choice rides on the pending token; two-step sign-in is never skipped."""

    def setUp(self):
        super().setUp()
        self.device = MfaDevice.objects.create(user=self.user, secret=RFC_SECRET, confirmed_at=timezone.now())
        self.codes_used = 0

    def code(self):
        """A fresh code each call. A code for a step already accepted is refused, and
        only one step either side of now is allowed, so a test may use at most two."""
        ahead, self.codes_used = self.codes_used, self.codes_used + 1
        self.assertLessEqual(ahead, 1, "a test may verify at most two codes")
        return mfa.hotp(RFC_SECRET, mfa.current_step() + ahead)

    def verify(self, client, token, **extra):
        return client.post("/api/auth/mfa/login/verify/", {"mfa_token": token, "code": self.code(), **extra}, format="json")

    def test_a_right_password_with_the_options_opens_no_session(self):
        resp = self.login(remember=True, trust=True)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["mfa_required"])
        self.assertNotIn("access", resp.data)
        self.assertNotIn(COOKIE, resp.cookies)
        self.assertEqual(self.rows(), [])
        self.assertFalse(OutstandingToken.objects.filter(user=self.user).exists())

    def test_the_trusted_choice_survives_the_second_step(self):
        token = self.login(trust=True).data["mfa_token"]
        resp = self.verify(self.client, token)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self.rows()[0].kind, "trusted")
        self.assertAbout(self.max_age(resp), 90 * DAY)

    def test_the_remember_choice_survives_the_second_step(self):
        token = self.login(remember=True).data["mfa_token"]
        self.verify(self.client, token)
        self.assertEqual(self.rows()[0].kind, "remember")

    def test_so_does_it_when_a_recovery_code_is_used(self):
        from accounts.mfa_views import issue_recovery_codes

        codes = issue_recovery_codes(self.user)
        token = self.login(trust=True).data["mfa_token"]
        resp = self.client.post(
            "/api/auth/mfa/login/verify/", {"mfa_token": token, "recovery_code": codes[0]}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self.rows()[0].kind, "trusted")

    def test_options_sent_with_the_code_cannot_upgrade_the_session(self):
        token = self.login().data["mfa_token"]
        self.verify(self.client, token, trust_device=True, remember_me=True)
        self.assertEqual(self.rows()[0].kind, "normal")

    def test_a_trusted_device_still_has_to_pass_two_step_sign_in_next_time(self):
        token = self.login(trust=True).data["mfa_token"]
        self.verify(self.client, token)
        again = self.login(self.reopen(self.client), trust=True)
        self.assertTrue(again.data.get("mfa_required"))
        self.assertNotIn("access", again.data)

    def test_a_wrong_code_opens_nothing(self):
        token = self.login(trust=True).data["mfa_token"]
        resp = self.client.post("/api/auth/mfa/login/verify/", {"mfa_token": token, "code": "000000"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self.rows(), [])
        self.assertNotIn(COOKIE, resp.cookies)

    def test_ticking_both_boxes_still_gives_the_device_session_after_the_code(self):
        resp = self.login(remember=True, trust=True)
        self.assertTrue(resp.data["mfa_required"])
        self.assertEqual(self.rows(), [])
        done = self.verify(self.client, resp.data["mfa_token"])
        self.assertEqual(done.status_code, 200, done.content)
        (row,) = self.rows()
        self.assertEqual(row.kind, "trusted")
        self.assertAbout(self.max_age(done), 90 * DAY)

    def test_a_wrong_code_after_ticking_either_or_both_opens_nothing(self):
        for options in ({"remember": True}, {"trust": True}, {"remember": True, "trust": True}):
            with self.subTest(options=options):
                cache.clear()
                token = self.login(**options).data["mfa_token"]
                for _ in range(2):          # and a second try is no more successful
                    resp = self.client.post(
                        "/api/auth/mfa/login/verify/", {"mfa_token": token, "code": "000000"}, format="json"
                    )
                    self.assertEqual(resp.status_code, 400)
                    self.assertNotIn(COOKIE, resp.cookies)
                self.assertEqual(self.rows(), [])
                self.assertFalse(OutstandingToken.objects.filter(user=self.user).exists())

    def test_a_wrong_recovery_code_after_ticking_both_opens_nothing(self):
        token = self.login(remember=True, trust=True).data["mfa_token"]
        resp = self.client.post(
            "/api/auth/mfa/login/verify/", {"mfa_token": token, "recovery_code": "nope-nope"}, format="json"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn(COOKIE, resp.cookies)
        self.assertEqual(self.rows(), [])

    def test_abandoning_the_second_step_leaves_nothing_behind(self):
        self.login(remember=True, trust=True)       # the code is never entered
        self.assertEqual(self.rows(), [])
        self.assertFalse(OutstandingToken.objects.filter(user=self.user).exists())

    def test_a_tampered_pending_token_is_refused(self):
        token = self.login(trust=True).data["mfa_token"]
        resp = self.verify(self.client, token[:-3] + "xyz")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self.rows(), [])

    def test_resetting_the_authenticator_ends_trusted_sessions(self):
        from accounts.mfa_views import reset_mfa

        self.verify(self.client, self.login(trust=True).data["mfa_token"])
        reset_mfa(self.user)
        self.assertEqual(self.refresh(self.client).status_code, 401)
        self.assertTrue(all(r.revoked_at for r in self.rows()))

    def test_a_session_for_an_account_that_lost_its_authenticator_is_refused(self):
        self.verify(self.client, self.login(trust=True).data["mfa_token"])
        MfaDevice.objects.filter(user=self.user).delete()
        resp = self.refresh(self.client)
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.data.get("reason"), "mfa_setup_required")

    def test_replacing_the_authenticator_ends_the_other_devices_but_keeps_this_ones_kind(self):
        laptop, phone = APIClient(), APIClient()
        l = self.verify(laptop, self.login(laptop, trust=True).data["mfa_token"])
        self.verify(phone, self.login(phone, ua=SAFARI_IPHONE).data["mfa_token"])

        laptop.credentials(HTTP_AUTHORIZATION=f"Bearer {l.data['access']}")
        secret = laptop.post("/api/auth/mfa/setup/", {"password": PASSWORD}, format="json").data["secret"]
        done = laptop.post(
            "/api/auth/mfa/confirm/", {"code": mfa.hotp(secret, mfa.current_step())}, format="json"
        )
        self.assertEqual(done.status_code, 200, done.content)

        live = [r for r in self.rows() if not r.revoked_at]
        self.assertEqual([r.kind for r in live], ["trusted"])           # this device, same kind
        self.assertAbout(self.max_age(done), 90 * DAY)
        self.assertEqual(self.refresh(phone).status_code, 401)           # the other device is out


# ================================================================ logout & revoke


@override_settings(MFA_REQUIRED=False)
class LogoutAndRevocationTests(SessionBase):
    def test_logout_revokes_the_session_and_removes_the_cookie(self):
        resp = self.login()
        out = self.logout(self.client, resp.data["access"])
        self.assertEqual(out.status_code, 204)
        self.assertEqual(int(out.cookies[COOKIE]["max-age"]), 0)
        (row,) = self.rows()
        self.assertIsNotNone(row.revoked_at)

    def test_the_access_token_that_logged_out_stops_working_too(self):
        resp = self.login()
        self.logout(self.client, resp.data["access"])
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_the_logged_out_refresh_token_is_blacklisted_as_before(self):
        resp = self.login()
        raw = self.raw_cookie(resp)
        self.logout(self.client, resp.data["access"])
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=claims(raw)["jti"]).exists())

    def test_logging_out_without_a_cookie_still_ends_the_access_token(self):
        resp = self.login()
        self.client.cookies.clear()
        out = self.logout(self.client, resp.data["access"])
        self.assertEqual(out.status_code, 204)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_logging_out_with_a_rotated_away_cookie_still_ends_the_session(self):
        """A stale tab's cookie is one rotation behind; logging out from it must not
        leave the device's real session standing."""
        first = self.login()
        stale = self.raw_cookie(first)
        self.refresh(self.client)                              # the live token moves on
        other_tab = APIClient()
        other_tab.cookies[COOKIE] = stale
        self.logout(other_tab, first.data["access"])
        (row,) = self.rows()
        self.assertIsNotNone(row.revoked_at)
        self.assertEqual(self.refresh(self.client).status_code, 401)

    def test_one_devices_logout_does_not_touch_another_users_sessions(self):
        other = make_person("pat")
        a = self.login()
        self.login(APIClient(), username="pat")
        self.logout(self.client, a.data["access"])
        self.assertFalse(any(r.revoked_at for r in self.rows(other)))

    def test_changing_the_password_ends_every_session_but_reissues_this_devices_kind(self):
        laptop, phone = APIClient(), APIClient()
        l = self.login(laptop, trust=True)
        self.login(phone, remember=True, ua=SAFARI_IPHONE)

        laptop.credentials(HTTP_AUTHORIZATION=f"Bearer {l.data['access']}")
        done = laptop.post(
            "/api/auth/password/change/",
            {"current_password": PASSWORD, "new_password": "a-brand-new-passphrase-88"},
            format="json",
        )
        self.assertEqual(done.status_code, 200, done.content)
        self.assertAbout(self.max_age(done), 90 * DAY)
        live = [r for r in self.rows() if not r.revoked_at]
        self.assertEqual([r.kind for r in live], ["trusted"])
        self.assertEqual(self.refresh(phone).status_code, 401)
        self.assertEqual(self.refresh(laptop).status_code, 200)

    def test_revoking_the_accounts_tokens_marks_every_session_revoked(self):
        from accounts.tokens import revoke_refresh_tokens

        self.login(APIClient(), trust=True)
        self.login(APIClient(), remember=True)
        self.login(APIClient())
        revoke_refresh_tokens(self.user)
        self.assertTrue(all(r.revoked_at for r in self.rows()))

    def test_the_durable_half_still_happens_when_redis_is_down(self):
        from accounts.revocation import RevocationUnavailable
        from accounts.tests_revocation_durability import REDIS_CACHES, redis_down
        from accounts.tokens import revoke_refresh_tokens

        c = APIClient()
        self.login(c, trust=True)
        with self.settings(CACHES=REDIS_CACHES), redis_down():
            with self.assertRaises(RevocationUnavailable):
                revoke_refresh_tokens(self.user)
        self.assertTrue(all(r.revoked_at for r in self.rows()))
        self.assertEqual(self.refresh(c).status_code, 401)

    def test_logout_is_still_refused_while_redis_is_down_and_leaves_the_session_alone(self):
        from accounts.tests_revocation_durability import REDIS_CACHES, redis_down

        resp = self.login(trust=True)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")
        with self.settings(CACHES=REDIS_CACHES), redis_down():
            out = self.client.post("/api/auth/logout/")
        self.assertEqual(out.status_code, 503)
        (row,) = self.rows()
        self.assertIsNone(row.revoked_at)

    def test_refreshing_does_not_need_the_revocation_store(self):
        from accounts.tests_revocation_durability import REDIS_CACHES, redis_down

        self.login(remember=True)
        with self.settings(CACHES=REDIS_CACHES), redis_down():
            self.assertEqual(self.refresh(self.client).status_code, 200)

    def test_a_blacklisted_refresh_token_is_still_refused(self):
        resp = self.login(trust=True)
        raw = self.raw_cookie(resp)
        BlacklistedToken.objects.get_or_create(token=OutstandingToken.objects.get(jti=claims(raw)["jti"]))
        stale = APIClient()
        stale.cookies[COOKIE] = raw
        self.assertEqual(self.refresh(stale).status_code, 401)


# ========================================================== managing devices


@override_settings(MFA_REQUIRED=False)
class SessionManagementApiTests(SessionBase):
    URL = "/api/auth/sessions/"

    def setUp(self):
        super().setUp()
        self.laptop, self.phone = APIClient(), APIClient()
        self.l = self.login(self.laptop, trust=True, ua=CHROME_WIN)
        self.p = self.login(self.phone, remember=True, ua=SAFARI_IPHONE)

    def signed_in(self, client, response):
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        return client

    def test_it_needs_a_signed_in_user(self):
        self.assertIn(APIClient().get(self.URL).status_code, (401, 403))
        self.assertIn(APIClient().delete(f"{self.URL}1/").status_code, (401, 403))

    def test_you_see_your_own_devices_and_which_one_this_is(self):
        resp = self.signed_in(self.laptop, self.l).get(self.URL)
        self.assertEqual(resp.status_code, 200)
        by_label = {row["label"]: row for row in resp.data}
        self.assertEqual(set(by_label), {"Chrome on Windows", "Safari on iOS"})
        self.assertTrue(by_label["Chrome on Windows"]["current"])
        self.assertFalse(by_label["Safari on iOS"]["current"])
        self.assertEqual(by_label["Chrome on Windows"]["kind"], "trusted")

    def test_no_secret_or_token_is_ever_in_the_answer(self):
        resp = self.signed_in(self.laptop, self.l).get(self.URL)
        text = resp.content.decode()
        for needle in ("secret", "sid", "jti", "hash", self.raw_cookie(self.l), claims(self.raw_cookie(self.l))["sid"]):
            self.assertNotIn(needle, text)

    def test_only_your_own_sessions_are_listed(self):
        make_person("pat")
        stranger = APIClient()
        s = self.login(stranger, username="pat")
        resp = self.signed_in(stranger, s).get(self.URL)
        self.assertEqual(len(resp.data), 1)

    def test_a_device_can_be_revoked_and_then_cannot_refresh(self):
        client = self.signed_in(self.laptop, self.l)
        target = [r for r in client.get(self.URL).data if r["label"].startswith("Safari")][0]
        self.assertEqual(client.delete(f"{self.URL}{target['id']}/").status_code, 204)
        self.assertEqual(self.refresh(self.phone).status_code, 401)
        self.assertEqual(self.refresh(self.laptop).status_code, 200)

    def test_revoking_a_device_does_not_look_like_a_theft_afterwards(self):
        """The revoked device asking again must not cost the owner every other session."""
        client = self.signed_in(self.laptop, self.l)
        target = [r for r in client.get(self.URL).data if r["label"].startswith("Safari")][0]
        client.delete(f"{self.URL}{target['id']}/")
        phone_raw = self.raw_cookie(self.p)
        for _ in range(2):
            stale = APIClient()
            stale.cookies[COOKIE] = phone_raw
            self.assertEqual(self.refresh(stale).status_code, 401)
        self.assertEqual(self.refresh(self.laptop).status_code, 200)

    def test_a_revoked_device_disappears_from_the_list(self):
        client = self.signed_in(self.laptop, self.l)
        target = [r for r in client.get(self.URL).data if r["label"].startswith("Safari")][0]
        client.delete(f"{self.URL}{target['id']}/")
        self.assertEqual([r["label"] for r in client.get(self.URL).data], ["Chrome on Windows"])

    def test_an_expired_session_is_not_listed(self):
        remembered = [r for r in self.rows() if r.kind == "remember"][0]
        auth_session_model().objects.filter(pk=remembered.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        labels = [r["label"] for r in self.signed_in(self.laptop, self.l).get(self.URL).data]
        self.assertEqual(labels, ["Chrome on Windows"])

    def test_you_cannot_see_or_revoke_someone_elses_device(self):
        make_person("pat")
        stranger = APIClient()
        s = self.login(stranger, username="pat")
        mine = self.signed_in(self.laptop, self.l).get(self.URL).data[0]["id"]
        client = self.signed_in(stranger, s)
        self.assertEqual(client.delete(f"{self.URL}{mine}/").status_code, 404)
        self.assertEqual(self.refresh(self.laptop).status_code, 200)

    def test_an_unknown_id_is_a_plain_404(self):
        self.assertEqual(self.signed_in(self.laptop, self.l).delete(f"{self.URL}999999/").status_code, 404)

    def test_revoking_this_very_device_removes_its_cookie(self):
        client = self.signed_in(self.laptop, self.l)
        mine = [r for r in client.get(self.URL).data if r["current"]][0]
        out = client.delete(f"{self.URL}{mine['id']}/")
        self.assertEqual(out.status_code, 204)
        self.assertEqual(int(out.cookies[COOKIE]["max-age"]), 0)


# ============================================================ cookie & hygiene


@override_settings(MFA_REQUIRED=False)
class CookieAndTokenHygieneTests(SessionBase):
    def kinds(self):
        return {"normal": {}, "remember": {"remember": True}, "trusted": {"trust": True}}

    @override_settings(JWT_REFRESH_COOKIE_SECURE=True, JWT_REFRESH_COOKIE_SAMESITE="Strict")
    def test_every_kind_gets_the_same_hardened_cookie(self):
        for kind, options in self.kinds().items():
            with self.subTest(kind):
                cookie = self.login(APIClient(), **options).cookies[COOKIE]
                self.assertTrue(cookie["httponly"])
                self.assertTrue(cookie["secure"])
                self.assertEqual(cookie["samesite"], "Strict")
                self.assertEqual(cookie["path"], "/api/auth/")
                self.assertEqual(cookie["domain"], "")

    def test_the_default_samesite_is_still_lax(self):
        cookie = self.login(trust=True).cookies[COOKIE]
        self.assertEqual(cookie["samesite"], "Lax")

    def test_the_refresh_token_is_never_in_a_response_body(self):
        for kind, options in self.kinds().items():
            with self.subTest(kind):
                resp = self.login(APIClient(), **options)
                raw = self.raw_cookie(resp)
                self.assertNotIn(raw, resp.content.decode())
                self.assertNotIn("refresh", resp.data)
                refreshed = self.refresh(self._with_cookie(raw))
                self.assertNotIn("refresh", refreshed.data)

    def _with_cookie(self, raw):
        client = APIClient()
        client.cookies[COOKIE] = raw
        return client

    def test_the_access_token_carries_no_session_secret_and_stays_short(self):
        resp = self.login(trust=True)
        payload = token_backend.decode(resp.data["access"], verify=True)
        self.assertNotIn("sid", payload)
        self.assertEqual(payload["exp"] - payload["iat"], 15 * 60)
        self.assertIn("sid", claims(self.raw_cookie(resp)))

    def test_every_kind_gets_the_same_short_access_token(self):
        lifetimes = set()
        for options in self.kinds().values():
            payload = token_backend.decode(self.login(APIClient(), **options).data["access"], verify=True)
            lifetimes.add(payload["exp"] - payload["iat"])
        self.assertEqual(lifetimes, {15 * 60})

    def test_the_server_never_asks_for_the_password_again_after_login(self):
        self.login(trust=True)
        resp = self.refresh(self.reopen(self.client))
        self.assertEqual(resp.status_code, 200)

    def test_the_frontend_keeps_credentials_out_of_browser_storage(self):
        """A static guard: no sign-in file touches localStorage/sessionStorage, and
        no line that does names a credential."""
        import re
        from pathlib import Path

        src = Path(settings.BASE_DIR).parent / "frontend" / "src"
        if not src.is_dir():
            self.skipTest("the frontend is not checked out alongside the backend")

        for relative in ("api/auth.ts", "store/authStore.ts", "lib/api.ts", "pages/LoginPage.tsx",
                         "hooks/useAuthBootstrap.ts"):
            path = src / relative
            if path.exists():
                code = "\n".join(
                    line for line in path.read_text(encoding="utf-8").splitlines()
                    if not line.lstrip().startswith(("//", "*", "/*"))
                )
                self.assertNotRegex(code, r"localStorage|sessionStorage", relative)

        credential = re.compile(r"password|token|refresh|access|session|jwt|secret|remember|trust", re.I)
        for path in src.rglob("*.ts*"):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"(local|session)Storage\.(set|get)Item", line):
                    self.assertNotRegex(line, credential, f"{path.relative_to(src)}:{number}")


# ======================================================= the login form's contract


class LoginFormContractTests(TestCase):
    """What the sign-in page sends, checked against the source.

    The frontend has no test runner, and adding one just for this was ruled out,
    so the wiring is pinned the way the storage guard above pins it: by reading
    the files. These do not replace trying the form in a browser; they stop the
    contract drifting silently afterwards.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from pathlib import Path

        cls.src = Path(settings.BASE_DIR).parent / "frontend" / "src"

    def setUp(self):
        if not self.src.is_dir():
            self.skipTest("the frontend is not checked out alongside the backend")

    def read(self, relative):
        return (self.src / relative).read_text(encoding="utf-8")

    def test_the_login_request_carries_the_two_fields_the_server_reads(self):
        auth = self.read("api/auth.ts")
        self.assertRegex(auth, r"remember_me\?: boolean")
        self.assertRegex(auth, r"trust_device\?: boolean")
        # The one place a choice becomes request fields, and how.
        self.assertRegex(auth, r'remember_me:\s*choice === "remember"')
        self.assertRegex(auth, r'trust_device:\s*choice === "trust"')
        self.assertRegex(auth, r'api\.post<LoginResponse>\("/auth/login/", payload\)')

    def test_the_page_offers_both_options_and_sends_the_choice(self):
        page = self.read("pages/LoginPage.tsx")
        self.assertIn('id="login-remember"', page)
        self.assertIn('id="login-trust"', page)
        self.assertRegex(page, r"\.\.\.persistenceFields\(persist\)")
        self.assertIn("Remember me", page)
        self.assertIn("Trust this device", page)

    def test_the_options_are_mutually_exclusive_by_construction(self):
        page = self.read("pages/LoginPage.tsx")
        # One piece of state holds the choice, so both cannot be ticked.
        self.assertEqual(len(__import__("re").findall(r"useState<Persistence>", page)), 1)
        self.assertNotRegex(page, r"setRemember|setTrust\b|\[remember,|\[trust,")
        self.assertRegex(page, r'checked=\{persist === "remember"\}')
        self.assertRegex(page, r'checked=\{persist === "trust"\}')
        self.assertRegex(page, r'setPersist\(on \? "remember" : "none"\)')
        self.assertRegex(page, r'setPersist\(on \? "trust" : "none"\)')

    def test_both_are_off_until_ticked(self):
        self.assertRegex(self.read("pages/LoginPage.tsx"), r'useState<Persistence>\("none"\)')

    def test_the_form_says_trusting_a_device_does_not_skip_sign_in_checks(self):
        page = self.read("pages/LoginPage.tsx")
        self.assertRegex(page, r"password and two-step code are still required")

    def test_the_second_step_never_resends_or_changes_the_choice(self):
        """The choice lives in the server's signed pending token from the password
        step on; nothing on the code step may carry, or try to alter, it."""
        for relative in ("components/mfa/MfaSignIn.tsx", "pages/SignupPage.tsx"):
            self.assertNotRegex(self.read(relative), r"remember_me|trust_device|persistenceFields", relative)
        auth = self.read("api/auth.ts")
        verify = auth[auth.index("export async function verifyMfa"):auth.index("/** Signing in without an authenticator")]
        self.assertNotRegex(verify, r"remember_me|trust_device")
        confirm = auth[auth.index("export async function confirmSignInMfaSetup"):auth.index("export async function fetchMfaStatus")]
        self.assertNotRegex(confirm, r"remember_me|trust_device")

    def test_the_choice_is_never_written_to_browser_storage_or_a_script_readable_cookie(self):
        for relative in ("pages/LoginPage.tsx", "api/auth.ts", "components/mfa/MfaSignIn.tsx"):
            self.assertNotRegex(self.read(relative), r"localStorage|sessionStorage|document\.cookie", relative)


# ====================================================== sessions that pre-date this


@override_settings(MFA_REQUIRED=False)
class SessionsOpenedBeforeThisFeatureTests(SessionBase):
    """Refresh tokens already in browsers when this ships carry no session secret."""

    def legacy_client(self):
        client = APIClient()
        client.cookies[COOKIE] = str(RefreshToken.for_user(self.user))
        return client

    def test_such_a_token_keeps_working_and_is_upgraded_on_first_use(self):
        client = self.legacy_client()
        resp = self.refresh(client)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIn("sid", claims(self.raw_cookie(resp)))
        (row,) = self.rows()
        self.assertEqual(row.kind, "normal")
        self.assertEqual(row.current_jti, claims(self.raw_cookie(resp))["jti"])

    def test_the_upgraded_session_has_a_ceiling_from_the_upgrade(self):
        client = self.legacy_client()
        self.refresh(client)
        (row,) = self.rows()
        self.assertAbout((row.expires_at - timezone.now()).total_seconds(), 7 * DAY)
        with time_travel(days=8):
            self.assertEqual(self.refresh(client).status_code, 401)

    def test_it_then_rotates_like_any_other(self):
        client = self.legacy_client()
        self.refresh(client)
        self.assertEqual(self.refresh(client).status_code, 200)
        self.assertEqual(len(self.rows()), 1)

    def test_an_upgraded_session_can_be_revoked(self):
        client = self.legacy_client()
        self.refresh(client)
        (row,) = self.rows()
        row.revoked_at = timezone.now()
        row.save(update_fields=["revoked_at"])
        self.assertEqual(self.refresh(client).status_code, 401)

    def test_an_old_token_for_a_closed_account_is_still_refused(self):
        client = self.legacy_client()
        type(self.user).objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.refresh(client).status_code, 401)
        self.assertEqual(self.rows(), [])

    def test_a_signed_token_naming_no_known_session_is_refused(self):
        """Its row is gone -- deleted, or never made -- so nothing vouches for it."""
        resp = self.login()
        auth_session_model().objects.all().delete()
        out = self.refresh(self.client)
        self.assertEqual(out.status_code, 401)
        self.assertEqual(out.data.get("reason"), "session_ended")
        self.assertEqual(int(out.cookies[COOKIE]["max-age"]), 0)


# ============================================================== device labels


class DeviceLabelTests(TestCase):
    def label(self, ua):
        from accounts.auth_sessions import device_label

        return device_label(ua)

    def test_common_browsers_and_systems(self):
        self.assertEqual(self.label(CHROME_WIN), "Chrome on Windows")
        self.assertEqual(self.label(SAFARI_IPHONE), "Safari on iOS")
        self.assertEqual(self.label(FIREFOX_LINUX), "Firefox on Linux")
        self.assertEqual(
            self.label(CHROME_WIN.replace("Chrome/120.0.0.0 Safari/537.36", "Chrome/120.0.0.0 Safari/537.36 Edg/120.0")),
            "Edge on Windows",
        )

    def test_nothing_unusable_becomes_a_crash_or_a_novel(self):
        self.assertEqual(self.label(""), "Unknown device")
        self.assertEqual(self.label(None), "Unknown device")
        self.assertEqual(self.label("curl/8.4.0"), "Unknown browser on Unknown system")
        self.assertLessEqual(len(self.label("x" * 5000)), 120)

    def test_no_version_number_or_raw_agent_string_survives(self):
        label = self.label(CHROME_WIN)
        self.assertNotIn("Mozilla", label)
        self.assertFalse(any(ch.isdigit() for ch in label))
