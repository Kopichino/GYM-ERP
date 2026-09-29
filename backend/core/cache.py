"""Two caches, because two different things live in one.

Most of what this application puts in the cache is there for *availability*:
rate-limit counters, the verified-hostname list. Losing them costs accuracy for
a few minutes. Redis going down should not take the API down with it, and it
did: DRF reads a throttle counter on every request, the read raised, and every
request -- including public ones -- answered 500.

One thing in the cache is there for *security*: `accounts.revocation`, which is
how an access token is ended before it expires. Answering "not revoked" because
the cache is unreachable would let a token somebody has just logged out of keep
working, so that one must not fail open.

So: `default` is resilient and `revocation` is strict. Both point at the same
Redis in production; the difference is what happens when it cannot be reached.

`RedisError` only. A `KeyError` or a `TypeError` from this module's own code is
a bug and must still surface -- swallowing everything would hide exactly the
failures that need fixing.
"""

import logging

from django.core.cache.backends.redis import RedisCache

logger = logging.getLogger(__name__)


def redis_error_class():
    """The one exception family a cache outage produces."""
    from redis.exceptions import RedisError

    return RedisError


class ResilientRedisCache(RedisCache):
    """Redis for the things a brief outage may degrade rather than break.

    Reads answer with their default and writes are dropped while Redis is
    unreachable. For throttling that means the limit stops counting for the
    duration -- deliberate, and documented in the README: the alternative was a
    platform-wide outage every time the cache blinked. The other limits that do
    not depend on this cache (the database's own constraints, MFA, tenant
    scoping, authentication) are untouched.
    """

    def _degrade(self, operation, error, default=None):
        logger.warning("cache unavailable (%s): %s", operation, error)
        return default

    def get(self, key, default=None, version=None):
        try:
            return super().get(key, default, version)
        except redis_error_class() as error:
            return self._degrade("get", error, default)

    def get_many(self, keys, version=None):
        try:
            return super().get_many(keys, version)
        except redis_error_class() as error:
            return self._degrade("get_many", error, {})

    def set(self, key, value, timeout=None, version=None, client=None):
        try:
            return super().set(key, value, timeout, version)
        except redis_error_class() as error:
            return self._degrade("set", error)

    def add(self, key, value, timeout=None, version=None, client=None):
        try:
            return super().add(key, value, timeout, version)
        except redis_error_class() as error:
            # False: "somebody else already holds it" is the safe answer to give
            # a caller using add() as a lock while the cache is unreachable.
            return self._degrade("add", error, False)

    def touch(self, key, timeout=None, version=None):
        try:
            return super().touch(key, timeout, version)
        except redis_error_class() as error:
            return self._degrade("touch", error, False)

    def delete(self, key, version=None):
        try:
            return super().delete(key, version)
        except redis_error_class() as error:
            return self._degrade("delete", error, False)

    def incr(self, key, delta=1, version=None):
        try:
            return super().incr(key, delta, version)
        except redis_error_class() as error:
            # None rather than a number: a counter that cannot be read has no
            # value to report, and callers here treat it as "unknown".
            return self._degrade("incr", error)

    def clear(self):
        try:
            return super().clear()
        except redis_error_class() as error:
            return self._degrade("clear", error)
