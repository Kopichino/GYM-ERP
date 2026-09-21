from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin, enrol

from accounts.models import MemberProfile, Role
from billing.models import Plan
from billing.services import record_payment
from expenses.models import Expense, ExpenseCategory

from .builder import ReportError, run
from core.permissions import IsAdmin

from .models import SavedReport
from .services import churn, pt_performance, revenue

User = get_user_model()


def make_user(username, role=Role.MEMBER):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    MemberProfile.objects.get_or_create(user=user)
    enrol(user)
    return user


class RevenueReportTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        # Taken per test, not once at import. The runner imports every module
        # at the start of a long run, so a run that crossed midnight handed these
        # tests yesterday while payments were stamped with the real today.
        self.today = timezone.localdate()
        self.member = make_user("member")
        self.plan = Plan.objects.create(name="Monthly", price=Decimal("1000"), duration_days=30)
        record_payment(member=self.member, plan=self.plan, amount=Decimal("800"), method="cash",
                       discount_amount=Decimal("200"))
        record_payment(member=make_user("second"), plan=self.plan, amount=Decimal("1000"), method="upi")

        category = ExpenseCategory.objects.create(name="Rent")
        Expense.objects.create(category=category, amount=Decimal("500"), spent_on=self.today)

    def test_revenue_nets_expenses_off_collections(self):
        data = revenue()
        self.assertEqual(data["collected"], Decimal("1800"))
        self.assertEqual(data["expenses"], Decimal("500"))
        self.assertEqual(data["net"], Decimal("1300"))

    def test_gross_adds_back_what_was_discounted(self):
        data = revenue()
        self.assertEqual(data["discounts_given"], Decimal("200"))
        self.assertEqual(data["gross"], Decimal("2000"))

    def test_breakdowns_are_returned(self):
        data = revenue()
        self.assertEqual(data["by_plan"][0]["plan"], "Monthly")
        self.assertEqual({r["method"] for r in data["by_method"]}, {"cash", "upi"})

    def test_a_window_excludes_payments_outside_it(self):
        data = revenue(start=self.today + timedelta(days=1), end=self.today + timedelta(days=5))
        self.assertEqual(data["collected"], Decimal("0"))


class ChurnReportTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        # Per test, for the reason given in RevenueReportTests.setUp.
        self.today = timezone.localdate()
        self.plan = Plan.objects.create(name="Monthly", price=Decimal("1000"), duration_days=30)

    def test_a_lapsed_member_counts_as_churned(self):
        member = make_user("lapsed")
        record_payment(
            member=member, plan=self.plan, amount=Decimal("1000"), method="cash",
            paid_date=self.today - timedelta(days=90),
        )
        data = churn(start=self.today - timedelta(days=90), end=self.today)
        self.assertEqual(data["churned_count"], 1)
        self.assertEqual(data["members"][0]["member"], "lapsed")

    def test_a_current_member_is_retained_not_churned(self):
        member = make_user("current")
        record_payment(member=member, plan=self.plan, amount=Decimal("1000"), method="cash")
        data = churn(start=self.today - timedelta(days=90), end=self.today + timedelta(days=90))
        self.assertEqual(data["churned_count"], 0)
        self.assertEqual(data["retained_count"], 1)

    def test_the_definition_is_stated_rather_than_implied(self):
        """The gym never records intent to leave, so the report has to say what
        it means by churn."""
        self.assertIn("no renewal since", churn()["definition"])

    def test_a_member_who_never_paid_is_not_counted_either_way(self):
        make_user("never_paid")
        data = churn()
        self.assertEqual(data["churned_count"], 0)
        self.assertEqual(data["retained_count"], 0)


class PtPerformanceTests(TenantAPIMixin, APITestCase):
    def test_revenue_is_attributed_to_the_assigned_trainer(self):
        trainer = make_user("trainer", Role.TRAINER)
        member = make_user("member")
        member.profile.trainer = trainer
        member.profile.save()
        plan = Plan.objects.create(name="Monthly", price=Decimal("1000"), duration_days=30)
        record_payment(member=member, plan=plan, amount=Decimal("1000"), method="cash")

        row = pt_performance()["trainers"][0]
        self.assertEqual(row["trainer"], "trainer")
        self.assertEqual(row["member_count"], 1)
        self.assertEqual(row["revenue"], Decimal("1000"))


class CustomBuilderTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.member = make_user("member")
        self.plan = Plan.objects.create(name="Monthly", price=Decimal("1000"), duration_days=30)
        record_payment(member=self.member, plan=self.plan, amount=Decimal("1000"), method="cash")

    def test_a_plain_listing_returns_the_selected_fields(self):
        result = run({"source": "payments", "fields": ["member", "plan", "amount"]})
        self.assertEqual(result["columns"], ["member", "plan", "amount"])
        self.assertEqual(result["rows"][0]["member"], "member")

    def test_grouping_with_an_aggregate(self):
        result = run({
            "source": "payments",
            "group_by": "plan",
            "aggregates": [{"fn": "sum", "field": "amount", "alias": "total"}],
        })
        self.assertEqual(result["rows"][0]["plan"], "Monthly")
        # Aggregates are returned unformatted -- the builder sums arbitrary
        # numeric fields, so money formatting is the caller's job.
        self.assertEqual(Decimal(result["rows"][0]["total"]), Decimal("1000"))

    def test_filters_are_applied(self):
        result = run({
            "source": "payments",
            "fields": ["member"],
            "filters": [{"field": "method", "op": "eq", "value": "upi"}],
        })
        self.assertEqual(result["row_count"], 0)

    def test_an_unknown_source_is_refused(self):
        with self.assertRaises(ReportError):
            run({"source": "auth_user"})

    def test_a_field_outside_the_whitelist_is_refused(self):
        """The guard that stops a report definition reading arbitrary columns."""
        with self.assertRaises(ReportError):
            run({"source": "payments", "fields": ["member__password"]})

    def test_a_filter_on_a_non_whitelisted_field_is_refused(self):
        with self.assertRaises(ReportError):
            run({
                "source": "payments",
                "filters": [{"field": "member__is_superuser", "op": "eq", "value": True}],
            })

    def test_an_unknown_operator_is_refused(self):
        with self.assertRaises(ReportError):
            run({
                "source": "payments",
                "filters": [{"field": "amount", "op": "regex", "value": ".*"}],
            })


class ReportAccessTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = make_user("admin", Role.ADMIN)
        self.trainer = make_user("trainer", Role.TRAINER)
        self.member = make_user("member")

    def test_reports_are_admin_only(self):
        for user in (self.member, self.trainer):
            self.client.force_authenticate(user)
            for url in (
                "/api/reports/revenue/",
                "/api/reports/attendance/",
                "/api/reports/churn/",
                "/api/reports/pt-performance/",
                "/api/reports/schema/",
            ):
                self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_admin_can_read_every_report(self):
        self.client.force_authenticate(self.admin)
        for url in (
            "/api/reports/revenue/",
            "/api/reports/attendance/",
            "/api/reports/churn/",
            "/api/reports/pt-performance/",
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_a_saved_report_reruns_against_current_data(self):
        self.client.force_authenticate(self.admin)
        created = self.client.post(
            "/api/reports/saved/",
            {
                "name": "Cash by plan",
                "definition": {
                    "source": "payments",
                    "group_by": "plan",
                    "aggregates": [{"fn": "sum", "field": "amount", "alias": "total"}],
                },
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        resp = self.client.get(f"/api/reports/saved/{created.data['id']}/run/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("columns", resp.data)

    def test_the_builder_schema_only_advertises_whitelisted_fields(self):
        self.client.force_authenticate(self.admin)
        sources = self.client.get("/api/reports/schema/").data
        payments = next(s for s in sources if s["source"] == "payments")
        self.assertIn("amount", payments["fields"])
        self.assertNotIn("member__password", payments["fields"])


class EveryReportRouteIsAdminOnlyTests(TenantAPIMixin, APITestCase):
    """The write and export routes, which the GET-only check above misses.

    Reports read the whole business -- every payment, every member's
    attendance, the trainer commission table. A gap anywhere in this app hands
    a member or a trainer the owner's dashboard, so the check is exhaustive
    over the URLconf rather than over a list someone remembered to update.
    """

    def setUp(self):
        self.admin = make_user("route_admin", Role.ADMIN)
        self.trainer = make_user("route_trainer", Role.TRAINER)
        self.member = make_user("route_member")
        self.saved = SavedReport.objects.create(
            name="Monthly revenue",
            definition={"source": "payments", "columns": ["amount"]},
            owner=self.admin,
        )

    def _reads(self):
        return [
            "/api/reports/kpis/",
            "/api/reports/occupancy/",
            "/api/reports/revenue/",
            "/api/reports/attendance/",
            "/api/reports/churn/",
            "/api/reports/pt-performance/",
            "/api/reports/schema/",
            "/api/reports/saved/",
            f"/api/reports/saved/{self.saved.id}/",
            f"/api/reports/saved/{self.saved.id}/run/",
        ]

    def _writes(self):
        definition = {"source": "payments", "columns": ["amount"]}
        return [
            ("post", "/api/reports/custom/", definition),
            ("post", "/api/reports/export/", definition),
            ("post", "/api/reports/saved/", {"name": "Mine", "definition": definition}),
            ("patch", f"/api/reports/saved/{self.saved.id}/", {"name": "Renamed"}),
            ("delete", f"/api/reports/saved/{self.saved.id}/", None),
        ]

    def test_a_member_is_refused_every_read(self):
        self.client.force_authenticate(self.member)
        for url in self._reads():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_a_trainer_is_refused_every_read(self):
        # The gym's books are not a trainer's to read.
        self.client.force_authenticate(self.trainer)
        for url in self._reads():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_an_anonymous_caller_is_refused_every_read(self):
        for url in self._reads():
            with self.subTest(url=url):
                self.assertIn(self.client.get(url).status_code, (401, 403))

    def test_non_admins_are_refused_every_write(self):
        for user in (self.member, self.trainer):
            self.client.force_authenticate(user)
            for method, url, payload in self._writes():
                with self.subTest(user=user.username, url=url, method=method):
                    call = getattr(self.client, method)
                    resp = call(url, payload, format="json") if payload else call(url)
                    self.assertEqual(resp.status_code, 403)

    def test_a_refused_write_leaves_the_saved_report_alone(self):
        self.client.force_authenticate(self.trainer)
        for method, url, payload in self._writes():
            call = getattr(self.client, method)
            call(url, payload, format="json") if payload else call(url)

        self.saved.refresh_from_db()
        self.assertEqual(self.saved.name, "Monthly revenue")
        self.assertEqual(SavedReport.objects.count(), 1)

    def test_the_export_is_admin_only_and_returns_a_workbook(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(
            self.client.post(
                "/api/reports/export/",
                {"source": "payments", "columns": ["amount"]},
                format="json",
            ).status_code,
            403,
        )

        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/reports/export/",
            {"source": "payments", "columns": ["amount"]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp["Content-Type"])

    def test_the_saved_owner_is_the_caller_not_the_payload(self):
        # `owner` is set from the token, so an admin cannot file a saved report
        # under another account.
        self.client.force_authenticate(self.admin)
        other = make_user("route_admin2", Role.ADMIN)
        resp = self.client.post(
            "/api/reports/saved/",
            {
                "name": "Mine",
                "definition": {"source": "payments", "columns": ["amount"]},
                "owner": other.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(SavedReport.objects.get(pk=resp.data["id"]).owner, self.admin)

    def test_every_view_in_the_app_carries_the_admin_guard(self):
        """Guards against a new report endpoint shipping unguarded.

        Checked against the view classes rather than the URL patterns: a route
        added without `IsAdmin` is the failure that matters, and it fails here
        by name whether or not anyone remembered to list its URL above.
        """
        from rest_framework.views import APIView
        from rest_framework.viewsets import ViewSetMixin

        from reports import views as report_views

        unguarded = []
        for name in dir(report_views):
            view = getattr(report_views, name)
            if not isinstance(view, type) or name.startswith("_"):
                continue
            if not issubclass(view, (APIView, ViewSetMixin)):
                continue
            if view.__module__ != report_views.__name__:
                continue
            if IsAdmin not in getattr(view, "permission_classes", []):
                unguarded.append(name)

        self.assertEqual(unguarded, [], f"report views without IsAdmin: {unguarded}")
