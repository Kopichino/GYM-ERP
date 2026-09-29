"""The refresh cookie, and the deployment shape it assumes.

The cookie is what keeps somebody signed in: the access token lives in memory
only, so every reload and every fifteen-minute expiry depends on the browser
sending this back. Whether it does is decided by the topology -- a browser that
blocks third-party cookies drops it when the portal and the API are different
sites, and the member is signed out over and over with nothing in the log.

So these tests pin the attributes (HttpOnly, Secure, SameSite), that SameSite
comes from configuration rather than being assumed, and that the origins the API
trusts are the ones someone configured rather than anything that showed up.
No real domain appears anywhere: the point is that `app.` and `api.` of *a*
domain work, not which domain it will be.
"""

from importlib import reload

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings

from accounts.models import Role
from core.testing import TenantAPIMixin

PASSWORD = "cookie-topology-pass-1"


class RefreshCookieAttributeTests(TenantAPIMixin, TestCase):
    """What the browser is actually told when a session starts."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="cookieuser", email="cookieuser@example.com",
            password=PASSWORD, role=Role.MEMBER,
        )
        self.member_for(self.user, Role.MEMBER)

    def login(self):
        return self.client.post(
            "/api/auth/login/",
            {"username": "cookieuser", "password": PASSWORD},
            content_type="application/json",
        )

    def cookie(self, response):
        self.assertIn(settings.JWT_REFRESH_COOKIE_NAME, response.cookies, response.content)
        return response.cookies[settings.JWT_REFRESH_COOKIE_NAME]

    @override_settings(MFA_REQUIRED=False)
    def test_the_cookie_is_httponly_and_scoped_to_the_auth_paths(self):
        cookie = self.cookie(self.login())
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["path"], "/api/auth/")
        # Host-only: no Domain attribute, so it is never widened to siblings of
        # the API host.
        self.assertEqual(cookie["domain"], "")

    @override_settings(MFA_REQUIRED=False)
    def test_the_cookie_carries_the_configured_samesite(self):
        cookie = self.cookie(self.login())
        self.assertEqual(cookie["samesite"], settings.JWT_REFRESH_COOKIE_SAMESITE)

    @override_settings(
        MFA_REQUIRED=False,
        JWT_REFRESH_COOKIE_SECURE=True,
        JWT_REFRESH_COOKIE_SAMESITE="Lax",
    )
    def test_production_attributes_are_secure_and_same_site(self):
        """A. What a production deployment sends: Secure, HttpOnly, Lax."""
        cookie = self.cookie(self.login())
        self.assertTrue(cookie["secure"])
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")

    @override_settings(
        MFA_REQUIRED=False,
        JWT_REFRESH_COOKIE_SECURE=True,
        JWT_REFRESH_COOKIE_SAMESITE="None",
    )
    def test_a_cross_site_deployment_can_still_be_configured(self):
        """Supported, but only deliberately -- and only alongside Secure."""
        cookie = self.cookie(self.login())
        self.assertEqual(cookie["samesite"], "None")
        self.assertTrue(cookie["secure"])


class CookiePolicyConfigurationTests(TestCase):
    """The settings module's own rules about the cookie."""

    def test_the_default_is_the_same_site_topology(self):
        """D. app.<domain> + api.<domain> is what a plain deployment gets."""
        self.assertEqual(settings.JWT_REFRESH_COOKIE_SAMESITE, "Lax")

    def test_samesite_none_without_secure_is_refused(self):
        """Browsers reject that pair; better to fail at boot than in the field."""
        import gymerp.settings as settings_module

        with self.settings():
            with self.assertRaises(ImproperlyConfigured):
                self._reload_with(settings_module, DEBUG="True",
                                  JWT_REFRESH_COOKIE_SAMESITE="None")

    def test_an_unknown_samesite_value_is_refused(self):
        import gymerp.settings as settings_module

        with self.assertRaises(ImproperlyConfigured):
            self._reload_with(settings_module, JWT_REFRESH_COOKIE_SAMESITE="sometimes")

    def _reload_with(self, settings_module, **env):
        """Re-import settings under a given environment, then put it back."""
        import os

        previous = {key: os.environ.get(key) for key in env}
        os.environ.update(env)
        try:
            reload(settings_module)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            reload(settings_module)


class TrustedOriginTests(TestCase):
    """B and C. What the API trusts is configured, not inferred or opened up."""

    def test_cors_is_never_open_to_everything(self):
        self.assertFalse(getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False))
        self.assertFalse(getattr(settings, "CORS_ORIGIN_ALLOW_ALL", False))
        # A regex list is allowed (local development uses one for the dev
        # server's port), but not one that matches any origin at all.
        for pattern in getattr(settings, "CORS_ALLOWED_ORIGIN_REGEXES", []):
            self.assertNotIn(pattern, (".*", "^.*$", ".+"))

    def test_cors_credentials_are_allowed_only_alongside_an_explicit_list(self):
        """Credentialed CORS with a wildcard is the combination to avoid."""
        if settings.CORS_ALLOW_CREDENTIALS:
            self.assertTrue(settings.CORS_ALLOWED_ORIGINS)
            self.assertNotIn("*", settings.CORS_ALLOWED_ORIGINS)

    def test_every_trusted_origin_names_a_scheme(self):
        """A bare hostname in either list silently trusts nothing at all."""
        for origin in list(settings.CORS_ALLOWED_ORIGINS) + list(settings.CSRF_TRUSTED_ORIGINS):
            self.assertRegex(origin, r"^https?://")

    @override_settings(
        CORS_ALLOWED_ORIGINS=["https://app.example.test"],
        CSRF_TRUSTED_ORIGINS=["https://app.example.test"],
        FRONTEND_URL="https://app.example.test",
    )
    def test_the_same_site_topology_configures_without_code_changes(self):
        """D. Nothing here hard-codes a domain: both come from configuration."""
        self.assertEqual(settings.CORS_ALLOWED_ORIGINS, ["https://app.example.test"])
        self.assertEqual(settings.CSRF_TRUSTED_ORIGINS, ["https://app.example.test"])
        self.assertTrue(settings.FRONTEND_URL.startswith("https://app."))

    def test_local_development_still_trusts_the_vite_dev_server(self):
        """E. The developer default keeps working."""
        self.assertTrue(
            any("localhost:5173" in origin for origin in settings.CORS_ALLOWED_ORIGINS),
            settings.CORS_ALLOWED_ORIGINS,
        )
