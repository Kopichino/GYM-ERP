"""Who a request is counted as coming from, under a proxy and without one.

`NUM_PROXIES` is the only thing that makes `X-Forwarded-For` worth reading:
anybody can send that header, so the address is trustworthy only at the position
the trusted proxies wrote it. These tests pin both halves -- the default that
trusts nothing, and the configured case -- and that the security log agrees with
the rate limiter rather than recording the proxy.
"""

from django.test import RequestFactory, TestCase, override_settings
from rest_framework.settings import api_settings
from rest_framework.throttling import BaseThrottle

from core.client_ip import client_ip
from core.security_log import security_event

CLIENT = "203.0.113.7"
PROXY = "10.0.0.9"


def request_with(xff=None, remote=PROXY):
    headers = {"HTTP_X_FORWARDED_FOR": xff} if xff else {}
    return RequestFactory().get("/", REMOTE_ADDR=remote, **headers)


def with_num_proxies(value):
    """DRF caches its settings, so the override has to invalidate that too."""
    api_settings._cached_attrs.discard("NUM_PROXIES")
    api_settings.__dict__.pop("NUM_PROXIES", None)
    return override_settings(REST_FRAMEWORK={**api_settings.user_settings, "NUM_PROXIES": value})


class ClientIpTests(TestCase):
    def tearDown(self):
        api_settings.__dict__.pop("NUM_PROXIES", None)

    def test_with_no_proxy_configured_only_the_socket_address_counts(self):
        """The default. A forged header must not be able to change the answer."""
        with with_num_proxies(0):
            self.assertEqual(client_ip(request_with(xff=f"{CLIENT}, 198.51.100.4")), PROXY)
            self.assertEqual(client_ip(request_with()), PROXY)

    def test_behind_one_proxy_the_last_forwarded_entry_counts(self):
        with with_num_proxies(1):
            self.assertEqual(client_ip(request_with(xff=CLIENT)), CLIENT)
            # A client that prepends its own entries cannot displace the one the
            # trusted proxy appended.
            self.assertEqual(client_ip(request_with(xff=f"1.2.3.4, {CLIENT}")), CLIENT)

    def test_behind_two_proxies_the_second_from_the_right_counts(self):
        with with_num_proxies(2):
            self.assertEqual(client_ip(request_with(xff=f"{CLIENT}, 198.51.100.4")), CLIENT)

    def test_it_matches_what_the_rate_limiter_counts(self):
        """One implementation: the limiter's. They cannot drift apart."""
        for proxies in (0, 1, 2):
            with with_num_proxies(proxies):
                request = request_with(xff=f"{CLIENT}, 198.51.100.4")
                self.assertEqual(client_ip(request), BaseThrottle().get_ident(request))

    def test_no_request_is_not_an_error(self):
        self.assertEqual(client_ip(None), "")


class SecurityLogIpTests(TestCase):
    """The audit trail names the caller, not the proxy in front of them."""

    def tearDown(self):
        api_settings.__dict__.pop("NUM_PROXIES", None)

    def test_the_log_records_the_forwarded_client_when_proxies_are_configured(self):
        with with_num_proxies(1):
            with self.assertLogs("security", level="INFO") as logs:
                security_event("probe", request=request_with(xff=CLIENT))
        self.assertIn(f"ip={CLIENT}", logs.output[0])

    def test_the_log_ignores_a_forged_header_by_default(self):
        with with_num_proxies(0):
            with self.assertLogs("security", level="INFO") as logs:
                security_event("probe", request=request_with(xff="1.2.3.4"))
        self.assertIn(f"ip={PROXY}", logs.output[0])
        self.assertNotIn("1.2.3.4", logs.output[0])
