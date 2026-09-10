"""Self-serve branding: a gym owner configuring their own identity.

Two things are being checked, and the second is the one that matters.

The first is ordinary: an admin can save a name, colours and a headline font,
and reading it back gives what they saved.

The second is that doing so touches **only their own gym**. Saving a new
identity retires the previous one, and before multi-tenancy that meant "the
previous one on the platform". If that retire ever escapes its organisation
again, every other gym on the platform silently loses its branding and falls
back to the default -- a failure the owner would see and nobody would be able
to explain from their own screen.
"""

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from accounts.models import Role
from tenancy import context
from tenancy.models import Membership, Organisation, Tenant

from .models import Branding, DisplayFont

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


class TwoGymsBranding(APITestCase):
    def setUp(self):
        self.org_a, self.gym_a, self.owner_a = make_gym("alpha", "Alpha Fitness")
        self.org_b, self.gym_b, self.owner_b = make_gym("beta", "Beta Gym")

        with context.scope(self.gym_a):
            self.brand_a = Branding.objects.create(
                name="ALPHA FITNESS", accent="#ff3d5a", accent_2="#ffb020",
                is_active=True,
            )
        with context.scope(self.gym_b):
            self.brand_b = Branding.objects.create(
                name="BETA GYM", accent="#00c2ff", accent_2="#7cf6a0",
                is_active=True,
            )

    def base(self, tenant):
        return f"/api/t/{tenant.slug}"


class PublicIdentityTests(TwoGymsBranding):
    """The login screen has to know whose gym it is before anybody signs in."""

    def test_each_gym_serves_its_own_identity_without_a_login(self):
        self.client.force_authenticate(None)
        a = self.client.get(f"{self.base(self.gym_a)}/branding/")
        b = self.client.get(f"{self.base(self.gym_b)}/branding/")

        self.assertEqual(a.status_code, 200)
        self.assertEqual(a.data["name"], "ALPHA FITNESS")
        self.assertEqual(b.data["name"], "BETA GYM")
        self.assertNotEqual(a.data["accent"], b.data["accent"])

    def test_the_tax_fields_are_not_in_the_public_payload(self):
        """They are for invoices, not for anyone who loads the login page."""
        self.client.force_authenticate(None)
        data = self.client.get(f"{self.base(self.gym_a)}/branding/").data
        self.assertNotIn("gstin", data)
        self.assertNotIn("state", data)

    def test_the_headline_font_is_public_too(self):
        """It is applied before login, so it has to arrive with the palette."""
        self.client.force_authenticate(None)
        data = self.client.get(f"{self.base(self.gym_a)}/branding/").data
        self.assertEqual(data["display_font"], DisplayFont.BEBAS)


class SelfServeTests(TwoGymsBranding):
    def test_an_owner_can_change_their_own_identity(self):
        self.client.force_authenticate(self.owner_a)
        resp = self.client.post(
            f"{self.base(self.gym_a)}/branding/admin/",
            {"name": "ALPHA STRENGTH", "accent": "#22d3ee", "accent_2": "#a855f7",
             "display_font": DisplayFont.ANTON},
        )
        self.assertEqual(resp.status_code, 201)

        self.client.force_authenticate(None)
        public = self.client.get(f"{self.base(self.gym_a)}/branding/").data
        self.assertEqual(public["name"], "ALPHA STRENGTH")
        self.assertEqual(public["accent"], "#22d3ee")
        self.assertEqual(public["display_font"], DisplayFont.ANTON)

    def test_saving_does_not_touch_another_gyms_identity(self):
        """The rule this whole file exists for."""
        self.client.force_authenticate(self.owner_a)
        self.client.post(
            f"{self.base(self.gym_a)}/branding/admin/",
            {"name": "ALPHA STRENGTH", "accent": "#22d3ee", "accent_2": "#a855f7"},
        )

        self.client.force_authenticate(None)
        b = self.client.get(f"{self.base(self.gym_b)}/branding/").data
        self.assertEqual(b["name"], "BETA GYM")
        self.assertEqual(b["accent"], "#00c2ff")

        # And Beta still has exactly one live identity -- Alpha's save must not
        # have retired it as a side effect.
        with context.scope(self.gym_b):
            self.assertEqual(Branding.objects.filter(is_active=True).count(), 1)

    def test_the_previous_identity_is_retired_not_deleted(self):
        self.client.force_authenticate(self.owner_a)
        self.client.post(
            f"{self.base(self.gym_a)}/branding/admin/",
            {"name": "ALPHA STRENGTH", "accent": "#22d3ee", "accent_2": "#a855f7"},
        )
        with context.scope(self.gym_a):
            self.assertEqual(Branding.objects.count(), 2)
            self.assertEqual(Branding.objects.filter(is_active=True).count(), 1)

    def test_an_owner_of_another_gym_cannot_rebrand_yours(self):
        self.client.force_authenticate(self.owner_b)
        resp = self.client.post(
            f"{self.base(self.gym_a)}/branding/admin/",
            {"name": "HOSTILE TAKEOVER", "accent": "#000000", "accent_2": "#ffffff"},
        )
        self.assertEqual(resp.status_code, 403)

        self.client.force_authenticate(None)
        self.assertEqual(
            self.client.get(f"{self.base(self.gym_a)}/branding/").data["name"],
            "ALPHA FITNESS",
        )

    def test_a_member_cannot_rebrand_their_gym(self):
        member = User.objects.create_user(
            username="alpha_member", email="am@example.com",
            password="pass12345", role=Role.MEMBER,
        )
        Membership.objects.create(user=member, tenant=self.gym_a, role=Role.MEMBER)
        self.client.force_authenticate(member)
        resp = self.client.post(
            f"{self.base(self.gym_a)}/branding/admin/",
            {"name": "MINE NOW", "accent": "#000000", "accent_2": "#ffffff"},
        )
        self.assertEqual(resp.status_code, 403)


class ValidationTests(TwoGymsBranding):
    def test_a_colour_that_is_not_a_hex_is_refused(self):
        self.client.force_authenticate(self.owner_a)
        resp = self.client.post(
            f"{self.base(self.gym_a)}/branding/admin/",
            {"name": "ALPHA", "accent": "cornflower", "accent_2": "#ffb020"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("accent", resp.data)

    def test_a_font_that_is_not_on_the_list_is_refused(self):
        """Free text here is a request to a third party we cannot vouch for."""
        self.client.force_authenticate(self.owner_a)
        resp = self.client.post(
            f"{self.base(self.gym_a)}/branding/admin/",
            {"name": "ALPHA", "accent": "#ff3d5a", "accent_2": "#ffb020",
             "display_font": "Comic Sans MS"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("display_font", resp.data)

    def test_the_font_defaults_rather_than_being_required(self):
        self.client.force_authenticate(self.owner_a)
        resp = self.client.post(
            f"{self.base(self.gym_a)}/branding/admin/",
            {"name": "ALPHA", "accent": "#ff3d5a", "accent_2": "#ffb020"},
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["display_font"], DisplayFont.BEBAS)
