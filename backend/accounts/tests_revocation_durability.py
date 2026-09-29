"""Ending a session has to survive the cache being down.

Two things end a session and they are not equally durable: blacklisting the
refresh tokens is a row in a table, while ending the access tokens is a note in
a cache that may be unreachable. When the cache half ran first, its exception
left `revoke_refresh_tokens` before a single refresh token had been blacklisted
-- so a password reset meant to lock an intruder out changed the password and
left them a refresh token good for another week.

Every test here asserts what is *in the database afterwards*. Asserting only
that the helper raises is what let this through the first time: the helper did
raise, correctly, and the durable work silently never happened.
"""

from contextlib import contextmanager
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from redis.exceptions import ConnectionError as RedisConnectionError
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import MfaDevice, Role
from accounts.revocation import RevocationUnavailable, is_revoked
from accounts.tokens import revoke_refresh_tokens
from core.testing import TenantAPIMixin

User = get_user_model()

STRONG = "a-long-enough-passphrase-1"
NEW = "an-entirely-different-one-2"

REDIS_CACHES = {
    "default": {
        "BACKEND": "core.cache.ResilientRedisCache",
        "LOCATION": "redis://127.0.0.1:6399/0",
        "OPTIONS": {"socket_connect_timeout": 0.05, "socket_timeout": 0.05},
    },
    "revocation": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://127.0.0.1:6399/0",
        "OPTIONS": {"socket_connect_timeout": 0.05, "socket_timeout": 0.05},
    },
}


@contextmanager
def redis_down():
    """Every call into the Redis backend fails, the way an outage does."""
    from django.core.cache.backends.redis import RedisCache

    outage = RedisConnectionError("Error 111 connecting to redis:6379.")
    with (
        mock.patch.object(RedisCache, "get", side_effect=outage),
        mock.patch.object(RedisCache, "set", side_effect=outage),
        mock.patch.object(RedisCache, "delete", side_effect=outage),
    ):
        yield


@contextmanager
def redis_healthy():
    """A reachable, empty Redis: a miss answers with the caller's default."""
    from django.core.cache.backends.redis import RedisCache

    with (
        mock.patch.object(RedisCache, "get", side_effect=lambda key, default=None, version=None: default),
        mock.patch.object(RedisCache, "set", return_value=None),
    ):
        yield


class RevocationDurabilityMixin:
    def make_user(self, username, role=Role.MEMBER):
        return User.objects.create_user(
            username=username, email=f"{username}@example.com", password=STRONG, role=role
        )

    def open_sessions(self, user, count=2):
        """`count` live refresh tokens, as `count` signed-in devices would have."""
        tokens = [RefreshToken.for_user(user) for _ in range(count)]
        self.assertEqual(OutstandingToken.objects.filter(user=user).count(), count)
        self.assertEqual(self.blacklisted(user), 0)
        return tokens

    def blacklisted(self, user):
        return BlacklistedToken.objects.filter(token__user=user).count()

    def still_usable(self, user):
        """Refresh tokens of `user` that nothing has blacklisted."""
        return OutstandingToken.objects.filter(user=user).exclude(
            id__in=BlacklistedToken.objects.values("token_id")
        ).count()


class RevokeRefreshTokensTests(RevocationDurabilityMixin, TestCase):
    """The helper itself, which every one of these paths goes through."""

    def test_the_database_blacklist_happens_even_though_redis_is_down(self):
        """Test 1's core: the durable half must not depend on the cache."""
        user = self.make_user("durable")
        self.open_sessions(user, count=2)

        with self.settings(CACHES=REDIS_CACHES), redis_down():
            with self.assertRaises(RevocationUnavailable):
                revoke_refresh_tokens(user)

        # The point of the whole fix: reported, but only after the durable work.
        self.assertEqual(self.blacklisted(user), 2)
        self.assertEqual(self.still_usable(user), 0)

    def test_the_failure_is_recorded_rather_than_passed_over_in_silence(self):
        user = self.make_user("recorded")
        self.open_sessions(user, count=1)

        with self.settings(CACHES=REDIS_CACHES), redis_down():
            with self.assertLogs("security", level="WARNING") as logs:
                with self.assertRaises(RevocationUnavailable):
                    revoke_refresh_tokens(user)

        joined = "\n".join(logs.output)
        self.assertIn("security_event=access_tokens_not_ended", joined)
        self.assertEqual(self.still_usable(user), 0)

    def test_healthy_redis_behaves_exactly_as_before(self):
        """Test 5: the fix must not change the working path."""
        user = self.make_user("healthy")
        self.open_sessions(user, count=2)

        with self.settings(CACHES=REDIS_CACHES), redis_healthy():
            revoked = revoke_refresh_tokens(user)

        self.assertEqual(revoked, 2)
        self.assertEqual(self.blacklisted(user), 2)
        self.assertEqual(self.still_usable(user), 0)

    def test_an_unexpected_error_is_not_swallowed(self):
        """Test 7: only a cache outage is handled; a bug still surfaces."""
        user = self.make_user("unexpected")
        self.open_sessions(user, count=1)

        with mock.patch(
            "accounts.revocation.end_access_tokens", side_effect=ValueError("a real bug")
        ):
            with self.assertRaises(ValueError):
                revoke_refresh_tokens(user)

        # And the durable half still ran first.
        self.assertEqual(self.still_usable(user), 0)


class ReadPathTests(RevocationDurabilityMixin, TestCase):
    def test_is_revoked_still_fails_closed(self):
        """Test 6: the read path must never answer "not revoked" from a dead
        cache. Unchanged by this fix, and pinned here so it stays that way."""
        user = self.make_user("readpath")
        token = RefreshToken.for_user(user).access_token

        with self.settings(CACHES=REDIS_CACHES), redis_down():
            with self.assertRaises(RevocationUnavailable):
                is_revoked(token)


class PasswordResetDurabilityTests(RevocationDurabilityMixin, APITestCase):
    """Test 1: the reset that is meant to lock somebody out."""

    def test_a_reset_blacklists_the_sessions_even_though_redis_is_down(self):
        user = self.make_user("resetter")
        self.open_sessions(user, count=2)

        self.client.post(
            "/api/auth/password/forgot/", {"email": user.email}, format="json"
        )
        body = mail.outbox[0].body
        uid = body.split("uid=")[1].split("&")[0]
        token = body.split("token=")[1].split()[0].strip()

        with self.settings(CACHES=REDIS_CACHES), redis_down():
            response = self.client.post(
                "/api/auth/password/reset/",
                {"uid": uid, "token": token, "password": NEW},
                format="json",
            )

        # The cache failure is reported rather than dressed up as success...
        self.assertEqual(response.status_code, 503)
        user.refresh_from_db()
        # ...the password really did change...
        self.assertTrue(user.check_password(NEW))
        # ...and no refresh token survives the reset.
        self.assertEqual(self.still_usable(user), 0)


class AdminSetPasswordDurabilityTests(RevocationDurabilityMixin, TenantAPIMixin, APITestCase):
    """Test 2: an admin resetting an account they believe is compromised."""

    def test_it_blacklists_the_members_sessions_even_though_redis_is_down(self):
        admin = self.make_user("setpwadmin", Role.ADMIN)
        member = self.make_user("setpwmember")
        self.member_for(admin, Role.ADMIN)
        self.member_for(member, Role.MEMBER)
        self.open_sessions(member, count=2)

        # force_authenticate rather than a bearer token on purpose: with Redis
        # down the revocation check would refuse the admin's own request before
        # the view ran, and this test is about what the view does.
        self.client.force_authenticate(admin)

        with self.settings(CACHES=REDIS_CACHES), redis_down():
            response = self.client.post(
                f"/api/auth/admin/members/{member.pk}/set-password/",
                {"password": NEW},
                format="json",
            )

        self.assertEqual(response.status_code, 503)
        member.refresh_from_db()
        self.assertTrue(member.check_password(NEW))
        self.assertEqual(self.still_usable(member), 0)


class MfaResetDurabilityTests(RevocationDurabilityMixin, TestCase):
    """Test 3: the reset for a member whose phone is gone."""

    def test_it_blacklists_the_sessions_even_though_redis_is_down(self):
        from accounts.mfa_views import reset_mfa

        user = self.make_user("mfareset")
        MfaDevice.objects.create(user=user, secret="JBSWY3DPEHPK3PXP", confirmed_at=timezone.now())
        self.open_sessions(user, count=2)

        with self.settings(CACHES=REDIS_CACHES), redis_down():
            with self.assertRaises(RevocationUnavailable):
                reset_mfa(user)

        # The authenticator is gone and so are the sessions it opened.
        self.assertFalse(MfaDevice.objects.filter(user=user).exists())
        self.assertEqual(self.still_usable(user), 0)


class ReplayDurabilityTests(RevocationDurabilityMixin, APITestCase):
    """Test 4: a rotated refresh token turning up again while Redis is down."""

    def replayed_token(self, user):
        """A refresh token that was rotated away long enough ago to be theft."""
        from accounts.views import REFRESH_REUSE_GRACE_SECONDS

        refresh = RefreshToken.for_user(user)
        raw = str(refresh)
        refresh.blacklist()
        BlacklistedToken.objects.filter(token__user=user).update(
            blacklisted_at=timezone.now()
            - timezone.timedelta(seconds=REFRESH_REUSE_GRACE_SECONDS + 60)
        )
        return raw

    def test_a_replay_is_refused_recorded_and_still_ends_every_session(self):
        user = self.make_user("replayer")
        raw = self.replayed_token(user)
        # A second device, signed in and not yet revoked.
        RefreshToken.for_user(user)
        self.assertEqual(self.still_usable(user), 1)

        self.client.cookies["refresh_token"] = raw
        with self.settings(CACHES=REDIS_CACHES), redis_down():
            with self.assertLogs("security", level="WARNING") as logs:
                response = self.client.post("/api/auth/refresh/")

        # The replay is refused the same way it is when Redis is healthy: a
        # cache outage must not give whoever holds a stolen token a different
        # answer from everybody else.
        self.assertEqual(response.status_code, 401)
        self.assertIn("security_event=refresh_token_replayed", "\n".join(logs.output))
        # And the defence itself happened: the other session is gone too.
        self.assertEqual(self.still_usable(user), 0)

    def test_the_same_replay_with_redis_healthy_is_unchanged(self):
        user = self.make_user("replayer_ok")
        raw = self.replayed_token(user)
        RefreshToken.for_user(user)

        self.client.cookies["refresh_token"] = raw
        with self.settings(CACHES=REDIS_CACHES), redis_healthy():
            with self.assertLogs("security", level="WARNING") as logs:
                response = self.client.post("/api/auth/refresh/")

        self.assertEqual(response.status_code, 401)
        self.assertIn("security_event=refresh_token_replayed", "\n".join(logs.output))
        self.assertEqual(self.still_usable(user), 0)


@override_settings(CACHES=REDIS_CACHES)
class LogoutDuringOutageTests(RevocationDurabilityMixin, APITestCase):
    """What logout does while Redis is down, pinned rather than changed.

    `LogoutView` requires authentication, and authentication asks the revocation
    store whether the access token still stands. With Redis down that question
    cannot be answered, so the request is refused before the view body runs and
    the refresh token in the cookie is *not* blacklisted. That is the existing
    fail-closed policy and this fix deliberately leaves it alone; the test is
    here so the behaviour is a decision on record rather than a surprise.
    """

    def test_logout_is_refused_and_the_cookie_token_is_left_alone(self):
        user = self.make_user("loggerout")
        refresh = RefreshToken.for_user(user)
        access = str(refresh.access_token)

        self.client.cookies["refresh_token"] = str(refresh)
        with redis_down():
            response = self.client.post(
                "/api/auth/logout/", HTTP_AUTHORIZATION=f"Bearer {access}"
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.still_usable(user), 1)
