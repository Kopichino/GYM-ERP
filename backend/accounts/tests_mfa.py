"""Two-step sign-in.

The arithmetic first, against the RFC's own test vectors; then the sign-in steps
as a person meets them; then managing it afterwards, and an admin's way back in
for someone who has lost both phone and recovery codes.
"""

import base64
import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from core.testing import TenantAPIMixin, founding_tenant
from tenancy.models import Membership

from . import mfa
from .mfa_views import issue_recovery_codes
from .models import MemberProfile, MfaDevice, MfaRecoveryCode, Role

User = get_user_model()

PASSWORD = "correct-horse-battery-42"
#: RFC 6238's test key -- the ASCII bytes "12345678901234567890" -- in base32.
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


def code_now(secret, ahead=0):
    """The code an authenticator app shows right now -- or `ahead` steps on, for
    a second code in one test that must not count as a replay of the first."""
    return mfa.hotp(secret, mfa.current_step() + ahead)


def wrong_code(secret):
    """A well-formed code that is not valid anywhere near the current window."""
    step = mfa.current_step()
    valid = {mfa.hotp(secret, step + drift) for drift in range(-2, 3)}
    return next(f"{n:06d}" for n in range(1_000_000) if f"{n:06d}" not in valid)


class TotpTests(SimpleTestCase):
    """RFC 4226 / 6238 are implemented on the standard library here, so they are
    checked against the published vectors rather than trusted."""

    def test_rfc_6238_sha1_test_vectors(self):
        vectors = {
            59: "94287082",
            1111111109: "07081804",
            1111111111: "14050471",
            1234567890: "89005924",
            2000000000: "69279037",
            20000000000: "65353130",
        }
        for moment, expected in vectors.items():
            with self.subTest(moment=moment):
                self.assertEqual(
                    mfa.hotp(RFC_SECRET, mfa.current_step(moment), digits=8), expected
                )

    def test_a_code_one_step_either_side_is_accepted_for_clock_drift(self):
        now = 1_700_000_000
        step = mfa.current_step(now)
        for drift in (-1, 0, 1):
            with self.subTest(drift=drift):
                code = mfa.hotp(RFC_SECRET, step + drift)
                self.assertEqual(mfa.matching_step(RFC_SECRET, code, now=now), step + drift)

    def test_a_code_further_out_is_not(self):
        now = 1_700_000_000
        step = mfa.current_step(now)
        for drift in (-3, -2, 2, 3):
            with self.subTest(drift=drift):
                code = mfa.hotp(RFC_SECRET, step + drift)
                self.assertIsNone(mfa.matching_step(RFC_SECRET, code, now=now))

    def test_a_code_for_a_step_already_used_is_refused(self):
        now = 1_700_000_000
        step = mfa.current_step(now)
        for used in (step, step - 1):
            with self.subTest(step=used - step):
                code = mfa.hotp(RFC_SECRET, used)
                self.assertIsNone(mfa.matching_step(RFC_SECRET, code, after=step, now=now))
        # The next code along is still good.
        following = mfa.hotp(RFC_SECRET, step + 1)
        self.assertEqual(
            mfa.matching_step(RFC_SECRET, following, after=step, now=now), step + 1
        )

    def test_spaces_in_a_typed_code_do_not_matter(self):
        now = 1_700_000_000
        code = mfa.hotp(RFC_SECRET, mfa.current_step(now))
        self.assertIsNotNone(mfa.matching_step(RFC_SECRET, f"{code[:3]} {code[3:]}", now=now))

    def test_malformed_codes_are_refused_without_error(self):
        for code in (None, "", "12345", "1234567", "abcdef"):
            with self.subTest(code=code):
                self.assertIsNone(mfa.matching_step(RFC_SECRET, code))

    def test_new_keys_are_160_bits_and_never_repeat(self):
        first, second = mfa.new_secret(), mfa.new_secret()
        self.assertNotEqual(first, second)
        self.assertEqual(len(base64.b32decode(first + "=" * (-len(first) % 8))), 20)

    @override_settings(MFA_ISSUER="IRONCORE")
    def test_the_setup_link_names_the_issuer_and_the_account(self):
        uri = mfa.provisioning_uri("ABCDEFGH", "arjun.s")
        self.assertTrue(uri.startswith("otpauth://totp/IRONCORE%3Aarjun.s?"), uri)
        self.assertIn("secret=ABCDEFGH", uri)
        self.assertIn("issuer=IRONCORE", uri)

    def test_recovery_codes_are_easy_to_read_and_forgiving_to_type(self):
        codes = mfa.new_recovery_codes()
        self.assertEqual(len(set(codes)), mfa.RECOVERY_CODE_COUNT)
        chars = f"[{mfa.RECOVERY_ALPHABET}]"
        for code in codes:
            self.assertRegex(code, rf"^{chars}{{5}}-{chars}{{5}}$")
        self.assertIsNone(re.search(r"[01ilo]", "".join(codes)))
        self.assertEqual(
            mfa.hash_recovery_code("ABCDE-FGHJK"), mfa.hash_recovery_code(" abcde fghjk ")
        )


class MfaAPITestCase(TenantAPIMixin, APITestCase):
    def setUp(self):
        # Throttle counts live in the cache and would otherwise leak between tests.
        cache.clear()
        self.user = self.make_user("mfa_member", Role.MEMBER)

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def make_user(self, username, role):
        user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password=PASSWORD, role=role
        )
        MemberProfile.objects.create(user=user)
        self.member_for(user, role)
        return user

    def post(self, path, data=None, **extra):
        return self.client.post(path, data or {}, format="json", **extra)

    def login(self, username="mfa_member", password=PASSWORD):
        return self.post("/api/auth/login/", {"username": username, "password": password})

    def pending_token(self):
        resp = self.login()
        self.assertEqual(resp.status_code, 200, resp.data)
        return resp.data["mfa_token"]

    def enrol(self, user=None, secret=RFC_SECRET):
        return MfaDevice.objects.create(
            user=user or self.user, secret=secret, confirmed_at=timezone.now()
        )


class SettingUpAtSignInTests(MfaAPITestCase):
    """An account with no authenticator, the first time it signs in."""

    def test_a_right_password_alone_opens_no_session(self):
        resp = self.login()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["mfa_setup_required"])
        self.assertIn("mfa_token", resp.data)
        self.assertNotIn("access", resp.data)
        self.assertNotIn("refresh_token", resp.cookies)
        # Not even an unused refresh token minted along the way.
        self.assertFalse(OutstandingToken.objects.filter(user=self.user).exists())

    def test_a_wrong_password_gets_no_further_than_it_did_before(self):
        resp = self.login(password="not-the-password")
        self.assertEqual(resp.status_code, 401)
        self.assertNotIn("mfa_token", resp.data)

    def test_setting_up_opens_the_session_and_hands_over_recovery_codes(self):
        token = self.pending_token()
        setup = self.post("/api/auth/mfa/login/setup/", {"mfa_token": token})
        self.assertEqual(setup.status_code, 200, setup.data)
        secret = setup.data["secret"]
        self.assertIn(f"secret={secret}", setup.data["otpauth_uri"])
        # Asking again -- a reload, an effect run twice -- keeps the key already scanned.
        again = self.post("/api/auth/mfa/login/setup/", {"mfa_token": token})
        self.assertEqual(again.data["secret"], secret)

        wrong = self.post(
            "/api/auth/mfa/login/confirm/", {"mfa_token": token, "code": wrong_code(secret)}
        )
        self.assertEqual(wrong.status_code, 400)
        self.assertNotIn("refresh_token", wrong.cookies)
        self.assertFalse(mfa.has_confirmed_device(self.user))

        right = self.post(
            "/api/auth/mfa/login/confirm/", {"mfa_token": token, "code": code_now(secret)}
        )
        self.assertEqual(right.status_code, 200, right.data)
        self.assertIn("access", right.data)
        self.assertTrue(right.cookies["refresh_token"]["httponly"])
        self.assertEqual(len(right.data["recovery_codes"]), 10)
        self.assertTrue(mfa.has_confirmed_device(self.user))

        # Only hashes are kept, never the codes themselves.
        stored = set(
            MfaRecoveryCode.objects.filter(user=self.user).values_list("code_hash", flat=True)
        )
        self.assertEqual(len(stored), 10)
        self.assertTrue(stored.isdisjoint(right.data["recovery_codes"]))

        # From now on the password step asks for a code instead.
        self.assertTrue(self.login().data["mfa_required"])

    def test_the_password_alone_cannot_replace_an_existing_authenticator(self):
        device = self.enrol()
        token = self.pending_token()
        self.assertEqual(
            self.post("/api/auth/mfa/login/setup/", {"mfa_token": token}).status_code, 409
        )
        self.assertEqual(
            self.post(
                "/api/auth/mfa/login/confirm/", {"mfa_token": token, "code": "123456"}
            ).status_code,
            409,
        )
        device.refresh_from_db()
        self.assertEqual(device.secret, RFC_SECRET)
        self.assertEqual(device.pending_secret, "")

    def test_a_session_opened_before_it_was_required_stops_refreshing(self):
        self.client.cookies["refresh_token"] = str(RefreshToken.for_user(self.user))
        resp = self.post("/api/auth/refresh/")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.data["reason"], "mfa_setup_required")

    def test_refreshing_works_again_once_it_is_set_up(self):
        self.enrol()
        self.client.cookies["refresh_token"] = str(RefreshToken.for_user(self.user))
        resp = self.post("/api/auth/refresh/")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertIn("access", resp.data)

    @override_settings(MFA_REQUIRED=False)
    def test_where_it_is_not_required_the_password_is_enough(self):
        resp = self.login()
        self.assertIn("access", resp.data)
        self.assertIn("refresh_token", resp.cookies)

    @override_settings(MFA_REQUIRED=False)
    def test_an_account_that_set_it_up_keeps_it_when_it_is_no_longer_required(self):
        self.enrol()
        resp = self.login()
        self.assertTrue(resp.data["mfa_required"])
        self.assertNotIn("access", resp.data)


class SigningInWithACodeTests(MfaAPITestCase):
    def setUp(self):
        super().setUp()
        self.device = self.enrol()

    def verify(self, **data):
        return self.post("/api/auth/mfa/login/verify/", data)

    def test_the_password_step_asks_for_a_code_and_opens_nothing(self):
        resp = self.login()
        self.assertTrue(resp.data["mfa_required"])
        self.assertNotIn("access", resp.data)
        self.assertNotIn("refresh_token", resp.cookies)

    def test_a_right_code_opens_the_session(self):
        resp = self.verify(mfa_token=self.pending_token(), code=code_now(RFC_SECRET))
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertIn("access", resp.data)
        self.assertTrue(resp.cookies["refresh_token"]["httponly"])

    def test_a_wrong_code_does_not(self):
        resp = self.verify(mfa_token=self.pending_token(), code=wrong_code(RFC_SECRET))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("code", resp.data)
        self.assertNotIn("refresh_token", resp.cookies)

    def test_a_code_cannot_be_used_twice(self):
        code = code_now(RFC_SECRET)
        self.assertEqual(self.verify(mfa_token=self.pending_token(), code=code).status_code, 200)
        # Read over a shoulder and typed in within the same half-minute.
        self.assertEqual(self.verify(mfa_token=self.pending_token(), code=code).status_code, 400)

    def test_a_recovery_code_works_once(self):
        codes = issue_recovery_codes(self.user)
        # Typed however it comes out: capitals, no dash.
        first = self.verify(
            mfa_token=self.pending_token(), recovery_code=codes[0].upper().replace("-", "")
        )
        self.assertEqual(first.status_code, 200, first.data)
        self.assertTrue(first.data["used_recovery_code"])
        self.assertEqual(first.data["recovery_codes_remaining"], 9)

        second = self.verify(mfa_token=self.pending_token(), recovery_code=codes[0])
        self.assertEqual(second.status_code, 400)
        self.assertIn("recovery_code", second.data)

    def test_a_made_up_or_tampered_sign_in_token_is_refused(self):
        token = self.pending_token()
        tampered = token[:-3] + ("xyz" if not token.endswith("xyz") else "abc")
        for bad in ("", "nonsense", tampered):
            with self.subTest(token=bad[:12]):
                resp = self.verify(mfa_token=bad, code=code_now(RFC_SECRET))
                self.assertEqual(resp.status_code, 400)
                self.assertEqual(resp.data["reason"], "mfa_token_invalid")

    def test_a_sign_in_left_too_long_expires(self):
        token = self.pending_token()
        with mock.patch.object(mfa, "PENDING_MAX_AGE", -1):
            resp = self.verify(mfa_token=token, code=code_now(RFC_SECRET))
        self.assertEqual(resp.data["reason"], "mfa_token_invalid")

    def test_a_new_password_voids_a_half_finished_sign_in(self):
        token = self.pending_token()
        self.user.set_password("a-different-strong-pass-77")
        self.user.save()
        resp = self.verify(mfa_token=token, code=code_now(RFC_SECRET))
        self.assertEqual(resp.data["reason"], "mfa_token_invalid")

    def test_a_deactivated_account_cannot_finish_signing_in(self):
        token = self.pending_token()
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.verify(mfa_token=token, code=code_now(RFC_SECRET)).status_code, 400)

    def test_a_stale_bearer_token_in_the_browser_does_not_get_in_the_way(self):
        token = self.pending_token()
        self.client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
        resp = self.verify(mfa_token=token, code=code_now(RFC_SECRET))
        self.assertEqual(resp.status_code, 200, resp.data)

    def test_guessing_codes_is_limited_per_account_whatever_the_address(self):
        token = self.pending_token()
        statuses = [
            self.post(
                "/api/auth/mfa/login/verify/",
                {"mfa_token": token, "code": wrong_code(RFC_SECRET)},
                REMOTE_ADDR=f"10.2.{n}.{n + 1}",
            ).status_code
            for n in range(8)
        ]
        self.assertEqual(statuses[0], 400)
        self.assertIn(429, statuses, "rotating addresses got past the per-account limit")


class ManagingYourOwnAuthenticatorTests(MfaAPITestCase):
    def setUp(self):
        super().setUp()
        self.device = self.enrol()
        self.old_codes = issue_recovery_codes(self.user)
        self.client.force_authenticate(self.user)

    def test_status(self):
        resp = self.client.get("/api/auth/mfa/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["enabled"])
        self.assertTrue(resp.data["required"])
        self.assertEqual(resp.data["recovery_codes_remaining"], 10)

    def test_moving_to_a_new_phone_needs_the_password(self):
        refused = self.post("/api/auth/mfa/setup/", {"password": "not-it"})
        self.assertEqual(refused.status_code, 400)
        self.assertIn("password", refused.data)
        self.device.refresh_from_db()
        self.assertEqual(self.device.pending_secret, "")

    def test_the_old_authenticator_keeps_working_until_the_new_one_is_proven(self):
        new_secret = self.post("/api/auth/mfa/setup/", {"password": PASSWORD}).data["secret"]
        self.assertNotEqual(new_secret, RFC_SECRET)

        resp = self.post("/api/auth/mfa/confirm/", {"code": wrong_code(new_secret)})
        self.assertEqual(resp.status_code, 400)
        self.device.refresh_from_db()
        self.assertEqual(self.device.secret, RFC_SECRET)

    def test_confirming_the_new_phone_swaps_the_key_and_ends_other_sessions(self):
        elsewhere = RefreshToken.for_user(self.user)
        new_secret = self.post("/api/auth/mfa/setup/", {"password": PASSWORD}).data["secret"]

        resp = self.post("/api/auth/mfa/confirm/", {"code": code_now(new_secret)})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertIn("access", resp.data)
        self.assertIn("refresh_token", resp.cookies)
        self.assertEqual(len(resp.data["recovery_codes"]), 10)

        self.device.refresh_from_db()
        self.assertEqual(self.device.secret, new_secret)
        self.assertEqual(self.device.pending_secret, "")
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=elsewhere["jti"]).exists())
        # The old sheet of recovery codes is dead.
        self.assertFalse(
            MfaRecoveryCode.objects.filter(
                user=self.user, code_hash=mfa.hash_recovery_code(self.old_codes[0])
            ).exists()
        )

    def test_new_recovery_codes_need_a_current_code(self):
        refused = self.post("/api/auth/mfa/recovery-codes/", {"code": wrong_code(RFC_SECRET)})
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(
            MfaRecoveryCode.objects.filter(user=self.user, used_at__isnull=True).count(), 10
        )

        resp = self.post("/api/auth/mfa/recovery-codes/", {"code": code_now(RFC_SECRET)})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(len(resp.data["recovery_codes"]), 10)
        self.assertFalse(set(resp.data["recovery_codes"]) & set(self.old_codes))
        self.assertFalse(
            MfaRecoveryCode.objects.filter(
                user=self.user, code_hash=mfa.hash_recovery_code(self.old_codes[0])
            ).exists()
        )

    def test_signed_out_callers_get_nothing(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/auth/mfa/").status_code, 401)
        self.assertEqual(self.post("/api/auth/mfa/setup/", {"password": PASSWORD}).status_code, 401)
        self.assertEqual(
            self.post("/api/auth/mfa/recovery-codes/", {"code": code_now(RFC_SECRET)}).status_code,
            401,
        )


class AdminResetTests(MfaAPITestCase):
    """The way back in for someone who has lost their phone and their codes."""

    def setUp(self):
        super().setUp()
        self.admin = self.make_user("mfa_admin", Role.ADMIN)
        self.enrol()
        issue_recovery_codes(self.user)
        self.session = RefreshToken.for_user(self.user)

    def reset(self, user):
        return self.post(f"/api/auth/admin/users/{user.pk}/reset-mfa/")

    def test_an_admin_resets_a_member_of_their_gym(self):
        self.client.force_authenticate(self.admin)
        resp = self.reset(self.user)
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertFalse(MfaDevice.objects.filter(user=self.user).exists())
        self.assertFalse(MfaRecoveryCode.objects.filter(user=self.user).exists())
        # Whoever reported the phone lost may not be the only one holding it.
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=self.session["jti"]).exists())

        self.client.force_authenticate(None)
        self.assertTrue(self.login().data["mfa_setup_required"])

    def test_the_member_list_says_who_has_it_set_up(self):
        self.make_user("mfa_newcomer", Role.MEMBER)
        self.client.force_authenticate(self.admin)
        resp = self.client.get("/api/auth/admin/members/")
        rows = {row["username"]: row for row in resp.data["results"]}
        self.assertTrue(rows["mfa_member"]["has_mfa"])
        self.assertFalse(rows["mfa_newcomer"]["has_mfa"])

    def test_an_admin_cannot_reset_someone_at_another_gym(self):
        _, elsewhere = founding_tenant("othergym")
        stranger = User.objects.create_user(
            username="mfa_stranger", email="mfa_stranger@example.com", password=PASSWORD
        )
        Membership.objects.create(user=stranger, tenant=elsewhere, role=Role.MEMBER)
        self.enrol(stranger)

        self.client.force_authenticate(self.admin)
        self.assertEqual(self.reset(stranger).status_code, 404)
        self.assertTrue(mfa.has_confirmed_device(stranger))

    def test_a_member_cannot_reset_anyone(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.reset(self.admin).status_code, 403)
        self.assertTrue(mfa.has_confirmed_device(self.user))
