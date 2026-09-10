"""The Django admin route is configurable, and can be switched off entirely.

It is a full read/write console over every table in every gym, behind a
password and nothing else -- no JWT, no tenant scoping, no second factor. At
the default path it is found by scanning for "/admin/", which is the first
thing anything pointed at a Django host tries.

Moving it is not security by itself; an attacker who knows the path is exactly
where they were before. What it does is take the console out of undirected
scanning, and `DJANGO_ADMIN_ENABLED=False` removes it from the attack surface
altogether once day-to-day work happens in the app's own admin dashboard.
"""

from django.test import TestCase, override_settings
from django.urls import clear_url_caches, resolve
from django.urls.exceptions import Resolver404

import importlib

from django.conf import settings


def _reloaded_urlconf():
    """Re-import the root URLconf so a changed setting is actually applied.

    `urlpatterns` is built at import time, so `override_settings` alone changes
    nothing -- the module has to be re-executed and the resolver's caches
    dropped, or the test asserts against the URLconf built at startup.
    """
    module = importlib.import_module(settings.ROOT_URLCONF)
    importlib.reload(module)
    clear_url_caches()
    return module


class AdminExposureTests(TestCase):
    def tearDown(self):
        # Put the process-wide URLconf back, or every later test resolves
        # against whatever this one left behind.
        _reloaded_urlconf()
        super().tearDown()

    @override_settings(DJANGO_ADMIN_ENABLED=True, DJANGO_ADMIN_URL="admin/")
    def test_the_default_still_serves_the_admin(self):
        _reloaded_urlconf()
        self.assertTrue(resolve("/admin/login/").route.startswith("admin/"))

    @override_settings(DJANGO_ADMIN_ENABLED=True, DJANGO_ADMIN_URL="back-office-9f2a/")
    def test_it_can_be_moved_off_the_default_path(self):
        _reloaded_urlconf()
        self.assertTrue(resolve("/back-office-9f2a/login/"))
        with self.assertRaises(Resolver404):
            resolve("/admin/login/")

    @override_settings(DJANGO_ADMIN_ENABLED=False, DJANGO_ADMIN_URL="admin/")
    def test_it_can_be_removed_entirely(self):
        _reloaded_urlconf()
        with self.assertRaises(Resolver404):
            resolve("/admin/login/")

    @override_settings(DJANGO_ADMIN_ENABLED=False)
    def test_disabling_the_admin_leaves_the_api_working(self):
        # The point of the switch is to drop the console, not the product.
        _reloaded_urlconf()
        self.assertTrue(resolve("/api/health/"))
        self.assertTrue(resolve("/api/auth/login/"))
