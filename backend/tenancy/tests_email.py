"""Per-gym sending identity, and the platform identity that must stay separate.

Three properties, in order of how much damage getting them wrong would do:

1. **Platform mail is never tenant-branded.** A notice telling an owner their
   subscription lapsed must not arrive dressed as their own gym. That is how a
   legitimate message comes to look like a forgery, and it is the one mistake
   here that teaches people to distrust real mail.
2. **An unverified domain is not used.** Sending as a domain that cannot be
   authenticated is worse than not trying: it lands in spam and the gym never
   learns their reminders stopped arriving.
3. **One gym's identity is never used for another's members.**

DNS is mocked. A real lookup would make the suite depend on somebody else's
zone and on having a network.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from accounts.models import Role
from tenancy import context
from tenancy.email_identity import (
    SendingSetupError,
    dkim_ok,
    platform_sender,
    sender_for,
    spf_ok,
    verify,
)
from tenancy.models import Membership, Organisation, SendingDomain, Tenant

User = get_user_model()

PLATFORM = "IRONCORE Platform <billing@ironcore-platform.example>"


def make_gym(slug, name):
    org = Organisation.objects.create(name=name, slug=slug)
    tenant = Tenant.objects.create(organisation=org, name=name, slug=f"{slug}-main")
    return org, tenant


def txt(values):
    return patch("tenancy.email_identity._txt_values", return_value=values)


def cname(target):
    return patch("tenancy.email_identity._cname_target", return_value=target)


@override_settings(PLATFORM_FROM_EMAIL=PLATFORM)
class SenderChoiceTests(TestCase):
    def setUp(self):
        self.org, self.gym = make_gym("alpha", "Alpha Fitness")

    def test_a_gym_with_no_sending_domain_uses_the_platform_address(self):
        self.assertEqual(sender_for(self.gym), PLATFORM)

    def test_an_unverified_domain_is_not_used(self):
        """Sending unauthenticated mail is worse than sending none."""
        with context.scope(self.gym):
            SendingDomain.objects.create(domain="alpha.example")
        self.gym.refresh_from_db()
        self.assertEqual(sender_for(self.gym), PLATFORM)

    def test_spf_alone_is_not_enough(self):
        """SPF without DKIM still fails DMARC alignment at most receivers."""
        with context.scope(self.gym):
            identity = SendingDomain.objects.create(domain="alpha.example")
        SendingDomain.unscoped.filter(pk=identity.pk).update(
            spf_verified=True, dkim_verified=False
        )
        self.gym.refresh_from_db()
        self.assertEqual(sender_for(self.gym), PLATFORM)

    def test_a_fully_verified_domain_is_used_with_the_gyms_name(self):
        with context.scope(self.gym):
            identity = SendingDomain.objects.create(
                domain="alpha.example", from_local_part="no-reply"
            )
        SendingDomain.unscoped.filter(pk=identity.pk).update(
            spf_verified=True, dkim_verified=True
        )
        self.gym.refresh_from_db()
        self.assertEqual(sender_for(self.gym), "Alpha Fitness <no-reply@alpha.example>")

    def test_a_custom_from_name_wins_over_the_gym_name(self):
        with context.scope(self.gym):
            identity = SendingDomain.objects.create(
                domain="alpha.example", from_name="Alpha Team"
            )
        SendingDomain.unscoped.filter(pk=identity.pk).update(
            spf_verified=True, dkim_verified=True
        )
        self.gym.refresh_from_db()
        self.assertIn("Alpha Team", sender_for(self.gym))

    def test_no_tenant_at_all_still_has_a_sender(self):
        """Management commands and platform work run outside any gym."""
        self.assertEqual(sender_for(None), PLATFORM)


@override_settings(PLATFORM_FROM_EMAIL=PLATFORM)
class PlatformIdentityTests(TestCase):
    """The separation the spec asked for, asserted directly."""

    def setUp(self):
        self.org, self.gym = make_gym("alpha", "Alpha Fitness")
        with context.scope(self.gym):
            identity = SendingDomain.objects.create(domain="alpha.example")
        SendingDomain.unscoped.filter(pk=identity.pk).update(
            spf_verified=True, dkim_verified=True
        )
        self.gym.refresh_from_db()

    def test_the_platform_sender_ignores_the_tenant_in_scope(self):
        with context.scope(self.gym):
            self.assertEqual(platform_sender(), PLATFORM)

    def test_it_never_carries_a_gyms_domain(self):
        """Even with a fully verified gym identity sitting right there."""
        with context.scope(self.gym):
            self.assertNotIn("alpha.example", platform_sender())


class SpfTests(TestCase):
    def test_an_spf_record_naming_our_provider_passes(self):
        with txt(["v=spf1 include:spf.mtasv.net ~all"]):
            self.assertTrue(spf_ok("alpha.example"))

    def test_an_existing_record_with_ours_added_passes(self):
        """The normal case -- a gym already sends mail from that domain."""
        with txt(["v=spf1 include:_spf.google.com include:spf.mtasv.net ~all"]):
            self.assertTrue(spf_ok("alpha.example"))

    def test_an_spf_record_without_us_fails(self):
        with txt(["v=spf1 include:_spf.google.com ~all"]):
            self.assertFalse(spf_ok("alpha.example"))

    def test_a_non_spf_txt_record_is_ignored(self):
        with txt(["google-site-verification=abc123"]):
            self.assertFalse(spf_ok("alpha.example"))

    def test_no_records_at_all_fails_quietly(self):
        with txt([]):
            self.assertFalse(spf_ok("alpha.example"))


class DkimTests(TestCase):
    def setUp(self):
        self.org, self.gym = make_gym("alpha", "Alpha Fitness")
        with context.scope(self.gym):
            self.identity = SendingDomain.objects.create(
                domain="alpha.example",
                dkim_selector="pm-abc",
                dkim_value="k=rsa; p=MIGfMA0GCSq",
            )

    def test_a_matching_txt_key_passes(self):
        with txt(["k=rsa; p=MIGfMA0GCSq"]), cname(None):
            self.assertTrue(dkim_ok(self.identity))

    def test_a_wrapped_key_still_matches(self):
        """Registrars split long values; the reassembled string gains spaces."""
        with txt(["k=rsa;  p=MIGf MA0GCSq"]), cname(None):
            self.assertTrue(dkim_ok(self.identity))

    def test_a_cname_style_record_also_passes(self):
        """Some providers host the key and have the gym point at it."""
        with txt([]), cname("pm-abc.dkim.postmarkapp.example"):
            self.assertTrue(dkim_ok(self.identity))

    def test_nothing_published_fails(self):
        with txt([]), cname(None):
            self.assertFalse(dkim_ok(self.identity))

    def test_without_a_selector_there_is_nothing_to_check(self):
        """No provider configured means no key was ever issued."""
        with context.scope(self.gym):
            bare = SendingDomain(domain="beta.example")
        self.assertFalse(dkim_ok(bare))


class VerifyTests(TestCase):
    def setUp(self):
        self.org, self.gym = make_gym("alpha", "Alpha Fitness")
        with context.scope(self.gym):
            self.identity = SendingDomain.objects.create(
                domain="alpha.example", dkim_selector="pm-abc",
                dkim_value="k=rsa; p=KEY",
            )

    def test_both_records_present_verifies(self):
        with txt(["v=spf1 include:spf.mtasv.net ~all", "k=rsa; p=KEY"]), cname(None):
            verify(self.identity)
        self.assertTrue(self.identity.is_verified)
        self.assertEqual(self.identity.last_error, "")

    def test_only_spf_reports_which_half_is_missing(self):
        """Two records to add: 'not verified' would send an owner back to the
        one that was already right."""
        with txt(["v=spf1 include:spf.mtasv.net ~all"]), cname(None):
            verify(self.identity)
        self.assertTrue(self.identity.spf_verified)
        self.assertFalse(self.identity.dkim_verified)
        self.assertIn("DKIM", self.identity.last_error)
        self.assertNotIn("SPF", self.identity.last_error)

    def test_a_later_failure_does_not_unverify_a_working_domain(self):
        with txt(["v=spf1 include:spf.mtasv.net ~all", "k=rsa; p=KEY"]), cname(None):
            verify(self.identity)
        first = self.identity.verified_at

        with txt([]), cname(None):
            verify(self.identity)
        self.assertEqual(self.identity.verified_at, first)

    def test_verification_does_not_raise_for_a_missing_record(self):
        """That is the ordinary state during setup, not a fault."""
        with txt([]), cname(None):
            verify(self.identity)
        self.assertFalse(self.identity.is_verified)


class ProviderTests(TestCase):
    def test_with_no_credentials_it_refuses_rather_than_inventing_a_key(self):
        from tenancy.email_provider import ManualProvider, provider

        self.assertIsInstance(provider(), ManualProvider)
        org, gym = make_gym("alpha", "Alpha Fitness")
        with context.scope(gym):
            identity = SendingDomain.objects.create(domain="alpha.example")
        with self.assertRaises(SendingSetupError) as caught:
            provider().register(identity)
        self.assertIn("No email provider is configured", str(caught.exception))


class SendingDomainApiTests(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient

        self.client = APIClient()
        self.org_a, self.gym_a = make_gym("alpha", "Alpha Fitness")
        self.org_b, self.gym_b = make_gym("beta", "Beta Gym")
        self.owner_a = User.objects.create_user(
            username="alpha_owner", email="a@example.com",
            password="pass12345", role=Role.ADMIN,
        )
        self.owner_b = User.objects.create_user(
            username="beta_owner", email="b@example.com",
            password="pass12345", role=Role.ADMIN,
        )
        Membership.objects.create(user=self.owner_a, tenant=self.gym_a, role=Role.ADMIN)
        Membership.objects.create(user=self.owner_b, tenant=self.gym_b, role=Role.ADMIN)

    def base(self, tenant):
        return f"/api/t/{tenant.slug}/tenancy"

    def test_an_address_instead_of_a_domain_is_refused_with_a_reason(self):
        self.client.force_authenticate(self.owner_a)
        resp = self.client.post(
            f"{self.base(self.gym_a)}/sending-domain/",
            {"domain": "you@alpha.example"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("not a full address", str(resp.data["domain"]))

    def test_the_spf_row_is_offered_even_with_no_provider(self):
        """SPF does not depend on the provider issuing anything, so an owner
        can make a start while the platform's account is being set up."""
        self.client.force_authenticate(self.owner_a)
        resp = self.client.post(
            f"{self.base(self.gym_a)}/sending-domain/", {"domain": "alpha.example"}
        )
        self.assertEqual(resp.status_code, 201)
        purposes = [r["purpose"] for r in resp.data["dns_records"]]
        self.assertIn("SPF", purposes)
        self.assertNotIn("DKIM", purposes)

    def test_an_owner_cannot_see_another_gyms_sending_domain(self):
        self.client.force_authenticate(self.owner_a)
        self.client.post(
            f"{self.base(self.gym_a)}/sending-domain/", {"domain": "alpha.example"}
        )
        self.client.force_authenticate(self.owner_b)
        listed = self.client.get(f"{self.base(self.gym_b)}/sending-domain/")
        self.assertEqual(listed.data["results"], [])

    def test_a_member_cannot_change_who_the_gym_sends_as(self):
        member = User.objects.create_user(
            username="alpha_member", email="am@example.com",
            password="pass12345", role=Role.MEMBER,
        )
        Membership.objects.create(user=member, tenant=self.gym_a, role=Role.MEMBER)
        self.client.force_authenticate(member)
        resp = self.client.post(
            f"{self.base(self.gym_a)}/sending-domain/", {"domain": "alpha.example"}
        )
        self.assertEqual(resp.status_code, 403)
