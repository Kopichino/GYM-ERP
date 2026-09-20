"""Whether a plan can be sold: decided in one place, enforced by the API.

A deactivated plan dropped off the public price list but stayed sellable at the
desk. The counter checkout and the record-payment endpoint looked plans up with
no regard for `is_active`, so the API sold whatever id it was sent -- and the
till's picker filtered a cached list that deactivating a plan never refreshed.

The other half is history. Payments, invoices and memberships already on a plan
must keep working after it is retired: retiring a plan stops new sales, it does
not rewrite what was sold.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from accounts.models import MemberProfile, Role
from core.testing import TenantAPIMixin, founding_tenant
from invoicing.models import Invoice
from invoicing.services import issue_invoice
from tenancy import context

from .models import OrderStatus, Payment, PaymentMethod, PaymentOrder, Plan
from .services import record_payment, settle_online_order

User = get_user_model()

NOT_ON_SALE = "That plan is no longer on sale."


class PlanSellabilityTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = self._person("owner", Role.ADMIN)
        self.member = self._person("member")
        self.plan = Plan.objects.create(name="Monthly", price=Decimal("1000"), duration_days=30)
        self.retired = Plan.objects.create(
            name="Old Yearly", price=Decimal("9000"), duration_days=365, is_active=False
        )

    def _person(self, username, role=Role.MEMBER):
        user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password="pass12345", role=role
        )
        MemberProfile.objects.get_or_create(user=user)
        self.member_for(user, role)
        return user

    def as_admin(self):
        self.client.force_authenticate(self.admin)

    def sale(self, plan_id, path="/api/billing/checkout/"):
        self.as_admin()
        return self.client.post(path, {"member": self.member.pk, "plan": plan_id})

    def plan_ids(self, path, user):
        self.client.force_authenticate(user)
        resp = self.client.get(path)
        self.assertEqual(resp.status_code, 200, resp.content)
        rows = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        return {row["id"] for row in rows}

    def set_active(self, plan, active):
        self.as_admin()
        resp = self.client.patch(
            f"/api/billing/plans/{plan.pk}/", {"is_active": active}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)

    def assert_not_on_sale(self, resp):
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual([str(message) for message in resp.data["plan"]], [NOT_ON_SALE])

    # -- activate -> sellable, deactivate -> not

    def test_an_active_plan_is_offered_and_sold(self):
        self.assertIn(self.plan.pk, self.plan_ids("/api/billing/plans/?sellable=1", self.admin))
        resp = self.sale(self.plan.pk)
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Payment.objects.get().plan, self.plan)

    def test_a_deactivated_plan_leaves_every_list_a_sale_starts_from(self):
        self.set_active(self.plan, False)
        self.assertNotIn(self.plan.pk, self.plan_ids("/api/billing/plans/?sellable=1", self.admin))
        self.assertNotIn(self.plan.pk, self.plan_ids("/api/billing/plans/", self.member))
        self.client.force_authenticate(None)
        public = {row["id"] for row in self.client.get("/api/billing/public/plans/").data}
        self.assertNotIn(self.plan.pk, public)
        # The Plans page still lists it, so it can be switched back on.
        self.assertIn(self.plan.pk, self.plan_ids("/api/billing/plans/", self.admin))

    def test_reactivating_a_plan_makes_it_sellable_again(self):
        self.set_active(self.retired, True)
        self.assertIn(self.retired.pk, self.plan_ids("/api/billing/plans/?sellable=1", self.admin))
        self.assertEqual(self.sale(self.retired.pk).status_code, 201)

    # -- the API refuses a retired plan however it is sent

    def test_a_retired_plan_cannot_be_priced_at_the_counter(self):
        self.assert_not_on_sale(self.sale(self.retired.pk, "/api/billing/checkout/quote/"))

    def test_a_retired_plan_cannot_be_sold_at_the_counter(self):
        self.assert_not_on_sale(self.sale(self.retired.pk))
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(Invoice.objects.exists())

    def test_a_retired_plan_cannot_be_recorded_as_a_new_payment(self):
        self.as_admin()
        resp = self.client.post(
            "/api/billing/admin/payments/",
            {"member": self.member.pk, "plan": self.retired.pk, "amount": "9000.00", "method": "cash"},
        )
        self.assert_not_on_sale(resp)
        self.assertFalse(Payment.objects.exists())

    @override_settings(RAZORPAY_KEY_ID="rzp_test_key", RAZORPAY_KEY_SECRET="rzp_test_secret")
    def test_a_retired_plan_cannot_be_bought_online(self):
        self.client.force_authenticate(self.member)
        resp = self.client.post("/api/billing/online/order/", {"plan": self.retired.pk})
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(PaymentOrder.objects.exists())

    def test_a_payment_cannot_be_moved_onto_a_retired_plan(self):
        payment = record_payment(
            member=self.member, plan=self.plan, amount=Decimal("1000"), method=PaymentMethod.CASH
        )
        self.as_admin()
        resp = self.client.patch(
            f"/api/billing/admin/payments/{payment.pk}/", {"plan": self.retired.pk}, format="json"
        )
        self.assert_not_on_sale(resp)
        payment.refresh_from_db()
        self.assertEqual(payment.plan, self.plan)

    def test_an_unknown_plan_is_still_a_404(self):
        self.assertEqual(self.sale(999_999).status_code, 404)

    # -- history on a retired plan

    def test_history_on_a_retired_plan_stays_readable_and_editable(self):
        payment = record_payment(
            member=self.member, plan=self.plan, amount=Decimal("1000"), method=PaymentMethod.CASH
        )
        invoice = issue_invoice(payment)
        self.set_active(self.plan, False)

        self.client.force_authenticate(self.member)
        subscription = self.client.get("/api/billing/my-subscription/")
        self.assertEqual(subscription.status_code, 200)
        self.assertEqual(subscription.data["plan"]["name"], "Monthly")
        mine = self.client.get("/api/billing/my-payments/").data["results"]
        self.assertEqual([row["plan_name"] for row in mine], ["Monthly"])
        self.assertEqual(self.client.get(f"/api/invoices/{invoice.pk}/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/invoices/{invoice.pk}/pdf/").status_code, 200)

        self.as_admin()
        ledger = self.client.get("/api/billing/admin/payments/").data["results"]
        self.assertEqual([row["plan_name"] for row in ledger], ["Monthly"])
        resp = self.client.patch(
            f"/api/billing/admin/payments/{payment.pk}/",
            {"notes": "Corrected at the desk.", "plan": self.plan.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        payment.refresh_from_db()
        invoice.refresh_from_db()
        self.assertEqual((payment.plan, payment.notes), (self.plan, "Corrected at the desk."))
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(invoice.total, Decimal("1000.00"))

    def test_an_online_order_opened_before_the_plan_was_retired_still_settles(self):
        """The money has already been taken; refusing to record it would leave a
        member who paid with nothing."""
        order = PaymentOrder.objects.create(
            member=self.member, plan=self.plan, amount=Decimal("1000.00"), order_id="order_R1"
        )
        self.set_active(self.plan, False)
        payment = settle_online_order(order, gateway_payment_id="pay_R1")
        order.refresh_from_db()
        self.assertEqual((order.status, payment.plan), (OrderStatus.PAID, self.plan))

    # -- who and where

    def test_signing_in_is_required_to_list_plans(self):
        self.assertEqual(self.client.get("/api/billing/plans/?sellable=1").status_code, 401)

    def test_another_gyms_plan_cannot_be_sold_or_listed_here(self):
        _, elsewhere = founding_tenant("elsewhere")
        with context.scope(elsewhere):
            foreign = Plan.objects.create(name="Monthly", price=Decimal("500"), duration_days=30)
        self.assertNotIn(foreign.pk, self.plan_ids("/api/billing/plans/?sellable=1", self.admin))
        self.assertEqual(self.sale(foreign.pk).status_code, 404)
        self.assertFalse(Payment.unscoped.filter(plan=foreign).exists())
