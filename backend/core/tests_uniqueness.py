"""Duplicate names and codes come back as a 400 on the field, never a 500.

The database constraints stay -- they are what guarantees uniqueness. What
changes is that a predictable duplicate is caught as validation, naming the
field, and that one which races past validation (two admins saving at the same
moment) is turned into the same 400 instead of escaping as an IntegrityError.

Uniqueness follows the constraints as they are: per brand (organisation), so
two branches of one brand share names and codes while unrelated gyms do not.
Offer codes are the one case-insensitive rule, because they are stored
upper-cased and matched at the till ignoring case.
"""

from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from accounts.models import Role
from billing.models import Discount, Plan
from core.testing import TenantAPIMixin, founding_tenant
from expenses.models import ExpenseCategory
from gamification.models import Badge
from tenancy import context
from tenancy.models import Tenant
from workouts.models import Exercise

User = get_user_model()

#: What a database error looks like when it reaches the client.
LEAKS = (b"IntegrityError", b"UNIQUE constraint", b"duplicate key", b"Traceback", b"_per_organisation")

CASES = [
    # label, path, payload, conflicting field, model
    ("plan name", "/api/billing/plans/", {"name": "Monthly", "price": "999.00", "duration_days": 30}, "name", Plan),
    ("offer code", "/api/billing/discounts/", {"code": "SAVE10", "discount_type": "percent", "value": "10"}, "code", Discount),
    ("expense category", "/api/expenses/categories/", {"name": "Rent"}, "name", ExpenseCategory),
    (
        "badge code",
        "/api/gamification/badges/",
        {"code": "ten-visits", "name": "Ten visits", "criterion": "visits", "threshold": 10},
        "code",
        Badge,
    ),
]


class DuplicateValueTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="owner", email="owner@example.com", password="pass12345", role=Role.ADMIN
        )
        self.member_for(self.admin, Role.ADMIN)
        self.client.force_authenticate(self.admin)

    def assert_refused_on(self, resp, field):
        self.assertEqual(resp.status_code, 400, resp.content[:300])
        self.assertIn(field, resp.data)
        self.assertIn("already", str(resp.data[field]).lower())
        for marker in LEAKS:
            self.assertNotIn(marker, resp.content)

    # -- a second record with the same value

    def test_a_second_record_with_the_same_value_is_refused_on_that_field(self):
        for label, path, payload, field, model in CASES:
            with self.subTest(label):
                self.assertEqual(self.client.post(path, payload, format="json").status_code, 201)
                self.assert_refused_on(self.client.post(path, payload, format="json"), field)
                self.assertEqual(model.objects.count(), 1)

    def test_editing_a_record_into_an_existing_value_is_refused_on_that_field(self):
        for label, path, payload, field, model in CASES:
            with self.subTest(label):
                first = self.client.post(path, payload, format="json").data
                other = dict(payload, **{field: f"{payload[field]}-2" if field != "code" or model is Badge else "OTHER10"})
                if model is Badge:
                    other["threshold"] = 20
                second = self.client.post(path, other, format="json")
                self.assertEqual(second.status_code, 201, second.content)
                resp = self.client.patch(f"{path}{second.data['id']}/", {field: first[field]}, format="json")
                self.assert_refused_on(resp, field)
                self.assertNotEqual(getattr(model.objects.get(pk=second.data["id"]), field), first[field])

    def test_saving_a_record_under_its_own_value_is_not_a_conflict(self):
        for label, path, payload, field, model in CASES:
            with self.subTest(label):
                created = self.client.post(path, payload, format="json").data
                resp = self.client.patch(f"{path}{created['id']}/", {field: created[field]}, format="json")
                self.assertEqual(resp.status_code, 200, resp.content)

    # -- the rules that are not plain equality

    def test_offer_codes_that_differ_only_in_case_are_the_same_code(self):
        self.client.post("/api/billing/discounts/", CASES[1][2], format="json")
        resp = self.client.post(
            "/api/billing/discounts/", dict(CASES[1][2], code=" save10 "), format="json"
        )
        self.assert_refused_on(resp, "code")

    def test_plan_names_are_compared_exactly_as_the_constraint_does(self):
        """Pins today's rule rather than inventing one: the constraint is exact."""
        self.client.post("/api/billing/plans/", CASES[0][2], format="json")
        resp = self.client.post("/api/billing/plans/", dict(CASES[0][2], name="monthly"), format="json")
        self.assertEqual(resp.status_code, 201)

    def test_badges_cannot_repeat_a_criterion_and_threshold(self):
        path, payload = CASES[3][1], CASES[3][2]
        self.client.post(path, payload, format="json")
        resp = self.client.post(path, dict(payload, code="another-ten"), format="json")
        self.assert_refused_on(resp, "threshold")

    def test_lift_badges_cannot_repeat_an_exercise_and_weight(self):
        squat = Exercise.objects.create(name="Back Squat")
        payload = {"code": "squat-100", "name": "Squat 100", "criterion": "lift", "exercise": squat.pk, "threshold": 100}
        self.assertEqual(self.client.post("/api/gamification/badges/", payload, format="json").status_code, 201)
        resp = self.client.post("/api/gamification/badges/", dict(payload, code="squat-100-b"), format="json")
        self.assert_refused_on(resp, "threshold")

    # -- a duplicate that slips past validation

    def test_a_duplicate_that_races_past_validation_is_still_a_400_on_the_field(self):
        """Two admins saving at once both pass validation; the constraint stops the
        second, and that must still reach the client as the same 400."""
        from core.uniqueness import UniqueInScope

        for label, path, payload, field, model in CASES:
            with self.subTest(label):
                self.client.post(path, payload, format="json")
                with mock.patch.object(UniqueInScope, "__call__", lambda self, attrs, serializer: None):
                    resp = self.client.post(path, payload, format="json")
                self.assert_refused_on(resp, field)
                self.assertEqual(model.objects.count(), 1)

    # -- where the rule applies

    def test_an_unrelated_gym_may_use_the_same_names_and_codes(self):
        _, elsewhere = founding_tenant("unrelated")
        with context.scope(elsewhere):
            Plan.objects.create(name="Monthly", price=Decimal("500"), duration_days=30)
            Discount.objects.create(code="SAVE10", discount_type="percent", value=Decimal("10"))
            ExpenseCategory.objects.create(name="Rent")
        for label, path, payload, field, model in CASES[:3]:
            with self.subTest(label):
                self.assertEqual(self.client.post(path, payload, format="json").status_code, 201)

    def test_another_branch_of_the_same_brand_shares_the_names(self):
        branch = Tenant.objects.create(
            organisation=self.organisation, name="North", slug="testgym-north"
        )
        with context.scope(branch):
            Plan.objects.create(name="Monthly", price=Decimal("500"), duration_days=30)
        self.assert_refused_on(self.client.post(CASES[0][1], CASES[0][2], format="json"), "name")

    def test_only_an_admin_can_create_them(self):
        member = User.objects.create_user(username="m", email="m@example.com", password="pass12345")
        self.member_for(member, Role.MEMBER)
        self.client.force_authenticate(member)
        for label, path, payload, field, model in CASES:
            with self.subTest(label):
                self.assertEqual(self.client.post(path, payload, format="json").status_code, 403)
