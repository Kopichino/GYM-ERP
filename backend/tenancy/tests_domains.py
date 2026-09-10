"""Custom domains: proving ownership, then routing by hostname.

DNS is mocked throughout. A test that did a real lookup would fail on a plane,
fail in CI behind a proxy, and pass or fail depending on somebody else's zone --
so what is under test here is our handling of each answer a resolver can give,
not the resolver.

The property that matters most is that an **unverified** domain does nothing.
Because the tenant is resolved *from* the hostname, honouring an unproved claim
would not be untidy -- it would let anyone who can type a domain name into this
form be served another gym's data.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APITestCase

from accounts.models import Role
from tenancy import context
from tenancy.domains import VerificationError, expected_record, verify
from tenancy.hosts import forget_hostnames, verified_hostnames
from tenancy.models import Domain, Membership, Organisation, Tenant
from tenancy.resolution import tenant_from_host

User = get_user_model()


def make_gym(slug, name):
    org = Organisation.objects.create(name=name, slug=slug)
    tenant = Tenant.objects.create(organisation=org, name=name, slug=f"{slug}-main")
    admin = User.objects.create_user(
        username=f"{slug}_owner", email=f"{slug}@example.com",
        password="pass12345", role=Role.ADMIN,
    )
    Membership.objects.create(user=admin, tenant=tenant, role=Role.ADMIN)
    return org, tenant, admin


def txt_returning(*values):
    """Patch the TXT lookup to return exactly these strings."""
    return patch("tenancy.domains._txt_values", return_value=list(values))


def txt_raising(message):
    return patch("tenancy.domains._txt_values", side_effect=VerificationError(message))


class TwoGyms(TestCase):
    def setUp(self):
        cache.clear()
        self.org_a, self.gym_a, self.owner_a = make_gym("alpha", "Alpha Fitness")
        self.org_b, self.gym_b, self.owner_b = make_gym("beta", "Beta Gym")
        with context.scope(self.gym_a):
            self.domain = Domain.objects.create(hostname="app.alpha.example")

    def tearDown(self):
        cache.clear()


class RecordTests(TwoGyms):
    def test_the_record_is_on_its_own_subdomain(self):
        """Not the apex: a second TXT there is a common way to break SPF."""
        record = expected_record(self.domain)
        self.assertEqual(record["type"], "TXT")
        self.assertEqual(record["name"], "_ironcore-verify.app.alpha.example")
        self.assertEqual(record["value"], self.domain.verification_token)

    def test_each_domain_gets_its_own_token(self):
        with context.scope(self.gym_b):
            other = Domain.objects.create(hostname="app.beta.example")
        self.assertNotEqual(self.domain.verification_token, other.verification_token)

    def test_a_hostname_is_stored_lowercase_and_without_a_trailing_dot(self):
        with context.scope(self.gym_b):
            d = Domain.objects.create(hostname="App.BETA.Example.")
        self.assertEqual(d.hostname, "app.beta.example")


class VerificationTests(TwoGyms):
    def test_a_matching_record_verifies(self):
        with txt_returning(self.domain.verification_token):
            verify(self.domain)
        self.domain.refresh_from_db()
        self.assertTrue(self.domain.is_verified)
        self.assertEqual(self.domain.last_error, "")

    def test_the_token_among_other_records_still_verifies(self):
        """Domains legitimately carry several TXT values."""
        with txt_returning("v=spf1 include:example.com ~all", self.domain.verification_token):
            verify(self.domain)
        self.domain.refresh_from_db()
        self.assertTrue(self.domain.is_verified)

    def test_a_wrong_value_does_not_verify_and_says_what_was_found(self):
        with txt_returning("some-other-token"):
            with self.assertRaises(VerificationError) as caught:
                verify(self.domain)
        self.domain.refresh_from_db()
        self.assertFalse(self.domain.is_verified)
        self.assertIn("some-other-token", str(caught.exception))

    def test_a_missing_record_is_an_ordinary_answer_not_a_crash(self):
        with txt_raising("No TXT record found at that name."):
            with self.assertRaises(VerificationError):
                verify(self.domain)
        self.domain.refresh_from_db()
        self.assertFalse(self.domain.is_verified)
        self.assertIn("No TXT record", self.domain.last_error)

    def test_re_verifying_keeps_the_original_timestamp(self):
        """Otherwise a re-check makes an old domain look freshly proved."""
        with txt_returning(self.domain.verification_token):
            verify(self.domain)
        self.domain.refresh_from_db()
        first = self.domain.verified_at

        with txt_returning(self.domain.verification_token):
            verify(self.domain)
        self.domain.refresh_from_db()
        self.assertEqual(self.domain.verified_at, first)

    def test_a_failed_recheck_does_not_unverify_a_live_domain(self):
        """A resolver blip must not take a gym's site off the air."""
        with txt_returning(self.domain.verification_token):
            verify(self.domain)
        with txt_raising("The DNS lookup timed out."):
            with self.assertRaises(VerificationError):
                verify(self.domain)
        self.domain.refresh_from_db()
        self.assertTrue(self.domain.is_verified)


class HostResolutionTests(TwoGyms):
    def test_an_unverified_domain_resolves_to_nothing(self):
        """The whole reason verification exists."""
        self.assertIsNone(tenant_from_host("app.alpha.example"))

    def test_a_verified_domain_resolves_to_its_gym(self):
        with txt_returning(self.domain.verification_token):
            verify(self.domain)
        self.assertEqual(tenant_from_host("app.alpha.example"), self.gym_a)

    def test_it_never_resolves_to_another_gym(self):
        with txt_returning(self.domain.verification_token):
            verify(self.domain)
        self.assertNotEqual(tenant_from_host("app.alpha.example"), self.gym_b)

    def test_the_port_is_ignored(self):
        with txt_returning(self.domain.verification_token):
            verify(self.domain)
        self.assertEqual(tenant_from_host("app.alpha.example:8000"), self.gym_a)

    def test_case_and_a_trailing_dot_do_not_matter(self):
        with txt_returning(self.domain.verification_token):
            verify(self.domain)
        self.assertEqual(tenant_from_host("APP.Alpha.Example."), self.gym_a)

    def test_an_unknown_host_resolves_to_nothing(self):
        self.assertIsNone(tenant_from_host("somewhere-else.example"))

    def test_an_empty_host_is_not_an_error(self):
        self.assertIsNone(tenant_from_host(""))
        self.assertIsNone(tenant_from_host(None))

    def test_a_suspended_gyms_domain_stops_resolving(self):
        with txt_returning(self.domain.verification_token):
            verify(self.domain)
        Tenant.objects.filter(pk=self.gym_a.pk).update(is_active=False)
        self.assertIsNone(tenant_from_host("app.alpha.example"))


class AllowedHostTests(TwoGyms):
    def test_an_unverified_domain_is_not_an_allowed_host(self):
        forget_hostnames()
        self.assertNotIn("app.alpha.example", verified_hostnames())

    def test_verifying_makes_it_an_allowed_host(self):
        with txt_returning(self.domain.verification_token):
            verify(self.domain)
        forget_hostnames()
        self.assertIn("app.alpha.example", verified_hostnames())


class DomainApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.org_a, self.gym_a, self.owner_a = make_gym("alpha", "Alpha Fitness")
        self.org_b, self.gym_b, self.owner_b = make_gym("beta", "Beta Gym")

    def tearDown(self):
        cache.clear()

    def base(self, tenant):
        return f"/api/t/{tenant.slug}/tenancy"

    def test_an_admin_adds_a_domain_and_is_told_which_record_to_create(self):
        self.client.force_authenticate(self.owner_a)
        resp = self.client.post(
            f"{self.base(self.gym_a)}/domains/", {"hostname": "app.alpha.example"}
        )
        self.assertEqual(resp.status_code, 201)
        self.assertFalse(resp.data["is_verified"])
        record = resp.data["dns_record"]
        self.assertEqual(record["type"], "TXT")
        self.assertEqual(record["name"], "_ironcore-verify.app.alpha.example")

    def test_a_url_instead_of_a_hostname_is_refused_with_a_reason(self):
        """The commonest paste error, and it would silently never match."""
        self.client.force_authenticate(self.owner_a)
        resp = self.client.post(
            f"{self.base(self.gym_a)}/domains/", {"hostname": "https://app.alpha.example/"}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("without http", str(resp.data["hostname"]))

    def test_a_domain_cannot_be_claimed_twice_across_the_platform(self):
        self.client.force_authenticate(self.owner_a)
        self.client.post(f"{self.base(self.gym_a)}/domains/", {"hostname": "shared.example"})
        self.client.force_authenticate(self.owner_b)
        resp = self.client.post(
            f"{self.base(self.gym_b)}/domains/", {"hostname": "shared.example"}
        )
        self.assertEqual(resp.status_code, 400)
        # Says it is taken without saying by whom -- that would leak who else
        # is on the platform.
        self.assertNotIn("alpha", str(resp.data).lower())

    def test_an_admin_sees_only_their_own_gyms_domains(self):
        self.client.force_authenticate(self.owner_a)
        self.client.post(f"{self.base(self.gym_a)}/domains/", {"hostname": "app.alpha.example"})
        self.client.force_authenticate(self.owner_b)
        listed = self.client.get(f"{self.base(self.gym_b)}/domains/")
        self.assertEqual(listed.data["results"], [])

    def test_an_admin_cannot_verify_another_gyms_domain(self):
        self.client.force_authenticate(self.owner_a)
        created = self.client.post(
            f"{self.base(self.gym_a)}/domains/", {"hostname": "app.alpha.example"}
        )
        domain_id = created.data["id"]

        self.client.force_authenticate(self.owner_b)
        resp = self.client.post(f"{self.base(self.gym_b)}/domains/{domain_id}/verify/")
        self.assertEqual(resp.status_code, 404)

    def test_a_member_cannot_add_a_domain(self):
        member = User.objects.create_user(
            username="alpha_member", email="am@example.com",
            password="pass12345", role=Role.MEMBER,
        )
        Membership.objects.create(user=member, tenant=self.gym_a, role=Role.MEMBER)
        self.client.force_authenticate(member)
        resp = self.client.post(
            f"{self.base(self.gym_a)}/domains/", {"hostname": "app.alpha.example"}
        )
        self.assertEqual(resp.status_code, 403)

    def test_verifying_through_the_api_makes_it_live(self):
        self.client.force_authenticate(self.owner_a)
        created = self.client.post(
            f"{self.base(self.gym_a)}/domains/", {"hostname": "app.alpha.example"}
        )
        token = Domain.unscoped.get(pk=created.data["id"]).verification_token

        with txt_returning(token):
            resp = self.client.post(
                f"{self.base(self.gym_a)}/domains/{created.data['id']}/verify/"
            )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["is_verified"])
        self.assertEqual(tenant_from_host("app.alpha.example"), self.gym_a)

    def test_a_failed_verification_answers_400_with_the_record_repeated(self):
        """So the owner can compare what they published against what is wanted."""
        self.client.force_authenticate(self.owner_a)
        created = self.client.post(
            f"{self.base(self.gym_a)}/domains/", {"hostname": "app.alpha.example"}
        )
        with txt_raising("No TXT record found at that name."):
            resp = self.client.post(
                f"{self.base(self.gym_a)}/domains/{created.data['id']}/verify/"
            )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("No TXT record", resp.data["detail"])
        self.assertEqual(resp.data["dns_record"]["type"], "TXT")

    def test_an_unverified_domain_cannot_be_made_primary(self):
        self.client.force_authenticate(self.owner_a)
        created = self.client.post(
            f"{self.base(self.gym_a)}/domains/", {"hostname": "app.alpha.example"}
        )
        resp = self.client.post(
            f"{self.base(self.gym_a)}/domains/{created.data['id']}/make-primary/"
        )
        self.assertEqual(resp.status_code, 400)


class CertificateTests(TwoGyms):
    def test_an_unverified_domain_is_refused_a_certificate(self):
        """Asking a host to serve a name nobody has proved they own is the same
        hole the TXT check closes."""
        from tenancy.certificates import request_certificate

        with self.assertRaises(ValueError):
            request_certificate(self.domain)

    def test_with_no_provider_configured_it_stays_pending_and_says_so(self):
        from tenancy.certificates import ManualProvider, provider, request_certificate

        self.assertIsInstance(provider(), ManualProvider)
        with txt_returning(self.domain.verification_token):
            verify(self.domain)
        request_certificate(self.domain)
        self.domain.refresh_from_db()
        self.assertEqual(self.domain.certificate, Domain.Certificate.PENDING)
