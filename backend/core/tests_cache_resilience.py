"""What a Redis outage may and may not break.

The rule these tests hold in place: a cache that cannot be reached degrades the
things that exist for availability (throttle counters) and refuses the things
that exist for security (whether a session has been ended). Before this, a
single unreachable Redis answered *every* request with a 500, public ones
included.

Nothing here needs a real Redis. The failure is injected by making the Django
Redis backend's own methods raise the exception a real outage produces.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.core.cache.backends.redis import RedisCache
from django.test import TestCase, override_settings
from redis.exceptions import ConnectionError as RedisConnectionError
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import Role
from accounts.revocation import (
    RevocationUnavailable,
    end_access_tokens,
    is_revoked,
    revoke_access_token,
)
from core.cache import ResilientRedisCache

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


class ResilientCacheTests(TestCase):
    """The backend itself: degrade on a Redis error, propagate anything else."""

    def setUp(self):
        self.cache = ResilientRedisCache("redis://127.0.0.1:6399/0", {})

    def test_a_healthy_get_is_passed_straight_through(self):
        with mock.patch.object(RedisCache, "get", return_value="cached") as parent:
            self.assertEqual(self.cache.get("key", "fallback"), "cached")
        parent.assert_called_once()

    def test_a_healthy_set_is_passed_straight_through(self):
        with mock.patch.object(RedisCache, "set", return_value=None) as parent:
            self.cache.set("key", "value", timeout=60)
        parent.assert_called_once()

    def test_a_redis_outage_reads_as_a_miss(self):
        with mock.patch.object(RedisCache, "get", side_effect=RedisConnectionError("down")):
            self.assertEqual(self.cache.get("key", "fallback"), "fallback")

    def test_a_redis_outage_drops_writes_rather_than_raising(self):
        with mock.patch.object(RedisCache, "set", side_effect=RedisConnectionError("down")):
            self.assertIsNone(self.cache.set("key", "value", timeout=60))

    def test_add_reports_not_acquired_while_redis_is_down(self):
        """`add` is how a caller claims something: unknown must not read as won."""
        with mock.patch.object(RedisCache, "add", side_effect=RedisConnectionError("down")):
            self.assertIs(self.cache.add("key", "value"), False)

    def test_an_unrelated_error_is_not_swallowed(self):
        """E. Only Redis failures degrade. A bug here must still surface."""
        with mock.patch.object(RedisCache, "get", side_effect=ValueError("a real bug")):
            with self.assertRaises(ValueError):
                self.cache.get("key")


@override_settings(CACHES=REDIS_CACHES)
class RedisOutageRequestTests(TestCase):
    """What a request does while Redis is unreachable."""

    def setUp(self):
        self.client = APIClient(headers={"host": "testserver"})
        self.user = get_user_model().objects.create_user(
            username="cacheprobe", email="cacheprobe@example.com",
            password="pass12345-long", role=Role.MEMBER,
        )
        self.access = str(RefreshToken.for_user(self.user).access_token)

    def authenticated(self):
        return self.client.get("/api/auth/me/", HTTP_AUTHORIZATION=f"Bearer {self.access}")

    def test_a_public_request_survives_the_outage(self):
        """B. Throttling reads the cache on every request; it used to 500 here."""
        with mock.patch.object(RedisCache, "get", side_effect=RedisConnectionError("down")), \
             mock.patch.object(RedisCache, "set", side_effect=RedisConnectionError("down")):
            response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)

    def test_an_authenticated_request_is_refused_not_waved_through(self):
        """C. Revocation cannot be checked, so the request must not be served."""
        with mock.patch.object(RedisCache, "get", side_effect=RedisConnectionError("down")), \
             mock.patch.object(RedisCache, "set", side_effect=RedisConnectionError("down")):
            response = self.authenticated()
        self.assertEqual(response.status_code, 503)

    def test_normal_service_resumes_once_redis_is_back(self):
        """D. The degradation is for the duration of the outage and no longer."""
        with mock.patch.object(RedisCache, "get", side_effect=RedisConnectionError("down")):
            self.assertEqual(self.authenticated().status_code, 503)

        # Redis answering again. A healthy cache returns the caller's default on
        # a miss, which is what the throttle counts on and what a mock returning
        # a bare None would not reproduce.
        def healthy_miss(key, default=None, version=None):
            return default

        with mock.patch.object(RedisCache, "get", side_effect=healthy_miss), \
             mock.patch.object(RedisCache, "set", return_value=None):
            self.assertEqual(self.authenticated().status_code, 200)


@override_settings(CACHES=REDIS_CACHES)
class RevocationFailsClosedTests(TestCase):
    """C. The security half: never answer "not revoked" from a dead cache."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="revprobe", email="revprobe@example.com",
            password="pass12345-long", role=Role.MEMBER,
        )
        self.token = RefreshToken.for_user(self.user).access_token

    def test_is_revoked_refuses_rather_than_returning_false(self):
        with mock.patch.object(RedisCache, "get", side_effect=RedisConnectionError("down")):
            with self.assertRaises(RevocationUnavailable):
                is_revoked(self.token)

    def test_logging_out_fails_loudly_rather_than_silently(self):
        with mock.patch.object(RedisCache, "set", side_effect=RedisConnectionError("down")):
            with self.assertRaises(RevocationUnavailable):
                revoke_access_token(self.token)
            with self.assertRaises(RevocationUnavailable):
                end_access_tokens(self.user)

    def test_the_revocation_cache_is_the_strict_one(self):
        """The two aliases must not collapse into one resilient backend."""
        self.assertNotIsInstance(caches["revocation"], ResilientRedisCache)
        self.assertIsInstance(caches["default"], ResilientRedisCache)

    def test_revocation_still_works_when_redis_is_healthy(self):
        """A. Unchanged behaviour on the happy path."""
        with mock.patch.object(RedisCache, "get", return_value=None):
            self.assertFalse(is_revoked(self.token))
        with mock.patch.object(RedisCache, "get", return_value=1):
            self.assertTrue(is_revoked(self.token))
