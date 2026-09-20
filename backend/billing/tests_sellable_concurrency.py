"""A plan retired while a sale is going through is not sold.

`tests_sellable` covers a plan that was retired before the sale started. These
cover the moment in between: the till has already checked the plan when an
admin switches it off. A sale that checks first and writes later leaves a gap
in which the plan can be sold after it was retired, so the check has to be
repeated under a lock in the transaction that writes the payment.

Postgres only -- SQLite serialises writers and ignores row locks (see
core.testing).
"""

import threading
import time
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from accounts.models import MemberProfile, Role
from core.testing import founding_tenant, requires_row_locks
from invoicing.models import Invoice
from tenancy import context
from tenancy.models import Membership

from . import views
from .models import Payment, Plan
from .serializers import AdminPaymentSerializer

User = get_user_model()

NOT_ON_SALE = "That plan is no longer on sale."


@requires_row_locks
class PlanRetiredDuringASaleTests(TransactionTestCase):
    def setUp(self):
        super().setUp()
        _, self.tenant = founding_tenant("retiregym")
        self._scope_token = context.set(self.tenant)
        self.admin = self._person("owner", Role.ADMIN)
        self.member = self._person("member", Role.MEMBER)
        self.plan = Plan.objects.create(name="Monthly", price=Decimal("1000"), duration_days=30)

    def tearDown(self):
        context.reset(self._scope_token)
        super().tearDown()

    def _person(self, username, role):
        user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password="pass12345", role=role
        )
        MemberProfile.objects.get_or_create(user=user)
        Membership.objects.create(user=user, tenant=self.tenant, role=role)
        return user

    def post(self, path, payload):
        """One admin's request from its own client, as the till would send it."""
        client = APIClient()
        client.force_authenticate(self.admin)
        return client.post(f"/api/t/{self.tenant.slug}/{path}", payload, format="json")

    def in_background(self, work):
        """Runs `work` on its own thread and connection. Returns the thread and a
        list that receives its result -- or the exception, which for a request
        is a 500 the till would have seen."""
        outcome = []

        def run():
            try:
                outcome.append(work())
            except BaseException as exc:  # noqa: BLE001 -- the exception is the result
                outcome.append(exc)
            finally:
                connections.close_all()

        thread = threading.Thread(target=run)
        thread.start()
        return thread, outcome

    def retire(self):
        """What the Plans page's Deactivate does, committed from another connection."""
        Plan.unscoped.filter(pk=self.plan.pk).update(is_active=False)

    def race(self, owner, attribute, path, payload):
        """Pauses the request right after its own on-sale check, retires the plan,
        then lets the request finish."""
        checked, resume = threading.Event(), threading.Event()
        original = getattr(owner, attribute)

        def paused(*args, **kwargs):
            value = original(*args, **kwargs)
            checked.set()
            resume.wait(timeout=15)
            return value

        with mock.patch.object(owner, attribute, paused):
            thread, outcome = self.in_background(lambda: self.post(path, payload))
            self.assertTrue(checked.wait(timeout=15), "the request never reached its on-sale check")
            self.retire()
            resume.set()
            thread.join(timeout=30)
        self.assertFalse(thread.is_alive(), "the request did not finish")
        [resp] = outcome
        return resp

    def assert_refused_and_nothing_written(self, resp):
        self.assertNotIsInstance(resp, BaseException, resp)
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual([str(message) for message in resp.data["plan"]], [NOT_ON_SALE])
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(Invoice.objects.exists())

    def test_a_counter_sale_is_refused_when_the_plan_is_retired_after_its_check(self):
        resp = self.race(
            views._CheckoutBase,
            "_plan_on_sale",
            "billing/checkout/",
            {"member": self.member.pk, "plan": self.plan.pk},
        )
        self.assert_refused_and_nothing_written(resp)

    def test_a_recorded_payment_is_refused_when_the_plan_is_retired_after_its_check(self):
        resp = self.race(
            AdminPaymentSerializer,
            "validate_plan",
            "billing/admin/payments/",
            {"member": self.member.pk, "plan": self.plan.pk, "amount": "1000.00", "method": "cash"},
        )
        self.assert_refused_and_nothing_written(resp)

    def test_retiring_a_plan_waits_for_a_sale_already_being_written(self):
        """The till got there first: the plan was on sale when the sale was being
        written, so the sale stands -- and switching the plan off waits for it
        instead of slipping in underneath."""
        writing = threading.Event()
        original = views.record_payment

        def slow_record_payment(**kwargs):
            writing.set()
            time.sleep(1.5)  # still inside the sale's transaction
            return original(**kwargs)

        with mock.patch.object(views, "record_payment", slow_record_payment):
            thread, outcome = self.in_background(
                lambda: self.post("billing/checkout/", {"member": self.member.pk, "plan": self.plan.pk})
            )
            self.assertTrue(writing.wait(timeout=15), "the sale never started writing")
            started = time.monotonic()
            self.retire()
            waited = time.monotonic() - started
            thread.join(timeout=30)

        [resp] = outcome
        self.assertNotIsInstance(resp, BaseException, resp)
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertGreaterEqual(waited, 1.0, f"retiring the plan waited only {waited:.2f}s for the sale")
        self.assertEqual(Payment.objects.get().plan_id, self.plan.pk)
        self.assertFalse(Plan.unscoped.get(pk=self.plan.pk).is_active)
