"""The price list the public website reads.

The point of the endpoint is that the website and the front desk cannot
disagree: both read the same Plan rows. So the tests are about that -- a price
edited in the portal shows up here -- and about what a signed-out stranger may
and may not see.
"""

from decimal import Decimal

from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin, founding_tenant

from .models import Plan

URL = "/api/billing/public/plans/"


class PublicPlanListTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.monthly = Plan.objects.create(
            name="Monthly", price=Decimal("3200"), duration_days=30, description="Full floor\nAll classes"
        )
        self.annual = Plan.objects.create(name="Annual", price=Decimal("26900"), duration_days=365)
        Plan.objects.create(name="Retired", price=Decimal("999"), duration_days=30, is_active=False)

    def test_it_is_readable_without_a_session(self):
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, 200)
        # A plain list, shortest plan first.
        self.assertEqual([plan["name"] for plan in resp.data], ["Monthly", "Annual"])

    def test_a_price_changed_in_the_portal_is_the_price_on_the_website(self):
        self.monthly.price = Decimal("3500")
        self.monthly.save()
        resp = self.client.get(URL)
        self.assertEqual(resp.data[0]["price"], "3500.00")

    def test_a_retired_plan_is_left_off(self):
        names = [plan["name"] for plan in self.client.get(URL).data]
        self.assertNotIn("Retired", names)

    def test_only_what_a_price_list_needs_is_exposed(self):
        plan = self.client.get(URL).data[0]
        self.assertEqual(set(plan), {"id", "name", "price", "duration_days", "description"})
        self.assertEqual(plan["description"], "Full floor\nAll classes")

    def test_a_stale_token_in_the_browser_does_not_break_it(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
        self.assertEqual(self.client.get(URL).status_code, 200)

    def test_another_gyms_prices_are_not_listed(self):
        elsewhere, _ = founding_tenant("othergym")
        Plan.unscoped.create(
            organisation=elsewhere, name="Elsewhere Monthly", price=Decimal("100"), duration_days=30
        )
        names = [plan["name"] for plan in self.client.get(URL).data]
        self.assertNotIn("Elsewhere Monthly", names)
