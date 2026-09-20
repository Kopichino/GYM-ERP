"""Stolen and stale sessions.

A refresh token lives for a week in a cookie; an access token lives for fifteen
minutes in memory. These pin what happens when either is in the wrong hands:

* a refresh token replayed after it was rotated is treated as theft, and every
  session of the account ends -- whoever holds the newer token, attacker or
  owner, has to sign in again;
* logging out, changing a password, or an admin resetting sign-in ends access
  tokens immediately rather than up to fifteen minutes later.
"""

from datetime import timedelta

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import MfaDevice, Role

from .testing import PASSWORD, TwoGymsTestCase, bearer, make_person


@override_settings(MFA_REQUIRED=False)
class RefreshTokenReuseTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = make_person("rotator")

    def refresh_with(self, raw):
        self.client.cookies["refresh_token"] = raw
        return self.client.post("/api/auth/refresh/")

    def pretend_rotated_long_ago(self, raw, seconds=600):
        jti = RefreshToken(raw, verify=False)["jti"]
        BlacklistedToken.objects.filter(token__jti=jti).update(
            blacklisted_at=timezone.now() - timedelta(seconds=seconds)
        )

    def test_replaying_a_rotated_refresh_token_ends_every_session_of_the_account(self):
        stolen = str(RefreshToken.for_user(self.user))
        first = self.refresh_with(stolen)
        self.assertEqual(first.status_code, 200)
        newer = first.cookies["refresh_token"].value

        self.pretend_rotated_long_ago(stolen)
        self.assertEqual(self.refresh_with(stolen).status_code, 401)
        self.assertEqual(self.refresh_with(newer).status_code, 401)

    def test_a_second_use_within_seconds_is_a_race_not_a_theft(self):
        """Two tabs refreshing at once must not sign the person out everywhere."""
        original = str(RefreshToken.for_user(self.user))
        newer = self.refresh_with(original).cookies["refresh_token"].value
        self.assertEqual(self.refresh_with(original).status_code, 401)
        self.assertEqual(self.refresh_with(newer).status_code, 200)

    def test_revoking_an_account_ends_a_refresh_token_that_was_already_rotated(self):
        """Rotation minted a new refresh token without recording it as outstanding,
        so "revoke every refresh token" -- what a password reset or an admin reset
        does -- only reached the token issued at sign-in. After one refresh, the
        token actually in the browser survived the reset for up to a week."""
        from accounts.tokens import revoke_refresh_tokens

        rotated = self.refresh_with(str(RefreshToken.for_user(self.user)))
        self.assertEqual(rotated.status_code, 200)
        in_use = rotated.cookies["refresh_token"].value

        revoke_refresh_tokens(self.user)
        self.assertEqual(self.refresh_with(in_use).status_code, 401)

    def test_rotation_still_hands_out_a_working_token(self):
        first = self.refresh_with(str(RefreshToken.for_user(self.user)))
        self.assertEqual(first.status_code, 200)
        second = self.refresh_with(first.cookies["refresh_token"].value)
        self.assertEqual(second.status_code, 200)


@override_settings(MFA_REQUIRED=False)
class AccessTokenRevocationTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = make_person("holder")

    def me(self, token):
        return self.client.get("/api/auth/me/", HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_the_access_token_used_to_log_out_stops_working(self):
        token = bearer(self.user)
        self.assertEqual(self.me(token).status_code, 200)
        resp = self.client.post("/api/auth/logout/", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(self.me(token).status_code, 401)

    def test_logging_out_one_device_leaves_another_signed_in(self):
        here, there = bearer(self.user), bearer(self.user)
        self.client.post("/api/auth/logout/", HTTP_AUTHORIZATION=f"Bearer {here}")
        self.assertEqual(self.me(there).status_code, 200)

    def test_changing_the_password_ends_access_tokens_issued_before_it(self):
        old = bearer(self.user, issued_seconds_ago=5)
        resp = self.client.post(
            "/api/auth/password/change/",
            {"current_password": PASSWORD, "new_password": "an-entirely-new-passphrase-8"},
            HTTP_AUTHORIZATION=f"Bearer {old}",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self.me(old).status_code, 401)
        self.assertEqual(self.me(resp.data["access"]).status_code, 200)

    def test_a_logged_out_refresh_token_cannot_be_used(self):
        refresh = RefreshToken.for_user(self.user)
        self.client.cookies["refresh_token"] = str(refresh)
        self.client.post(
            "/api/auth/logout/", HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}"
        )
        self.client.cookies["refresh_token"] = str(refresh)
        self.assertEqual(self.client.post("/api/auth/refresh/").status_code, 401)


class AdminResetEndsSessionsTests(TwoGymsTestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_person("admin_a", gym=self.gym_a, role=Role.ADMIN)
        self.member = make_person("member_a", gym=self.gym_a)
        self.member_token = bearer(self.member, issued_seconds_ago=5)
        self.base = self.at(self.gym_a)

    def members_token_still_works(self):
        self.client.credentials()
        return (
            self.client.get("/api/auth/me/", HTTP_AUTHORIZATION=f"Bearer {self.member_token}").status_code
            == 200
        )

    def test_an_admin_setting_a_new_password_signs_the_member_out_at_once(self):
        self.assertTrue(self.members_token_still_works())
        self.sign_in(self.admin)
        resp = self.client.post(
            f"{self.base}/auth/admin/members/{self.member.pk}/set-password/",
            {"password": "a-brand-new-passphrase-99"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(self.members_token_still_works())

    def test_an_admin_resetting_two_step_sign_in_signs_the_member_out_at_once(self):
        MfaDevice.objects.create(
            user=self.member, secret="JBSWY3DPEHPK3PXP", confirmed_at=timezone.now()
        )
        self.sign_in(self.admin)
        resp = self.client.post(f"{self.base}/auth/admin/users/{self.member.pk}/reset-mfa/")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(self.members_token_still_works())
