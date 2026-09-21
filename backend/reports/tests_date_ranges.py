"""A report's To date before its From date is refused, never quietly run.

Bug 2 gave the four tabbed reports one parsed, validated window. Three other
places still took dates as they came: the dashboard's KPIs and occupancy heatmap
(`date.fromisoformat`, so a malformed date was a 500 and a backwards range ran),
and the custom builder (raw strings handed to the ORM -- the same 500, and a
backwards window quietly matching nothing). Every report now reads its window
the same way, and a saved report cannot store one that could never run.

Leaving either end out still means "use the default". The one case a default
cannot make sense of -- a From date after today with no To date, when To
defaults to today -- is refused rather than answered with an empty report.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import MemberProfile, Role
from core.testing import TenantAPIMixin

from .models import SavedReport

User = get_user_model()

TODAY = timezone.localdate()

#: Every report read with a date window in the query string.
WINDOWED_REPORTS = ["revenue", "attendance", "churn", "pt-performance", "kpis", "occupancy"]
END_BEFORE_START = "The end date is before the start date."


def iso(days_from_today):
    return (TODAY + timedelta(days=days_from_today)).isoformat()


class ReportDateRangeTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="owner", email="owner@example.com", password="pass12345", role=Role.ADMIN
        )
        MemberProfile.objects.get_or_create(user=self.admin)
        self.member_for(self.admin, Role.ADMIN)
        self.client.force_authenticate(self.admin)

    def read(self, report, **params):
        return self.client.get(f"/api/reports/{report}/", params)

    def build(self, path="/api/reports/custom/", **window):
        return self.client.post(path, {"source": "payments", **window}, format="json")

    # -- valid ranges

    def test_a_same_day_range_runs_everywhere(self):
        for report in WINDOWED_REPORTS:
            with self.subTest(report=report):
                self.assertEqual(self.read(report, start=iso(-3), end=iso(-3)).status_code, 200)
        for path in ("/api/reports/custom/", "/api/reports/export/"):
            with self.subTest(path=path):
                self.assertEqual(self.build(path, start=iso(-3), end=iso(-3)).status_code, 200)

    def test_a_multi_day_range_runs_everywhere(self):
        for report in WINDOWED_REPORTS:
            with self.subTest(report=report):
                self.assertEqual(self.read(report, start=iso(-30), end=iso(0)).status_code, 200)
        for path in ("/api/reports/custom/", "/api/reports/export/"):
            with self.subTest(path=path):
                self.assertEqual(self.build(path, start=iso(-30), end=iso(0)).status_code, 200)

    # -- backwards ranges

    def test_every_windowed_report_refuses_an_end_before_the_start(self):
        for report in WINDOWED_REPORTS:
            with self.subTest(report=report):
                resp = self.read(report, start=iso(0), end=iso(-1))
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertEqual([str(m) for m in resp.data["end"]], [END_BEFORE_START])

    def test_the_custom_builder_refuses_an_end_before_the_start(self):
        for path in ("/api/reports/custom/", "/api/reports/export/"):
            with self.subTest(path=path):
                resp = self.build(path, start=iso(0), end=iso(-1))
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertEqual(resp.data["detail"], END_BEFORE_START)

    def test_a_report_with_a_backwards_window_cannot_be_saved(self):
        resp = self.client.post(
            "/api/reports/saved/",
            {"name": "Backwards", "definition": {"source": "payments", "start": iso(0), "end": iso(-1)}},
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("definition", resp.data)
        self.assertFalse(SavedReport.objects.exists())

    def test_a_backwards_window_saved_before_this_rule_is_refused_when_run(self):
        saved = SavedReport.objects.create(
            name="Old", definition={"source": "payments", "start": iso(0), "end": iso(-1)}, owner=self.admin
        )
        resp = self.client.get(f"/api/reports/saved/{saved.pk}/run/")
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(resp.data["detail"], END_BEFORE_START)

    # -- one end left out

    def test_leaving_out_the_from_date_uses_the_default(self):
        for report in WINDOWED_REPORTS:
            with self.subTest(report=report):
                self.assertEqual(self.read(report, end=iso(-2)).status_code, 200)
        self.assertEqual(self.build(end=iso(-2)).status_code, 200)

    def test_leaving_out_the_to_date_uses_the_default(self):
        for report in WINDOWED_REPORTS:
            with self.subTest(report=report):
                self.assertEqual(self.read(report, start=iso(-10)).status_code, 200)
        self.assertEqual(self.build(start=iso(-10)).status_code, 200)

    def test_a_from_date_after_today_with_no_to_date_is_refused(self):
        """To defaults to today, so this would be a backwards window in disguise."""
        for report in WINDOWED_REPORTS:
            with self.subTest(report=report):
                resp = self.read(report, start=iso(5))
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertIn("start", resp.data)

    # -- malformed dates

    def test_a_malformed_date_is_a_400_not_a_500(self):
        for report in WINDOWED_REPORTS:
            with self.subTest(report=report):
                resp = self.read(report, start="2026-13-45")
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertIn("start", resp.data)
                resp = self.read(report, end="not-a-date")
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertIn("end", resp.data)
        for path in ("/api/reports/custom/", "/api/reports/export/"):
            with self.subTest(path=path):
                resp = self.build(path, start="14/09/2026")
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertIn("start", resp.data["detail"])

    # -- who

    def test_only_an_admin_reads_them(self):
        member = User.objects.create_user(username="member", email="member@example.com", password="pass12345")
        self.member_for(member, Role.MEMBER)
        self.client.force_authenticate(member)
        for report in ("kpis", "occupancy"):
            with self.subTest(report=report):
                self.assertEqual(self.read(report, start=iso(0), end=iso(-1)).status_code, 403)
