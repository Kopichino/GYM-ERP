"""Trainer commission was removed from the product. These pin that it stays removed.

Rules, entries and payouts already recorded are history, and they are kept as
they were. What is gone is every way to use them: no route reads, creates,
changes or pays them out, taking a payment no longer earns a trainer anything,
no report shows a commission figure, and the Django admin only displays them.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import MemberProfile, Role
from billing.models import PaymentMethod, PaymentStatus, Plan
from billing.services import record_payment
from core.testing import TenantAPIMixin

from .models import CommissionBasis, CommissionEntry, CommissionRule, EntryStatus, Payout
from .services import accrue_for_payment, void_for_payment

User = get_user_model()

#: Every route the feature had, reads and writes alike.
FORMER_ROUTES = [
    ("get", "/api/commissions/rules/"),
    ("post", "/api/commissions/rules/"),
    ("get", "/api/commissions/rules/{rule}/"),
    ("patch", "/api/commissions/rules/{rule}/"),
    ("delete", "/api/commissions/rules/{rule}/"),
    ("get", "/api/commissions/entries/"),
    ("get", "/api/commissions/entries/{entry}/"),
    ("get", "/api/commissions/payouts/"),
    ("post", "/api/commissions/payouts/"),
    ("get", "/api/commissions/payouts/{payout}/"),
    ("get", "/api/commissions/my-earnings/"),
    ("get", "/api/commissions/my-earnings/summary/"),
]


class CommissionRemovedTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = self.person("owner", Role.ADMIN)
        self.trainer = self.person("coach", Role.TRAINER)
        self.member = self.person("member")
        self.member.profile.trainer = self.trainer
        self.member.profile.save(update_fields=["trainer"])
        self.plan = Plan.objects.create(name="Monthly", price=Decimal("1000"), duration_days=30)
        today = timezone.localdate()

        # History from before the removal: a payment, the rule that earned from
        # it, the entry it earned, and the payout that settled that entry.
        self.old_payment = record_payment(
            member=self.member, plan=self.plan, amount=Decimal("1000"), method=PaymentMethod.CASH
        )
        self.rule = CommissionRule.objects.create(basis=CommissionBasis.PERCENT, rate=Decimal("10"))
        self.payout = Payout.objects.create(
            trainer=self.trainer, period_start=today - timedelta(days=30), period_end=today,
            total=Decimal("100.00"), notes="",
        )
        self.old_entry = CommissionEntry.objects.create(
            trainer=self.trainer, payment=self.old_payment, rule=self.rule,
            basis=CommissionBasis.PERCENT, rate_applied=Decimal("10"), amount=Decimal("100.00"),
            earned_on=today, status=EntryStatus.PAID, payout=self.payout,
        )
        self.history = self.recorded()

    def person(self, username, role=Role.MEMBER):
        user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password="pass12345", role=role
        )
        MemberProfile.objects.get_or_create(user=user)
        self.member_for(user, role)
        return user

    def recorded(self):
        return {
            "rules": list(CommissionRule.objects.order_by("pk").values()),
            "entries": list(CommissionEntry.objects.order_by("pk").values()),
            "payouts": list(Payout.objects.order_by("pk").values()),
        }

    def test_every_former_commission_route_is_gone(self):
        ids = {"rule": self.rule.pk, "entry": self.old_entry.pk, "payout": self.payout.pk}
        body = {
            "trainer": self.trainer.pk, "basis": "percent", "rate": "50",
            "period_start": "2026-01-01", "period_end": "2026-12-31",
        }
        for user in (self.admin, self.trainer, self.member):
            self.client.force_authenticate(user)
            for method, template in FORMER_ROUTES:
                with self.subTest(user=user.username, method=method, route=template):
                    resp = getattr(self.client, method)(template.format(**ids), body, format="json")
                    self.assertEqual(resp.status_code, 404)
        self.assertEqual(self.recorded(), self.history)

    def test_taking_a_payment_earns_no_commission(self):
        record_payment(
            member=self.member, plan=self.plan, amount=Decimal("1000"), method=PaymentMethod.UPI
        )
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/billing/checkout/", {"member": self.member.pk, "plan": self.plan.pk}, format="json"
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(self.recorded(), self.history)

    def test_the_old_accrual_hooks_change_nothing(self):
        self.assertIsNone(accrue_for_payment(self.old_payment))
        self.old_payment.status = PaymentStatus.REFUNDED
        self.old_payment.save(update_fields=["status"])
        self.assertIsNone(accrue_for_payment(self.old_payment))
        self.assertIsNone(void_for_payment(self.old_payment))
        self.assertEqual(self.recorded(), self.history)

    def test_no_report_shows_a_commission_figure(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get("/api/reports/pt-performance/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.data["trainers"])
        for row in resp.data["trainers"]:
            self.assertNotIn("commission", row)
        self.assertNotIn(b"commission", resp.content.lower())

    def test_the_django_admin_shows_history_but_cannot_change_it(self):
        superuser = User.objects.create_superuser("root", "root@example.com", "pass12345")
        request = RequestFactory().get("/admin/")
        request.user = superuser
        for model in (CommissionRule, CommissionEntry, Payout):
            model_admin = admin.site._registry[model]
            with self.subTest(model=model.__name__):
                self.assertTrue(model_admin.has_view_permission(request))
                self.assertFalse(model_admin.has_add_permission(request))
                self.assertFalse(model_admin.has_change_permission(request))
                self.assertFalse(model_admin.has_delete_permission(request))
