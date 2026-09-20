"""Two admins adding the same value at the same instant.

`tests_uniqueness` simulates the race by skipping validation. These run it for
real: every save passes validation because no row exists yet, the unique index
lets one through, and the others must come back as a field error rather than an
IntegrityError. Postgres only -- SQLite serialises writers, so the race cannot
happen there (see core.testing).

Three layers, because each can fail on its own:

* the database constraint, with no serializer in the way;
* the serializer, which must turn the constraint's refusal into a field error;
* the API, which must deliver that as a 400 on the field and never a 500.
"""

import threading
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TransactionTestCase
from rest_framework import serializers
from rest_framework.test import APIClient

from accounts.models import Role
from billing.models import Plan
from billing.serializers import PlanSerializer
from tenancy import context
from tenancy.models import Membership

from . import tests_uniqueness as sequential
from .testing import founding_tenant, losers, requires_row_locks, run_concurrently, winners
from .uniqueness import SaveConflictsAsValidationErrors, UniqueInScope

User = get_user_model()

MONTHLY = {"name": "Monthly", "price": "999.00", "duration_days": 30}


def all_past_validation(count=2):
    """Hold each request after its uniqueness check until `count` have passed it.

    Without this the race is left to timing: a request that validates after the
    other has committed is refused by validation, and the constraint path this
    module exists to prove never runs. With it, no request writes until all of
    them have been cleared -- so every duplicate must be stopped by the database.

    Holds once per thread, not once per validator, so a serializer carrying more
    than one check does not deadlock the gate.
    """
    gate = threading.Barrier(count, timeout=15)
    held = threading.local()
    original = UniqueInScope.__call__

    def gated(validator, attrs, serializer):
        original(validator, attrs, serializer)
        if not getattr(held, "done", False):
            held.done = True
            gate.wait()

    return mock.patch.object(UniqueInScope, "__call__", gated)


def counting_conversions():
    """Patch the constraint-to-field-error conversion to record each use."""
    calls = []
    original = SaveConflictsAsValidationErrors._raise_conflict

    def counted(serializer, data):
        calls.append(type(serializer).__name__)
        return original(serializer, data)

    return calls, mock.patch.object(SaveConflictsAsValidationErrors, "_raise_conflict", counted)


@requires_row_locks
class SimultaneousDuplicateTests(TransactionTestCase):
    def setUp(self):
        super().setUp()
        _, self.tenant = founding_tenant("duplicategym")
        self._scope_token = context.set(self.tenant)

    def tearDown(self):
        context.reset(self._scope_token)
        super().tearDown()

    def test_the_constraint_alone_refuses_the_second_row(self):
        """No serializer and no validation: only the unique index stands in the way."""

        def insert(_):
            return Plan.objects.create(**MONTHLY).pk

        results = run_concurrently(insert, count=2)

        self.assertEqual(len(winners(results)), 1, results)
        [refusal] = losers(results)
        self.assertIsInstance(refusal, IntegrityError)
        self.assertEqual(Plan.objects.filter(name="Monthly").count(), 1)

    def test_two_simultaneous_adds_leave_one_plan_and_one_field_error(self):
        def add(_):
            form = PlanSerializer(data=MONTHLY)
            form.is_valid(raise_exception=True)
            return form.save().pk

        conversions, converting = counting_conversions()
        with all_past_validation(), converting:
            results = run_concurrently(add, count=2)

        self.assertEqual(len(winners(results)), 1, results)
        [refusal] = losers(results)
        self.assertIsInstance(refusal, serializers.ValidationError)
        self.assertIn("name", refusal.detail)
        # Both passed validation, so the refusal came from the constraint.
        self.assertEqual(conversions, ["PlanSerializer"])
        self.assertEqual(Plan.objects.filter(name="Monthly").count(), 1)


@requires_row_locks
class SimultaneousDuplicateRequestTests(TransactionTestCase):
    """The same race through the real API: routing, tenant, view, serializer, savepoint."""

    def setUp(self):
        super().setUp()
        _, self.tenant = founding_tenant("racegym")
        self._scope_token = context.set(self.tenant)
        self.admin = User.objects.create_user(
            username="owner", email="owner@example.com", password="pass12345", role=Role.ADMIN
        )
        Membership.objects.create(user=self.admin, tenant=self.tenant, role=Role.ADMIN)

    def tearDown(self):
        context.reset(self._scope_token)
        super().tearDown()

    def send(self, method, path, payload):
        """One admin's request from its own client, as a second browser would send it."""
        client = APIClient()
        client.force_authenticate(self.admin)
        url = f"/api/t/{self.tenant.slug}/{path[len('/api/'):]}"
        return getattr(client, method)(url, payload, format="json")

    def responses(self, results, count):
        """Every call returned a response -- an exception here is a 500 the client would see."""
        responses = winners(results)
        self.assertEqual(len(responses), count, results)
        return responses

    def assert_refused_on(self, resp, field):
        self.assertEqual(resp.status_code, 400, resp.content[:300])
        self.assertIn(field, resp.data)
        self.assertIn("already", str(resp.data[field]).lower())
        for marker in sequential.LEAKS:
            self.assertNotIn(marker, resp.content)

    def test_two_simultaneous_adds_are_one_201_and_one_400_on_the_field(self):
        for label, path, payload, field, model in sequential.CASES:
            with self.subTest(label):
                conversions, converting = counting_conversions()
                with all_past_validation(), converting:
                    results = run_concurrently(lambda _: self.send("post", path, payload), count=2)

                responses = self.responses(results, 2)
                self.assertEqual(
                    sorted(r.status_code for r in responses),
                    [201, 400],
                    [r.content[:200] for r in responses],
                )
                self.assert_refused_on(next(r for r in responses if r.status_code == 400), field)
                self.assertEqual(len(conversions), 1, conversions)
                self.assertEqual(model.objects.count(), 1)

    def test_a_burst_of_identical_adds_leaves_exactly_one_plan(self):
        """Unforced: five saves landing together, however the timing falls."""
        results = run_concurrently(lambda _: self.send("post", "/api/billing/plans/", MONTHLY), count=5)

        responses = self.responses(results, 5)
        self.assertEqual(sorted(r.status_code for r in responses), [201, 400, 400, 400, 400])
        for resp in responses:
            if resp.status_code == 400:
                self.assert_refused_on(resp, "name")
        self.assertEqual(Plan.objects.filter(name="Monthly").count(), 1)

    def test_two_simultaneous_renames_to_one_name_are_one_200_and_one_400(self):
        plans = [
            Plan.objects.create(**MONTHLY),
            Plan.objects.create(**dict(MONTHLY, name="Quarterly", duration_days=90)),
        ]

        conversions, converting = counting_conversions()
        with all_past_validation(), converting:
            results = run_concurrently(
                lambda i: self.send("patch", f"/api/billing/plans/{plans[i].pk}/", {"name": "Annual"}),
                count=2,
            )

        responses = self.responses(results, 2)
        self.assertEqual(sorted(r.status_code for r in responses), [200, 400])
        self.assert_refused_on(next(r for r in responses if r.status_code == 400), "name")
        self.assertEqual(len(conversions), 1, conversions)
        self.assertEqual(Plan.objects.filter(name="Annual").count(), 1)
        self.assertEqual(Plan.objects.count(), 2)
