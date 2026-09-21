"""Deleting a plan that has already been sold.

`Payment.plan` and `PaymentOrder.plan` are PROTECT: the ledger, and the
invoices hanging off it, are the gym's financial history, and a plan cannot be
pulled out from under them. The model has always refused; these pin that the
API says so as a readable 400 instead of letting the ProtectedError escape as
a 500.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from accounts.models import MemberProfile, Role
from invoicing.models import Invoice
from invoicing.services import issue_invoice

from .models import Payment, PaymentGateway, PaymentOrder, Plan
from .services import record_payment

User = get_user_model()


def make_user(username, role=Role.MEMBER):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    MemberProfile.objects.get_or_create(user=user)
    return user


class PlanDeleteTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = make_user("plan_admin", Role.ADMIN)
        self.member = make_user("plan_member")
        self.plan = Plan.objects.create(name="Monthly", price=Decimal("1500"), duration_days=30)

    def url(self):
        return f"/api/billing/plans/{self.plan.id}/"

    def test_a_plan_with_payments_is_refused_and_its_history_is_untouched(self):
        payment = record_payment(
            member=self.member, plan=self.plan, amount=Decimal("1500"), method="cash"
        )
        number = issue_invoice(payment).number

        self.client.force_authenticate(self.admin)
        resp = self.client.delete(self.url())

        self.assertEqual(resp.status_code, 400)
        self.assertIn("Deactivate it instead", str(resp.data["detail"]))
        # The ProtectedError's own text names models and rows; none of it
        # belongs in a response.
        self.assertNotIn("Payment.plan", resp.content.decode())
        self.assertTrue(Plan.objects.filter(pk=self.plan.pk).exists())
        payment.refresh_from_db()
        self.assertEqual(payment.plan_id, self.plan.pk)
        self.assertEqual(Invoice.objects.get(payment=payment).number, number)

    def test_a_plan_with_only_a_payment_order_is_refused(self):
        # An online checkout opened but not yet settled still prices against
        # this plan when the gateway calls back.
        order = PaymentOrder.objects.create(
            member=self.member,
            plan=self.plan,
            amount=Decimal("1500.00"),
            order_id="order_PLANDEL1",
            gateway=PaymentGateway.RAZORPAY,
        )
        self.assertFalse(Payment.objects.filter(plan=self.plan).exists())

        self.client.force_authenticate(self.admin)
        resp = self.client.delete(self.url())

        self.assertEqual(resp.status_code, 400)
        self.assertTrue(Plan.objects.filter(pk=self.plan.pk).exists())
        self.assertTrue(PaymentOrder.objects.filter(pk=order.pk, plan=self.plan).exists())

    def test_a_plan_that_was_never_sold_can_be_deleted(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.delete(self.url())
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Plan.objects.filter(pk=self.plan.pk).exists())

    def test_only_an_admin_can_delete_a_plan(self):
        for user in (self.member, make_user("plan_trainer", Role.TRAINER)):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.delete(self.url()).status_code, 403)
        self.assertTrue(Plan.objects.filter(pk=self.plan.pk).exists())
