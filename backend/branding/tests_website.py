"""What the public website reads from Branding.

The website's footer and colours come from the same public endpoint the login
screen uses, so an admin's edit on the Branding page reaches the website with
no second copy to keep in step.
"""

from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from .models import Branding


class WebsiteDetailsTests(TenantAPIMixin, APITestCase):
    def test_the_address_hours_and_colour_reach_the_public_endpoint(self):
        Branding.objects.create(
            name="Iron Temple",
            address="12 Hill Road\nBandra West, Mumbai",
            opening_hours="Monday to Friday: 6:00 - 22:00\nSunday: closed",
            accent="#22aaee",
            phone="+91 98200 10000",
        )
        data = self.client.get("/api/branding/").data
        self.assertEqual(data["address"], "12 Hill Road\nBandra West, Mumbai")
        self.assertEqual(data["opening_hours"], "Monday to Friday: 6:00 - 22:00\nSunday: closed")
        self.assertEqual(data["accent"], "#22aaee")
        self.assertEqual(data["phone"], "+91 98200 10000")

    def test_an_edit_is_what_the_website_reads_next(self):
        branding = Branding.objects.create(name="Iron Temple", address="Old Street")
        branding.address = "New Street"
        branding.accent = "#ffb020"
        branding.save()
        data = self.client.get("/api/branding/").data
        self.assertEqual(data["address"], "New Street")
        self.assertEqual(data["accent"], "#ffb020")

    def test_an_unconfigured_gym_shows_no_hours_rather_than_invented_ones(self):
        data = self.client.get("/api/branding/").data
        self.assertEqual(data["opening_hours"], "")

    def test_an_admin_can_set_the_opening_hours(self):
        from accounts.models import Role, User

        admin = User.objects.create_user(
            username="brand_admin", email="brand_admin@example.com", password="pass12345", role=Role.ADMIN
        )
        self.client.force_authenticate(admin)
        resp = self.client.post(
            "/api/branding/admin/",
            {"name": "Iron Temple", "opening_hours": "Every day: 6:00 - 22:00"},
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/branding/").data["opening_hours"], "Every day: 6:00 - 22:00")
