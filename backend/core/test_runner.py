"""The test runner, with the production HTTPS redirect stood down.

`SECURE_SSL_REDIRECT` is on whenever DEBUG is off, which is exactly how CI runs
the suite. Django's test client speaks plain HTTP, so `SecurityMiddleware`
answered every single request with `301 https://testserver/...` and no test
reached a view.

The redirect is production behaviour worth keeping, so it is not weakened here:
it is switched off for the duration of the run and put back afterwards, in the
one place that is only ever entered by `manage.py test`. Tests that care about
the redirect itself turn it back on with `override_settings`, which is how
`core.tests_transport_security` pins that it still works.

Alternatives rejected: `follow=True` at the call sites (hides the real status
code), rewriting every test URL to https (hundreds of edits, and the next test
written would 301 again), and clearing the setting in `settings.py` (that is
the production control).
"""

from django.conf import settings
from django.test.runner import DiscoverRunner


class SecurityAwareTestRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self._ssl_redirect = settings.SECURE_SSL_REDIRECT
        settings.SECURE_SSL_REDIRECT = False

    def teardown_test_environment(self, **kwargs):
        settings.SECURE_SSL_REDIRECT = self._ssl_redirect
        super().teardown_test_environment(**kwargs)
