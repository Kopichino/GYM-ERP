from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from accounts.models import MemberProfile, Role
from billing.models import Payment, PaymentStatus, Plan
from billing.services import record_payment

from .models import CommissionBasis, CommissionEntry, CommissionRule, EntryStatus, Payout
from .services import accrue_for_payment, rule_for, settle, void_for_payment

User = get_user_model()
TODAY = timezone.localdate()


def make_user(username, role=Role.MEMBER):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    MemberProfile.objects.get_or_create(user=user)
    return user


class RuleResolutionTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.trainer = make_user("trainer", Role.TRAINER)
        self.other = make_user("other_trainer", Role.TRAINER)
        self.monthly = Plan.objects.create(name="Monthly", price=Decimal("1000"), duration_days=30)
        self.annual = Plan.objects.create(name="Annual", price=Decimal("10000"), duration_days=365)

    def test_the_most_specific_rule_wins(self):
        CommissionRule.objects.create(basis=CommissionBasis.PERCENT, rate=Decimal("5"))
        trainer_rule = CommissionRule.objects.create(
            trainer=self.trainer, basis=CommissionBasis.PERCENT, rate=Decimal("10")
        )
        both = CommissionRule.objects.create(
            trainer=self.trainer, plan=self.annual, basis=CommissionBasis.PERCENT, rate=Decimal("15")
        )

        self.assertEqual(rule_for(self.trainer, self.annual), both)
        self.assertEqual(rule_for(self.trainer, self.monthly), trainer_rule)
        # The other trainer only matches the gym-wide default.
        self.assertEqual(rule_for(self.other, self.annual).rate, Decimal("5"))

    def test_inactive_rules_are_ignored(self):
        CommissionRule.objects.create(
            trainer=self.trainer, basis=CommissionBasis.PERCENT, rate=Decimal("10"), is_active=False
        )
        self.assertIsNone(rule_for(self.trainer, self.monthly))


class AccrualTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.trainer = make_user("trainer", Role.TRAINER)
        self.member = make_user("member")
        self.member.profile.trainer = self.trainer
        self.member.profile.save()
        self.plan = Plan.objects.create(name="Monthly", price=Decimal("1000"), duration_days=30)

    def _pay(self, amount="1000", status=PaymentStatus.COMPLETED):
        return record_payment(
            member=self.member, plan=self.plan, amount=Decimal(amount), method="cash", status=status
        )

    def test_a_percentage_rule_earns_from_the_payment(self):
        CommissionRule.objects.create(
            trainer=self.trainer, basis=CommissionBasis.PERCENT, rate=Decimal("10")
        )
        entry = accrue_for_payment(self._pay())
        self.assertEqual(entry.amount, Decimal("100.00"))
        self.assertEqual(entry.status, EntryStatus.PENDING)

    def test_a_flat_rule_earns_a_fixed_amount(self):
        CommissionRule.objects.create(
            trainer=self.trainer, basis=CommissionBasis.FLAT, rate=Decimal("250")
        )
        self.assertEqual(accrue_for_payment(self._pay()).amount, Decimal("250.00"))

    def test_commission_is_taken_on_what_was_actually_paid(self):
        """A discounted sale earns commission on the discounted figure, not the
        list price -- the gym never received the difference."""
        CommissionRule.objects.create(
            trainer=self.trainer, basis=CommissionBasis.PERCENT, rate=Decimal("10")
        )
        entry = accrue_for_payment(self._pay(amount="800"))
        self.assertEqual(entry.amount, Decimal("80.00"))

    def test_a_member_with_no_trainer_earns_nobody_anything(self):
        CommissionRule.objects.create(basis=CommissionBasis.PERCENT, rate=Decimal("10"))
        loner = make_user("loner")
        payment = record_payment(
            member=loner, plan=self.plan, amount=Decimal("1000"), method="cash"
        )
        self.assertIsNone(accrue_for_payment(payment))

    def test_no_matching_rule_means_no_entry(self):
        self.assertIsNone(accrue_for_payment(self._pay()))

    def test_accruing_twice_does_not_double_pay(self):
        CommissionRule.objects.create(
            trainer=self.trainer, basis=CommissionBasis.PERCENT, rate=Decimal("10")
        )
        payment = self._pay()
        accrue_for_payment(payment)
        accrue_for_payment(payment)
        self.assertEqual(CommissionEntry.objects.filter(payment=payment).count(), 1)

    def test_the_rate_is_snapshotted_so_editing_a_rule_never_restates_earnings(self):
        rule = CommissionRule.objects.create(
            trainer=self.trainer, basis=CommissionBasis.PERCENT, rate=Decimal("10")
        )
        entry = accrue_for_payment(self._pay())

        rule.rate = Decimal("50")
        rule.save()
        entry.refresh_from_db()

        self.assertEqual(entry.rate_applied, Decimal("10.00"))
        self.assertEqual(entry.amount, Decimal("100.00"))

    def test_a_refunded_payment_reverses_the_commission(self):
        CommissionRule.objects.create(
            trainer=self.trainer, basis=CommissionBasis.PERCENT, rate=Decimal("10")
        )
        payment = self._pay()
        entry = accrue_for_payment(payment)

        payment.status = PaymentStatus.REFUNDED
        payment.save()
        accrue_for_payment(payment)

        entry.refresh_from_db()
        self.assertEqual(entry.status, EntryStatus.VOID)

    def test_voiding_a_payment_voids_a_pending_entry(self):
        CommissionRule.objects.create(
            trainer=self.trainer, basis=CommissionBasis.PERCENT, rate=Decimal("10")
        )
        payment = self._pay()
        accrue_for_payment(payment)
        entry = void_for_payment(payment)
        self.assertEqual(entry.status, EntryStatus.VOID)

    def test_an_already_settled_entry_is_not_clawed_back_automatically(self):
        """Money that has left the building is a person's decision to recover,
        not something a delete should do silently."""
        CommissionRule.objects.create(
            trainer=self.trainer, basis=CommissionBasis.PERCENT, rate=Decimal("10")
        )
        payment = self._pay()
        entry = accrue_for_payment(payment)
        entry.status = EntryStatus.PAID
        entry.save()

        void_for_payment(payment)
        entry.refresh_from_db()
        self.assertEqual(entry.status, EntryStatus.PAID)


class PayoutTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = make_user("admin", Role.ADMIN)
        self.trainer = make_user("trainer", Role.TRAINER)
        self.member = make_user("member")
        self.member.profile.trainer = self.trainer
        self.member.profile.save()
        self.plan = Plan.objects.create(name="Monthly", price=Decimal("1000"), duration_days=30)
        CommissionRule.objects.create(
            trainer=self.trainer, basis=CommissionBasis.PERCENT, rate=Decimal("10")
        )
        for _ in range(3):
            accrue_for_payment(
                record_payment(
                    member=self.member, plan=self.plan, amount=Decimal("1000"), method="cash"
                )
            )

    def test_settling_marks_entries_paid_and_totals_them(self):
        payout = settle(self.trainer, TODAY - timedelta(days=1), TODAY + timedelta(days=1))
        self.assertEqual(payout.total, Decimal("300.00"))
        self.assertEqual(payout.entries.count(), 3)
        self.assertFalse(
            CommissionEntry.objects.filter(trainer=self.trainer, status=EntryStatus.PENDING).exists()
        )

    def test_settling_twice_does_not_pay_the_same_entry_again(self):
        settle(self.trainer, TODAY - timedelta(days=1), TODAY + timedelta(days=1))
        second = settle(self.trainer, TODAY - timedelta(days=1), TODAY + timedelta(days=1))
        self.assertEqual(second.total, Decimal("0.00"))

    def test_entries_outside_the_window_are_left_alone(self):
        payout = settle(self.trainer, TODAY - timedelta(days=30), TODAY - timedelta(days=20))
        self.assertEqual(payout.total, Decimal("0.00"))
        self.assertEqual(
            CommissionEntry.objects.filter(status=EntryStatus.PENDING).count(), 3
        )


class CommissionAccessTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = make_user("admin", Role.ADMIN)
        self.trainer = make_user("trainer", Role.TRAINER)
        self.other_trainer = make_user("other_trainer", Role.TRAINER)
        self.member = make_user("member")
        self.member.profile.trainer = self.trainer
        self.member.profile.save()
        self.plan = Plan.objects.create(name="Monthly", price=Decimal("1000"), duration_days=30)
        CommissionRule.objects.create(
            trainer=self.trainer, basis=CommissionBasis.PERCENT, rate=Decimal("10")
        )
        accrue_for_payment(
            record_payment(member=self.member, plan=self.plan, amount=Decimal("1000"), method="cash")
        )

    def test_rules_and_entries_are_admin_only(self):
        for user in (self.member, self.trainer):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get("/api/commissions/rules/").status_code, 403)
            self.assertEqual(self.client.get("/api/commissions/entries/").status_code, 403)

    def test_a_trainer_sees_only_their_own_earnings(self):
        self.client.force_authenticate(self.trainer)
        self.assertEqual(self.client.get("/api/commissions/my-earnings/").data["count"], 1)

        self.client.force_authenticate(self.other_trainer)
        self.assertEqual(self.client.get("/api/commissions/my-earnings/").data["count"], 0)

    def test_my_earnings_summary(self):
        self.client.force_authenticate(self.trainer)
        data = self.client.get("/api/commissions/my-earnings/summary/").data
        self.assertEqual(data["pending_total"], Decimal("100.00"))
        self.assertEqual(data["pending_count"], 1)
        self.assertEqual(data["paid_count"], 0)

    def test_entries_cannot_be_created_by_hand(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post("/api/commissions/entries/", {"amount": "9999"})
        self.assertEqual(resp.status_code, 405)

    def test_a_payout_totals_from_the_entries_not_the_request(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/commissions/payouts/",
            {
                "trainer": self.trainer.pk,
                "period_start": str(TODAY - timedelta(days=1)),
                "period_end": str(TODAY + timedelta(days=1)),
                "total": "99999",
            },
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Payout.objects.get().total, Decimal("100.00"))
