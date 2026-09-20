"""The churn report through its API, the way the Reports page calls it.

`reports.tests` exercises `services.churn` directly with real `date` objects,
which is why the 500 went unnoticed: the view handed the service the raw
`?start=` / `?end=` query strings, and churn -- unlike revenue or attendance,
which pass the window straight to the ORM -- compares them with dates in Python.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import MemberProfile, Role
from billing.models import Payment, PaymentMethod, PaymentStatus, Plan
from core.testing import TenantAPIMixin, founding_tenant
from tenancy import context
from tenancy.models import Membership

User = get_user_model()

TODAY = timezone.localdate()


def iso(days_from_today):
    return (TODAY + timedelta(days=days_from_today)).isoformat()


class ChurnReportApiTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = self._person("owner", Role.ADMIN)
        self.plan = Plan.objects.create(name="Monthly", price=Decimal("1000"), duration_days=30)

    def _person(self, username, role=Role.MEMBER):
        user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password="pass12345", role=role
        )
        MemberProfile.objects.get_or_create(user=user)
        self.member_for(user, role)
        return user

    def _paid_until(self, member, days_from_today, plan=None):
        end = TODAY + timedelta(days=days_from_today)
        return Payment.objects.create(
            member=member,
            plan=plan or self.plan,
            amount=Decimal("1000"),
            method=PaymentMethod.CASH,
            status=PaymentStatus.COMPLETED,
            paid_date=end - timedelta(days=30),
            period_start=end - timedelta(days=30),
            period_end=end,
        )

    def churn(self, **params):
        self.client.force_authenticate(self.admin)
        return self.client.get("/api/reports/churn/", params)

    # -- the regression

    def test_the_window_the_reports_page_sends_does_not_crash(self):
        self._paid_until(self._person("lapsed"), -20)
        resp = self.churn(start=iso(-29), end=iso(0))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["churned_count"], 1)
        self.assertEqual(resp.data["start"].isoformat(), iso(-29))
        self.assertEqual(resp.data["end"].isoformat(), iso(0))

    def test_the_default_window_still_works(self):
        resp = self.churn()
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual((resp.data["start"], resp.data["end"]), (TODAY - timedelta(days=29), TODAY))

    # -- what it counts

    def test_nobody_having_paid_is_an_empty_report(self):
        self._person("never_paid")
        resp = self.churn(start=iso(-60), end=iso(0))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            (resp.data["churned_count"], resp.data["retained_count"], resp.data["churn_rate_pct"]),
            (0, 0, 0),
        )
        self.assertEqual(resp.data["members"], [])

    def test_several_members_are_each_counted_once(self):
        self._paid_until(self._person("lapsed_recently"), -20)
        self._paid_until(self._person("lapsed_earlier"), -40)
        renewed = self._person("renewed")
        self._paid_until(renewed, -40)
        self._paid_until(renewed, 10)  # the later payment is the one that counts
        self._person("never_paid")

        resp = self.churn(start=iso(-60), end=iso(0))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual((resp.data["churned_count"], resp.data["retained_count"]), (2, 1))
        self.assertEqual(resp.data["churn_rate_pct"], 66.7)
        # Most recent lapse first, as the page lists them.
        self.assertEqual(
            [row["member"] for row in resp.data["members"]], ["lapsed_recently", "lapsed_earlier"]
        )

    def test_both_ends_of_the_window_are_included(self):
        self._paid_until(self._person("on_start"), -50)
        self._paid_until(self._person("on_end"), -10)
        self._paid_until(self._person("day_before_start"), -51)
        resp = self.churn(start=iso(-50), end=iso(-10))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual({row["member"] for row in resp.data["members"]}, {"on_start", "on_end"})

    def test_a_single_day_window_is_allowed(self):
        self._paid_until(self._person("that_day"), -20)
        resp = self.churn(start=iso(-20), end=iso(-20))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["churned_count"], 1)

    def test_the_grace_period_boundary(self):
        """Lapsed means ended *more than* grace_days ago: on the cutoff day they
        are still within grace and count as retained."""
        self._paid_until(self._person("inside_grace"), -7)
        self._paid_until(self._person("past_grace"), -8)
        resp = self.churn(start=iso(-30), end=iso(0), grace_days=7)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([row["member"] for row in resp.data["members"]], ["past_grace"])
        self.assertEqual(resp.data["retained_count"], 1)

    # -- bad input is a 400 that says which field, never a 500

    def test_a_malformed_date_is_a_400(self):
        for params, field in (
            ({"start": "2026-13-45"}, "start"),
            ({"end": "yesterday"}, "end"),
            ({"start": "14/09/2026"}, "start"),
        ):
            with self.subTest(params=params):
                resp = self.churn(**params)
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertIn(field, resp.data)

    def test_an_end_before_the_start_is_a_400(self):
        resp = self.churn(start=iso(0), end=iso(-1))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("end", resp.data)

    def test_grace_days_must_be_a_sensible_whole_number(self):
        for value in ("abc", "-1", "1.5", "100000000"):
            with self.subTest(grace_days=value):
                self.assertEqual(self.churn(grace_days=value).status_code, 400)

    def test_the_other_reports_refuse_a_malformed_date_too(self):
        """They share the same window parsing, so they share the fix."""
        self.client.force_authenticate(self.admin)
        for path in ("revenue", "attendance", "pt-performance"):
            with self.subTest(report=path):
                resp = self.client.get(f"/api/reports/{path}/", {"start": "not-a-date"})
                self.assertEqual(resp.status_code, 400)
                resp = self.client.get(f"/api/reports/{path}/", {"start": iso(-10), "end": iso(-5)})
                self.assertEqual(resp.status_code, 200)

    # -- who may read it

    def test_only_an_admin_here_can_read_it(self):
        self.assertEqual(self.client.get("/api/reports/churn/").status_code, 401)
        for role in (Role.MEMBER, Role.TRAINER):
            with self.subTest(role=role):
                self.client.force_authenticate(self._person(f"a_{role}", role))
                self.assertEqual(self.client.get("/api/reports/churn/").status_code, 403)

    def test_another_gyms_lapsed_members_do_not_appear(self):
        _, rival = founding_tenant("rivalgym")
        outsider = User.objects.create_user(
            username="rival_member", email="rival_member@example.com", password="pass12345"
        )
        MemberProfile.objects.get_or_create(user=outsider)
        Membership.objects.create(user=outsider, tenant=rival, role=Role.MEMBER)
        with context.scope(rival):
            rival_plan = Plan.objects.create(name="Monthly", price=Decimal("900"), duration_days=30)
            self._paid_until(outsider, -20, plan=rival_plan)

        resp = self.churn(start=iso(-60), end=iso(0))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["churned_count"], 0)
        self.assertNotIn(b"rival_member", resp.content)
