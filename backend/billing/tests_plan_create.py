"""Adding a plan: one intended save is one plan, however often it reaches the server.

A double click on "Add plan" used to send two POSTs. The page now sends one, but
the server does not rely on that: a second identical POST -- a double click that
beats the page, a retry, a second tab -- is refused on the name by the
plan-name constraint, so it can never become a second plan.

There is no idempotency key, on purpose. A plan's name is already its natural
key within a brand, so "the same plan again" is exactly "a plan with a name that
exists", and that is refused. Two *different* plans saved together are two
plans; nothing here suppresses a request just because it arrived close to
another.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from rest_framework.test import APIClient, APITestCase

from accounts.models import Role
from billing.models import Plan
from core.testing import TenantAPIMixin, founding_tenant, requires_row_locks, run_concurrently, winners
from tenancy import context
from tenancy.models import Membership

User = get_user_model()

URL = "/api/billing/plans/"
MONTHLY = {"name": "Monthly", "price": "999.00", "duration_days": 30, "description": "", "is_active": True}
NAME_TAKEN = {"name": ["A plan with this name already exists."]}


class AddPlanTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="owner", email="owner@example.com", password="pass12345", role=Role.ADMIN
        )
        self.member_for(self.admin, Role.ADMIN)
        self.client.force_authenticate(self.admin)

    def test_a_plan_is_created(self):
        resp = self.client.post(URL, MONTHLY, format="json")

        self.assertEqual(resp.status_code, 201, resp.content)
        plan = Plan.objects.get()
        self.assertEqual(resp.data["id"], plan.pk)
        self.assertEqual(
            (plan.name, plan.price, plan.duration_days, plan.is_active),
            ("Monthly", Decimal("999.00"), 30, True),
        )
        self.assertEqual(plan.organisation, self.organisation)

    def test_the_same_plan_sent_twice_is_one_plan_and_a_refusal_on_the_name(self):
        """What a double click did: the second, identical POST lands after the first has saved."""
        first = self.client.post(URL, MONTHLY, format="json")
        second = self.client.post(URL, MONTHLY, format="json")

        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 400, second.content)
        self.assertEqual(second.data, NAME_TAKEN)
        self.assertEqual(Plan.objects.count(), 1)

    def test_an_invalid_plan_is_refused_on_its_field_and_saves_nothing(self):
        without_price = {key: value for key, value in MONTHLY.items() if key != "price"}
        cases = [
            ("blank name", dict(MONTHLY, name=""), "name"),
            ("missing price", without_price, "price"),
            ("price that is not a number", dict(MONTHLY, price="abc"), "price"),
            ("price with too many digits", dict(MONTHLY, price="1234567.00"), "price"),
            ("negative duration", dict(MONTHLY, duration_days=-1), "duration_days"),
        ]
        for label, payload, field in cases:
            with self.subTest(label):
                resp = self.client.post(URL, payload, format="json")
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertIn(field, resp.data)
                self.assertEqual(Plan.objects.count(), 0)

    def test_a_corrected_plan_saves_after_a_validation_refusal(self):
        refused = self.client.post(URL, dict(MONTHLY, price="abc"), format="json")
        self.assertEqual(refused.status_code, 400, refused.content)

        retried = self.client.post(URL, MONTHLY, format="json")

        self.assertEqual(retried.status_code, 201, retried.content)
        self.assertEqual(Plan.objects.count(), 1)

    def test_a_renamed_plan_saves_after_a_name_refusal(self):
        self.client.post(URL, MONTHLY, format="json")
        self.assertEqual(self.client.post(URL, MONTHLY, format="json").status_code, 400)

        retried = self.client.post(URL, dict(MONTHLY, name="Monthly Plus"), format="json")

        self.assertEqual(retried.status_code, 201, retried.content)
        self.assertEqual(sorted(Plan.objects.values_list("name", flat=True)), ["Monthly", "Monthly Plus"])


@requires_row_locks
class SimultaneousAddPlanTests(TransactionTestCase):
    """POSTs landing at the same instant -- a double click that beat the page's guard."""

    def setUp(self):
        super().setUp()
        _, self.tenant = founding_tenant("doubleclickgym")
        self._scope_token = context.set(self.tenant)
        self.admin = User.objects.create_user(
            username="owner", email="owner@example.com", password="pass12345", role=Role.ADMIN
        )
        Membership.objects.create(user=self.admin, tenant=self.tenant, role=Role.ADMIN)

    def tearDown(self):
        context.reset(self._scope_token)
        super().tearDown()

    def post(self, payload):
        client = APIClient()
        client.force_authenticate(self.admin)
        return client.post(f"/api/t/{self.tenant.slug}/billing/plans/", payload, format="json")

    def test_two_identical_posts_at_once_make_one_plan(self):
        results = run_concurrently(lambda _: self.post(MONTHLY), count=2)

        responses = winners(results)
        # Both calls came back as responses: an exception here is a 500 the page would see.
        self.assertEqual(len(responses), 2, results)
        self.assertEqual(sorted(r.status_code for r in responses), [201, 400])
        self.assertEqual(next(r for r in responses if r.status_code == 400).data, NAME_TAKEN)
        self.assertEqual(Plan.objects.count(), 1)

    def test_two_different_plans_at_once_are_both_saved(self):
        """Nothing suppresses a request just for arriving alongside another."""
        payloads = [MONTHLY, dict(MONTHLY, name="Quarterly", duration_days=90)]

        results = run_concurrently(lambda i: self.post(payloads[i]), count=2)

        responses = winners(results)
        self.assertEqual(len(responses), 2, results)
        self.assertEqual([r.status_code for r in responses], [201, 201])
        self.assertEqual(sorted(Plan.objects.values_list("name", flat=True)), ["Monthly", "Quarterly"])
