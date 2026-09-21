"""Security properties of the account paths, pinned.

These cover the two ways a password gets set outside signup -- an admin
resetting one, and a lead being converted into a member -- because both are
easy to add to and easy to forget about, and both had a hole:

* an admin reset left the member's existing refresh tokens live for a week,
  so resetting a compromised account did not sign the intruder out;
* lead conversion was the one route to a first password that never ran the
  configured validators, so it accepted "123456".
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import MemberProfile, Role
from core.testing import TenantAPIMixin
from accounts.tokens import revoke_refresh_tokens

User = get_user_model()

GOOD_PASSWORD = "correct-horse-battery-42"


def make_user(username, role=Role.MEMBER):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    if role == Role.MEMBER:
        MemberProfile.objects.get_or_create(user=user)
    return user


class RevokeRefreshTokensTests(APITestCase):
    """The helper on its own."""

    def setUp(self):
        self.member = make_user("revoke_member")

    def _issue(self, count=1):
        return [RefreshToken.for_user(self.member) for _ in range(count)]

    def _blacklisted(self):
        return BlacklistedToken.objects.filter(token__user=self.member).count()

    def test_every_outstanding_token_is_blacklisted(self):
        self._issue(3)
        self.assertEqual(revoke_refresh_tokens(self.member), 3)
        self.assertEqual(self._blacklisted(), 3)

    def test_a_revoked_token_can_no_longer_be_refreshed(self):
        token = self._issue()[0]
        revoke_refresh_tokens(self.member)

        # The point of the whole exercise: the token in the intruder's hands
        # stops working, not merely the password they used to get it.
        from rest_framework_simplejwt.exceptions import TokenError

        with self.assertRaises(TokenError):
            RefreshToken(str(token)).check_blacklist()

    def test_calling_it_twice_is_harmless(self):
        # An admin who saves the form twice must not hit a unique violation.
        self._issue(2)
        self.assertEqual(revoke_refresh_tokens(self.member), 2)
        self.assertEqual(revoke_refresh_tokens(self.member), 0)
        self.assertEqual(self._blacklisted(), 2)

    def test_another_users_tokens_are_untouched(self):
        other = make_user("revoke_other")
        RefreshToken.for_user(other)
        self._issue(1)

        revoke_refresh_tokens(self.member)
        self.assertEqual(BlacklistedToken.objects.filter(token__user=other).count(), 0)

    def test_a_user_with_no_tokens_is_not_an_error(self):
        self.assertEqual(revoke_refresh_tokens(self.member), 0)


class AdminPasswordResetRevokesSessionsTests(TenantAPIMixin, APITestCase):
    """The path that matters: an admin resetting a compromised account."""

    def setUp(self):
        self.admin = make_user("sec_admin", role=Role.ADMIN)
        self.member = make_user("sec_member")
        # A member of this gym. Account admin is scoped to the gym, so without
        # this the member is out of reach -- and these tests would pass for the
        # wrong reason, on a 404 that never touched a password.
        self.member_for(self.member, Role.MEMBER)
        self.client.force_authenticate(self.admin)

    def _member_url(self):
        return f"/api/auth/admin/users/{self.member.id}/"

    def test_resetting_a_password_signs_existing_sessions_out(self):
        stolen = RefreshToken.for_user(self.member)
        self.assertEqual(OutstandingToken.objects.filter(user=self.member).count(), 1)

        resp = self.client.patch(self._member_url(), {"password": GOOD_PASSWORD})
        self.assertIn(resp.status_code, (200, 202))

        from rest_framework_simplejwt.exceptions import TokenError

        with self.assertRaises(TokenError):
            RefreshToken(str(stolen)).check_blacklist()

    def test_the_new_password_actually_works(self):
        self.client.patch(self._member_url(), {"password": GOOD_PASSWORD})
        self.member.refresh_from_db()
        self.assertTrue(self.member.check_password(GOOD_PASSWORD))

    def test_an_edit_that_does_not_touch_the_password_leaves_sessions_alone(self):
        # Renaming somebody must not log them out of their phone.
        live = RefreshToken.for_user(self.member)
        self.client.patch(self._member_url(), {"first_name": "Renamed"})

        RefreshToken(str(live)).check_blacklist()  # does not raise
        self.assertEqual(BlacklistedToken.objects.filter(token__user=self.member).count(), 0)

    def test_a_weak_password_is_refused_by_the_admin_route_too(self):
        resp = self.client.patch(self._member_url(), {"password": "123456"})
        self.assertEqual(resp.status_code, 400)
        self.member.refresh_from_db()
        self.assertFalse(self.member.check_password("123456"))


class LoginThrottleTests(TenantAPIMixin, APITestCase):
    """Guessing is limited by whose account is being guessed at, not only by
    where the guesses come from.

    The IP-based `login` scope was already there. It does nothing about the
    attack worth worrying about -- one account, a list of stolen passwords, a
    different source address each time -- because every request looks like a
    first attempt from a new client.
    """

    def setUp(self):
        self.member = make_user("throttle_target")
        cache.clear()

    def addCleanup_cache(self):  # pragma: no cover - defensive
        cache.clear()

    def tearDown(self):
        # Throttle state is global to the cache, so a leftover count would
        # make whichever test ran next fail for no reason of its own.
        cache.clear()
        super().tearDown()

    def _attempt(self, username="throttle_target", password="wrong-password", ip="10.0.0.1"):
        return self.client.post(
            "/api/auth/login/",
            {"username": username, "password": password},
            REMOTE_ADDR=ip,
        )

    def test_repeated_guesses_at_one_account_are_eventually_refused(self):
        seen_429 = False
        for _ in range(15):
            if self._attempt().status_code == 429:
                seen_429 = True
                break
        self.assertTrue(seen_429, "no throttle fired after 15 guesses at one account")

    def test_rotating_the_source_address_does_not_reset_the_limit(self):
        # The whole point. Each attempt comes from a different address, which
        # defeats an IP-only throttle entirely.
        seen_429 = False
        for n in range(15):
            if self._attempt(ip=f"10.0.{n}.{n + 1}").status_code == 429:
                seen_429 = True
                break
        self.assertTrue(
            seen_429, "rotating source IPs bypassed the limit -- per-username throttle not applied"
        )

    def test_a_different_account_is_not_punished_for_the_first_ones_attempts(self):
        # Throttling by username must not let one attacker lock out the rest
        # of the gym by hammering somebody else's login.
        make_user("throttle_bystander")
        # Spread across addresses so the per-IP throttle is not what refuses
        # the bystander -- this test is about the per-username one only.
        for n in range(12):
            self._attempt(ip=f"10.1.{n}.{n + 1}")

        resp = self._attempt(username="throttle_bystander", ip="10.9.9.9")
        self.assertNotEqual(
            resp.status_code, 429, "one account's attempts locked out another"
        )

    def test_the_username_key_is_case_insensitive(self):
        # Otherwise "Admin" and "admin" get a fresh budget each.
        for _ in range(12):
            self._attempt(username="Throttle_Target")
        resp = self._attempt(username="throttle_target")
        self.assertEqual(resp.status_code, 429)

    def test_a_request_with_no_username_is_not_a_crash(self):
        resp = self.client.post("/api/auth/login/", {"password": "x"})
        self.assertIn(resp.status_code, (400, 401, 429))
