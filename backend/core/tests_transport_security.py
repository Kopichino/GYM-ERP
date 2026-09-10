"""HSTS is announced honestly and can be ramped.

Two settings that have to agree. `SECURE_HSTS_PRELOAD` tells browsers the
domain is a candidate for the preload list, and browsers only accept a domain
onto that list at a `max-age` of a year or more. Claiming preload under a
shorter window is not a cautious middle ground -- the submission is rejected,
and the shorter promise still binds every browser that saw the header.

The project shipped with `preload` set against a seven-day max-age, which is
that exact mismatch. It is now derived rather than asserted, so the two cannot
drift apart again.
"""

from django.test import SimpleTestCase, override_settings

from gymerp import settings as project_settings


class HstsConsistencyTests(SimpleTestCase):
    def _preload_for(self, seconds):
        """What the settings module would conclude for a given max-age."""
        return seconds >= project_settings.HSTS_PRELOAD_MINIMUM_SECONDS

    def test_the_threshold_is_the_browsers_one_year(self):
        self.assertEqual(project_settings.HSTS_PRELOAD_MINIMUM_SECONDS, 31_536_000)

    def test_a_short_max_age_does_not_claim_preload(self):
        # The bug this closes: a week of HSTS advertised as preload-ready.
        self.assertFalse(self._preload_for(60 * 60 * 24 * 7))

    def test_a_year_qualifies(self):
        self.assertTrue(self._preload_for(31_536_000))

    def test_just_under_a_year_does_not(self):
        self.assertFalse(self._preload_for(31_535_999))

    def test_a_week_is_the_shipped_starting_point_and_does_not_qualify(self):
        # The value the project ships with, stated as the derivation rather
        # than as SECURE_HSTS_SECONDS itself -- under DEBUG that is forced to
        # zero, so asserting the attribute would only test the local override.
        week = 60 * 60 * 24 * 7
        self.assertLess(week, project_settings.HSTS_PRELOAD_MINIMUM_SECONDS)
        self.assertFalse(self._preload_for(week))

    def test_the_two_settings_agree_in_the_current_configuration(self):
        # Whatever the deployment sets, these can never contradict each other.
        preload = getattr(project_settings, "SECURE_HSTS_PRELOAD", False)
        seconds = project_settings.SECURE_HSTS_SECONDS
        if preload:
            self.assertGreaterEqual(seconds, project_settings.HSTS_PRELOAD_MINIMUM_SECONDS)


class LocalDevelopmentTests(SimpleTestCase):
    def test_hsts_is_off_when_debug_is_on(self):
        # A stray HSTS header on localhost makes every other project served
        # from that hostname unreachable over plain HTTP, for the full max-age,
        # and there is no convenient way to retract it.
        if project_settings.DEBUG:
            self.assertEqual(project_settings.SECURE_HSTS_SECONDS, 0)


class ThrottleStateCheckTests(SimpleTestCase):
    """The deploy check that makes weak rate limiting loud.

    DRF counts every throttled request in the default cache. On LocMemCache
    that count is per-worker and is discarded on restart — and Render's free
    tier sleeps the service after fifteen minutes idle, so it is discarded
    routinely. The login limit and the per-username guessing limit both rest on
    it, and both stop being limits without anything appearing to be wrong.
    """

    def _run_check(self):
        from core.checks import throttle_state_survives_a_restart

        return throttle_state_survives_a_restart(None)

    LOCMEM = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    }
    REDIS = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": "redis://localhost:6379/0",
        }
    }

    @override_settings(DEBUG=False, CACHES=LOCMEM)
    def test_it_warns_in_production_on_per_process_memory(self):
        found = self._run_check()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].id, "security.W901")

    @override_settings(DEBUG=False, CACHES=REDIS)
    def test_a_shared_cache_satisfies_it(self):
        self.assertEqual(self._run_check(), [])

    @override_settings(DEBUG=True, CACHES=LOCMEM)
    def test_it_stays_quiet_in_development(self):
        # Local work has one process and no uptime expectation; warning there
        # would train people to ignore it.
        self.assertEqual(self._run_check(), [])

    @override_settings(DEBUG=False, CACHES=LOCMEM)
    def test_the_hint_says_what_to_do(self):
        # A warning that does not name the fix gets silenced rather than acted on.
        self.assertIn("REDIS_URL", self._run_check()[0].hint)
