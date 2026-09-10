from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from accounts.models import MembershipStatus, MemberProfile, Role

from .models import Discount, DiscountType, Payment, PaymentStatus, Plan
from .services import DiscountError, price_with_discount, record_payment

User = get_user_model()
TODAY = timezone.localdate()


def make_user(username, role=Role.MEMBER):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    MemberProfile.objects.get_or_create(user=user)
    return user


class DiscountPricingTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.member = make_user("member")
        self.monthly = Plan.objects.create(name="Monthly", price=Decimal("1000"), duration_days=30)
        self.annual = Plan.objects.create(name="Annual", price=Decimal("10000"), duration_days=365)

    def _discount(self, code, kind, value, **kwargs):
        return Discount.objects.create(
            code=code, discount_type=kind, value=Decimal(str(value)), **kwargs
        )

    def test_no_code_charges_list_price(self):
        discount, off, total = price_with_discount(self.monthly, self.member, None)
        self.assertIsNone(discount)
        self.assertEqual(off, Decimal("0.00"))
        self.assertEqual(total, Decimal("1000.00"))

    def test_percentage_off(self):
        self._discount("NEWYEAR", DiscountType.PERCENT, 20)
        _, off, total = price_with_discount(self.monthly, self.member, "NEWYEAR")
        self.assertEqual(off, Decimal("200.00"))
        self.assertEqual(total, Decimal("800.00"))

    def test_flat_amount_off(self):
        self._discount("FLAT250", DiscountType.FLAT, 250)
        _, off, total = price_with_discount(self.monthly, self.member, "FLAT250")
        self.assertEqual(off, Decimal("250.00"))
        self.assertEqual(total, Decimal("750.00"))

    def test_codes_are_case_insensitive_and_stored_upper(self):
        self._discount("summer", DiscountType.PERCENT, 10)
        self.assertEqual(Discount.objects.get().code, "SUMMER")
        _, off, _total = price_with_discount(self.monthly, self.member, "  sUmMeR ")
        self.assertEqual(off, Decimal("100.00"))

    def test_a_discount_can_never_exceed_the_price(self):
        """An offer worth more than the plan must not hand money back."""
        self._discount("HUGE", DiscountType.FLAT, 5000)
        _, off, total = price_with_discount(self.monthly, self.member, "HUGE")
        self.assertEqual(off, Decimal("1000"))
        self.assertEqual(total, Decimal("0.00"))

    def test_unknown_code_is_refused(self):
        with self.assertRaises(DiscountError):
            price_with_discount(self.monthly, self.member, "NOPE")

    def test_inactive_code_is_refused(self):
        self._discount("OFF", DiscountType.PERCENT, 10, is_active=False)
        with self.assertRaises(DiscountError):
            price_with_discount(self.monthly, self.member, "OFF")

    def test_expired_and_not_yet_started_codes_are_refused(self):
        self._discount("PAST", DiscountType.PERCENT, 10, valid_until=TODAY - timedelta(days=1))
        self._discount("FUTURE", DiscountType.PERCENT, 10, valid_from=TODAY + timedelta(days=5))
        for code in ("PAST", "FUTURE"):
            with self.assertRaises(DiscountError):
                price_with_discount(self.monthly, self.member, code)

    def test_code_restricted_to_other_plans_is_refused(self):
        annual_only = self._discount("ANNUAL10", DiscountType.PERCENT, 10)
        annual_only.plans.add(self.annual)

        _, off, _t = price_with_discount(self.annual, self.member, "ANNUAL10")
        self.assertEqual(off, Decimal("1000.00"))

        with self.assertRaises(DiscountError):
            price_with_discount(self.monthly, self.member, "ANNUAL10")

    def test_usage_cap_counts_completed_payments_only(self):
        discount = self._discount("ONCE", DiscountType.FLAT, 100, max_uses=1, max_uses_per_member=0)
        record_payment(
            member=self.member,
            plan=self.monthly,
            amount=Decimal("900"),
            method="cash",
            discount=discount,
            discount_amount=Decimal("100"),
        )
        self.assertEqual(discount.times_used, 1)
        with self.assertRaises(DiscountError):
            price_with_discount(self.monthly, make_user("other"), "ONCE")

    def test_a_voided_payment_frees_the_usage_back_up(self):
        """times_used is derived from the ledger, so deleting the payment
        releases the redemption instead of leaving a stale counter."""
        discount = self._discount("ONCE", DiscountType.FLAT, 100, max_uses=1, max_uses_per_member=0)
        payment = record_payment(
            member=self.member,
            plan=self.monthly,
            amount=Decimal("900"),
            method="cash",
            discount=discount,
            discount_amount=Decimal("100"),
        )
        payment.delete()
        self.assertEqual(discount.times_used, 0)
        price_with_discount(self.monthly, self.member, "ONCE")  # no longer refused

    def test_per_member_cap(self):
        discount = self._discount("WELCOME", DiscountType.FLAT, 100, max_uses_per_member=1)
        record_payment(
            member=self.member,
            plan=self.monthly,
            amount=Decimal("900"),
            method="cash",
            discount=discount,
            discount_amount=Decimal("100"),
        )
        with self.assertRaises(DiscountError):
            price_with_discount(self.monthly, self.member, "WELCOME")
        # A different member may still use it.
        price_with_discount(self.monthly, make_user("second"), "WELCOME")


class CheckoutApiTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = make_user("admin", Role.ADMIN)
        self.member = make_user("member")
        self.trainer = make_user("trainer", Role.TRAINER)
        self.plan = Plan.objects.create(name="Monthly", price=Decimal("1000"), duration_days=30)
        Discount.objects.create(
            code="SAVE20", discount_type=DiscountType.PERCENT, value=Decimal("20")
        )
        self.client.force_authenticate(self.admin)

    def _payload(self, **extra):
        return {"member": self.member.pk, "plan": self.plan.pk, **extra}

    def test_checkout_is_admin_only(self):
        for user in (self.member, self.trainer):
            self.client.force_authenticate(user)
            self.assertEqual(
                self.client.post("/api/billing/checkout/quote/", self._payload()).status_code, 403
            )
            self.assertEqual(
                self.client.post("/api/billing/checkout/", self._payload()).status_code, 403
            )

    def test_quote_writes_nothing(self):
        before = Payment.objects.count()
        resp = self.client.post("/api/billing/checkout/quote/", self._payload(code="SAVE20"))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["list_price"], "1000.00")
        self.assertEqual(resp.data["discount_amount"], "200.00")
        self.assertEqual(resp.data["total"], "800.00")
        self.assertEqual(Payment.objects.count(), before)

    def test_quote_rejects_a_bad_code_before_any_money_moves(self):
        resp = self.client.post("/api/billing/checkout/quote/", self._payload(code="WRONG"))
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(resp.data["code_rejected"])
        self.assertEqual(Payment.objects.count(), 0)

    def test_checkout_records_the_discounted_payment(self):
        resp = self.client.post("/api/billing/checkout/", self._payload(code="SAVE20", method="upi"))
        self.assertEqual(resp.status_code, 201)

        payment = Payment.objects.get()
        # `amount` is the money that actually moved; gross is derived.
        self.assertEqual(payment.amount, Decimal("800.00"))
        self.assertEqual(payment.discount_amount, Decimal("200.00"))
        self.assertEqual(payment.discount.code, "SAVE20")
        self.assertEqual(resp.data["payment"]["gross_amount"], "1000.00")

    def test_checkout_reactivates_a_lapsed_member_through_the_derived_status(self):
        """The whole reason checkout calls record_payment rather than inserting
        a Payment itself. A fresh profile already defaults to active, so start
        the member expired -- only a real re-sync can flip that back."""
        MemberProfile.objects.filter(user=self.member).update(
            membership_status=MembershipStatus.EXPIRED
        )
        self.client.post("/api/billing/checkout/", self._payload())

        self.member.profile.refresh_from_db()
        self.assertEqual(self.member.profile.membership_status, MembershipStatus.ACTIVE)

    def test_a_renewal_stacks_on_the_existing_period(self):
        first = self.client.post("/api/billing/checkout/", self._payload()).data
        second = self.client.post("/api/billing/checkout/", self._payload()).data

        self.assertFalse(first["extends_existing"])
        self.assertTrue(second["extends_existing"])
        self.assertEqual(second["period_start"], first["period_end"])

    def test_the_quote_matches_what_checkout_charges(self):
        quote = self.client.post(
            "/api/billing/checkout/quote/", self._payload(code="SAVE20")
        ).data
        sale = self.client.post("/api/billing/checkout/", self._payload(code="SAVE20")).data

        for field in ("list_price", "discount_amount", "total", "period_start", "period_end"):
            self.assertEqual(quote[field], sale[field], f"{field} drifted between quote and sale")


class DiscountAdminApiTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = make_user("admin", Role.ADMIN)
        self.member = make_user("member")

    def test_offers_are_admin_only(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get("/api/billing/discounts/").status_code, 403)

    def test_percentage_over_100_is_rejected(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/billing/discounts/",
            {"code": "TOOMUCH", "discount_type": "percent", "value": "120"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("value", resp.data)

    def test_end_date_before_start_is_rejected(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/billing/discounts/",
            {
                "code": "BACKWARDS",
                "discount_type": "flat",
                "value": "100",
                "valid_from": str(TODAY),
                "valid_until": str(TODAY - timedelta(days=1)),
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("valid_until", resp.data)

    def test_times_used_is_reported(self):
        self.client.force_authenticate(self.admin)
        self.client.post(
            "/api/billing/discounts/",
            {"code": "TRACKED", "discount_type": "flat", "value": "100"},
        )
        row = self.client.get("/api/billing/discounts/").data["results"][0]
        self.assertEqual(row["times_used"], 0)
        self.assertEqual(row["plan_names"], ["All plans"])


class CustomAmountCheckoutTests(TenantAPIMixin, APITestCase):
    """A gym negotiates. The till has to take a price that no offer covers,
    without that money falling off the books."""

    def setUp(self):
        self.admin = make_user("admin", Role.ADMIN)
        self.member = make_user("member")
        self.annual = Plan.objects.create(
            name="Annual", price=Decimal("14000"), duration_days=365
        )
        self.client.force_authenticate(self.admin)

    def _payload(self, **extra):
        return {"member": self.member.pk, "plan": self.annual.pk, **extra}

    def test_an_agreed_price_with_no_offer_code_is_chargeable(self):
        resp = self.client.post("/api/billing/checkout/", self._payload(amount="8000"))
        self.assertEqual(resp.status_code, 201)

        payment = Payment.objects.get()
        self.assertEqual(payment.amount, Decimal("8000.00"))
        # The gap to list price is booked as a discount, so gross still
        # reconciles to what the plan is actually worth.
        self.assertEqual(payment.discount_amount, Decimal("6000.00"))
        self.assertIsNone(payment.discount)
        self.assertEqual(resp.data["payment"]["gross_amount"], "14000.00")

    def test_the_quote_reflects_the_typed_amount_before_charging(self):
        resp = self.client.post("/api/billing/checkout/quote/", self._payload(amount="8000"))
        self.assertEqual(resp.data["total"], "8000.00")
        self.assertEqual(resp.data["discount_amount"], "6000.00")
        self.assertTrue(resp.data["custom_amount"])
        self.assertEqual(Payment.objects.count(), 0)

    def test_omitting_the_amount_still_charges_the_plan_price(self):
        resp = self.client.post("/api/billing/checkout/", self._payload())
        self.assertEqual(resp.data["total"], "14000.00")
        self.assertFalse(resp.data["custom_amount"])
        self.assertEqual(Payment.objects.get().discount_amount, Decimal("0.00"))

    def test_a_custom_amount_still_activates_the_membership(self):
        MemberProfile.objects.filter(user=self.member).update(
            membership_status=MembershipStatus.EXPIRED
        )
        self.client.post("/api/billing/checkout/", self._payload(amount="8000"))

        self.member.profile.refresh_from_db()
        self.assertEqual(self.member.profile.membership_status, MembershipStatus.ACTIVE)

    def test_paying_over_list_price_never_books_a_negative_discount(self):
        self.client.post("/api/billing/checkout/", self._payload(amount="15000"))
        payment = Payment.objects.get()
        self.assertEqual(payment.amount, Decimal("15000.00"))
        self.assertEqual(payment.discount_amount, Decimal("0.00"))

    def test_a_code_and_a_typed_amount_together_book_the_whole_gap(self):
        Discount.objects.create(
            code="SAVE10", discount_type=DiscountType.PERCENT, value=Decimal("10")
        )
        resp = self.client.post(
            "/api/billing/checkout/", self._payload(code="SAVE10", amount="8000")
        )
        payment = Payment.objects.get()
        self.assertEqual(payment.amount, Decimal("8000.00"))
        self.assertEqual(payment.discount_amount, Decimal("6000.00"))
        # The code is still recorded against the sale even though the operator
        # overrode the figure it produced.
        self.assertEqual(payment.discount.code, "SAVE10")
        self.assertEqual(resp.data["total"], "8000.00")

    def test_a_negative_amount_is_refused(self):
        resp = self.client.post("/api/billing/checkout/", self._payload(amount="-500"))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Payment.objects.count(), 0)
