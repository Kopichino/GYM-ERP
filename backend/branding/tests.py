from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.utils import IntegrityError
from django.test import override_settings
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from accounts.models import MemberProfile, Role
from billing.models import PaymentMethod, Plan
from billing.services import record_payment

from . import identity
from .models import Branding

User = get_user_model()


class PublicBrandingTests(TenantAPIMixin, APITestCase):
    """The login screen has to be branded before anyone has signed in."""

    def test_it_is_readable_without_a_session(self):
        Branding.objects.create(name="Iron Temple", accent="#00ff00")
        resp = self.client.get("/api/branding/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["name"], "Iron Temple")
        self.assertEqual(resp.data["accent"], "#00ff00")
        self.assertTrue(resp.data["configured"])

    @override_settings(GYM_NAME="FALLBACK GYM")
    def test_an_unconfigured_install_still_renders_as_something(self):
        resp = self.client.get("/api/branding/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["name"], "FALLBACK GYM")
        self.assertFalse(resp.data["configured"])
        self.assertEqual(resp.data["accent"], "#ff3d5a")

    def test_tax_details_are_not_handed_to_the_browser(self):
        Branding.objects.create(name="Iron Temple", gstin="27AAAAA0000A1Z5", state="Maharashtra")
        resp = self.client.get("/api/branding/")
        self.assertNotIn("gstin", resp.data)
        self.assertNotIn("state", resp.data)


class BrandingAdminTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="brandadmin", email="ba@example.com", password="pass12345", role=Role.ADMIN
        )
        self.member = User.objects.create_user(
            username="brandmember", email="bm@example.com", password="pass12345"
        )
        MemberProfile.objects.get_or_create(user=self.member)

    def test_members_cannot_rebrand_the_gym(self):
        self.client.force_authenticate(self.member)
        resp = self.client.post("/api/branding/admin/", {"name": "Mine Now"})
        self.assertEqual(resp.status_code, 403)

    def test_an_admin_sets_the_identity(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/branding/admin/",
            {"name": "Iron Temple", "accent": "#123456", "accent_2": "#abcdef"},
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Branding.current().name, "Iron Temple")

    def test_a_bad_colour_is_refused(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/branding/admin/", {"name": "Iron Temple", "accent": "not-a-colour"}
        )
        self.assertEqual(resp.status_code, 400)

    def test_creating_a_new_identity_retires_the_old_one(self):
        self.client.force_authenticate(self.admin)
        self.client.post("/api/branding/admin/", {"name": "First"})
        self.client.post("/api/branding/admin/", {"name": "Second"})
        self.assertEqual(Branding.objects.filter(is_active=True).count(), 1)
        self.assertEqual(Branding.current().name, "Second")

    def test_two_active_identities_are_impossible_at_the_database_level(self):
        """One per organisation now -- a second gym gets its own identity."""
        from core.testing import founding_tenant

        org, _ = founding_tenant()
        Branding.objects.create(name="One", is_active=True, organisation=org)
        with self.assertRaises(IntegrityError):
            Branding.objects.create(name="Two", is_active=True, organisation=org)

    def test_but_another_organisation_may_have_its_own(self):
        """The whole point of the swap: multi-tenancy was impossible before."""
        from core.testing import founding_tenant

        org, _ = founding_tenant("gymone")
        other, _ = founding_tenant("gymtwo")
        Branding.unscoped.create(name="One", is_active=True, organisation=org)
        Branding.unscoped.create(name="Two", is_active=True, organisation=other)
        self.assertEqual(Branding.unscoped.filter(is_active=True).count(), 2)


@override_settings(GYM_NAME="ENV GYM", GYM_GSTIN="27ENV0000A1Z5", GYM_STATE="Goa")
class IdentityFallbackTests(TenantAPIMixin, APITestCase):
    """The branding row wins; the environment is the fallback."""

    def test_environment_is_used_when_nothing_is_configured(self):
        self.assertEqual(identity.gym_name(), "ENV GYM")
        self.assertEqual(identity.gstin(), "27ENV0000A1Z5")
        self.assertEqual(identity.state(), "Goa")

    def test_the_row_overrides_the_environment(self):
        Branding.objects.create(
            name="Row Gym", gstin="27ROW0000A1Z5", state="Maharashtra"
        )
        self.assertEqual(identity.gym_name(), "Row Gym")
        self.assertEqual(identity.gstin(), "27ROW0000A1Z5")
        self.assertEqual(identity.state(), "Maharashtra")

    def test_a_blank_field_on_the_row_falls_back_rather_than_going_empty(self):
        Branding.objects.create(name="Row Gym", gstin="", state="")
        self.assertEqual(identity.gym_name(), "Row Gym")
        self.assertEqual(identity.gstin(), "27ENV0000A1Z5")

    def test_the_contact_line_is_empty_rather_than_a_stray_separator(self):
        Branding.objects.create(name="Quiet Gym")
        self.assertEqual(identity.contact_line(), "")

    def test_the_contact_line_joins_what_is_filled_in(self):
        Branding.objects.create(
            name="Loud Gym", phone="+91 90000 00000", email="hi@example.com"
        )
        self.assertIn("+91 90000 00000", identity.contact_line())
        self.assertIn("hi@example.com", identity.contact_line())


class BrandedInvoiceTests(TenantAPIMixin, APITestCase):
    """An invoice carries whatever the gym has called itself."""

    def setUp(self):
        self.member = User.objects.create_user(
            username="invoiced", email="i@example.com", password="pass12345"
        )
        MemberProfile.objects.get_or_create(user=self.member)
        self.plan = Plan.objects.create(
            name="Monthly", price=Decimal("1500"), duration_days=30
        )

    def test_the_invoice_takes_its_gstin_from_the_branding_row(self):
        from invoicing.services import issue_invoice

        Branding.objects.create(
            name="Iron Temple", gstin="27BRAND000A1Z5", state="Maharashtra"
        )
        payment = record_payment(
            member=self.member,
            plan=self.plan,
            amount=self.plan.price,
            method=PaymentMethod.CASH,
        )
        invoice = issue_invoice(payment)
        self.assertEqual(invoice.seller_gstin, "27BRAND000A1Z5")
        self.assertEqual(invoice.place_of_supply, "Maharashtra")

    def test_the_pdf_renders_with_the_gyms_own_name(self):
        from invoicing.pdf import render_invoice
        from invoicing.services import issue_invoice

        Branding.objects.create(
            name="Iron Temple", address="12 Gym Road\nMumbai", phone="+91 90000 00000"
        )
        payment = record_payment(
            member=self.member,
            plan=self.plan,
            amount=self.plan.price,
            method=PaymentMethod.CASH,
        )
        pdf = render_invoice(issue_invoice(payment))
        self.assertTrue(pdf.startswith(b"%PDF"))


class BrandedEmailTests(TenantAPIMixin, APITestCase):
    def test_reminders_are_signed_with_the_configured_name(self):
        from datetime import timedelta

        from django.core import mail
        from django.utils import timezone

        from notifications.services import send_expiry_reminders

        Branding.objects.create(name="Iron Temple")
        member = User.objects.create_user(
            username="mailed", email="m@example.com", password="pass12345", role=Role.MEMBER
        )
        MemberProfile.objects.get_or_create(user=member)
        plan = Plan.objects.create(name="Monthly", price=Decimal("1500"), duration_days=30)
        record_payment(
            member=member,
            plan=plan,
            amount=plan.price,
            method=PaymentMethod.CASH,
            paid_date=timezone.localdate() - timedelta(days=29),
        )

        send_expiry_reminders()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Iron Temple", mail.outbox[0].subject)
        self.assertIn("Iron Temple", mail.outbox[0].body)
