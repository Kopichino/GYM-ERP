from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin, enrol

from accounts.models import MemberProfile, Role
from billing.models import Plan
from billing.services import record_payment

from .models import Invoice, InvoiceCounter, financial_year_for
from .services import issue_invoice, split_tax

User = get_user_model()


def make_user(username, role=Role.MEMBER):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    MemberProfile.objects.get_or_create(user=user)
    enrol(user)
    return user


class FinancialYearTests(TenantAPIMixin, APITestCase):
    def test_april_starts_a_new_financial_year(self):
        self.assertEqual(financial_year_for(date(2026, 4, 1)), "2026-27")
        self.assertEqual(financial_year_for(date(2027, 3, 31)), "2026-27")
        # February belongs to the year that began the previous April.
        self.assertEqual(financial_year_for(date(2026, 2, 11)), "2025-26")


class TaxSplitTests(TenantAPIMixin, APITestCase):
    def test_tax_is_backed_out_of_a_tax_inclusive_total(self):
        taxable, cgst, sgst, igst = split_tax(Decimal("1180"), Decimal("18"), interstate=False)
        self.assertEqual(taxable, Decimal("1000.00"))
        self.assertEqual(cgst + sgst, Decimal("180.00"))
        self.assertEqual(igst, Decimal("0.00"))

    def test_intrastate_splits_evenly_and_interstate_uses_igst(self):
        _, cgst, sgst, igst = split_tax(Decimal("1180"), Decimal("18"), interstate=False)
        self.assertEqual(cgst, sgst)

        taxable, cgst, sgst, igst = split_tax(Decimal("1180"), Decimal("18"), interstate=True)
        self.assertEqual(igst, Decimal("180.00"))
        self.assertEqual(cgst, Decimal("0.00"))
        self.assertEqual(sgst, Decimal("0.00"))

    def test_the_parts_always_sum_to_the_total(self):
        """Rounding must never leave the invoice a paisa short."""
        for total in ("999.99", "1500", "4000", "8333.33", "14000"):
            taxable, cgst, sgst, igst = split_tax(Decimal(total), Decimal("18"), False)
            self.assertEqual(taxable + cgst + sgst + igst, Decimal(total))


@override_settings(GYM_GSTIN="29ABCDE1234F1Z5", GYM_STATE="Karnataka", GST_RATE="18")
class InvoiceIssueTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = make_user("admin", Role.ADMIN)
        self.member = make_user("member")
        self.plan = Plan.objects.create(name="Monthly", price=Decimal("1180"), duration_days=30)

    def _pay(self, amount="1180"):
        return record_payment(
            member=self.member, plan=self.plan, amount=Decimal(amount), method="cash"
        )

    def test_issuing_an_invoice_snapshots_the_seller_details(self):
        invoice = issue_invoice(self._pay())
        self.assertEqual(invoice.seller_gstin, "29ABCDE1234F1Z5")
        self.assertEqual(invoice.place_of_supply, "Karnataka")
        self.assertEqual(invoice.total, Decimal("1180.00"))
        self.assertEqual(invoice.taxable_value, Decimal("1000.00"))

    def test_numbers_are_sequential_within_a_financial_year(self):
        first = issue_invoice(self._pay())
        second = issue_invoice(record_payment(
            member=make_user("second"), plan=self.plan, amount=Decimal("1180"), method="cash"
        ))
        self.assertEqual(first.sequence, 1)
        self.assertEqual(second.sequence, 2)
        self.assertTrue(second.number.endswith("00002"))
        self.assertEqual(InvoiceCounter.objects.get().last_number, 2)

    def test_issuing_twice_for_one_payment_does_not_burn_a_number(self):
        """A retried checkout must not consume a second statutory number."""
        payment = self._pay()
        first = issue_invoice(payment)
        again = issue_invoice(payment)

        self.assertEqual(first.pk, again.pk)
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(InvoiceCounter.objects.get().last_number, 1)

    def test_a_sale_outside_the_gyms_state_is_charged_igst(self):
        invoice = issue_invoice(self._pay(), place_of_supply="Maharashtra")
        self.assertTrue(invoice.is_interstate)
        self.assertEqual(invoice.igst, Decimal("180.00"))
        self.assertEqual(invoice.cgst, Decimal("0.00"))

    def test_checkout_issues_an_invoice_automatically(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/billing/checkout/", {"member": self.member.pk, "plan": self.plan.pk}
        )
        self.assertEqual(resp.status_code, 201)
        self.assertIn("invoice", resp.data)
        self.assertTrue(resp.data["invoice"]["number"].startswith("INV/"))


class InvoiceAccessTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = make_user("admin", Role.ADMIN)
        self.member = make_user("member")
        self.other = make_user("other")
        self.plan = Plan.objects.create(name="Monthly", price=Decimal("1180"), duration_days=30)
        self.invoice = issue_invoice(
            record_payment(member=self.member, plan=self.plan, amount=Decimal("1180"), method="cash")
        )

    def test_a_member_sees_only_their_own_invoices(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get("/api/invoices/").data["count"], 0)

        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get("/api/invoices/").data["count"], 1)

    def test_admin_sees_every_invoice(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/invoices/").data["count"], 1)

    def test_invoices_cannot_be_edited_or_deleted(self):
        self.client.force_authenticate(self.admin)
        url = f"/api/invoices/{self.invoice.pk}/"
        self.assertEqual(self.client.patch(url, {"total": "1"}).status_code, 405)
        self.assertEqual(self.client.delete(url).status_code, 405)

    def test_the_pdf_renders(self):
        self.client.force_authenticate(self.member)
        resp = self.client.get(f"/api/invoices/{self.invoice.pk}/pdf/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_a_member_cannot_download_someone_elses_pdf(self):
        self.client.force_authenticate(self.other)
        resp = self.client.get(f"/api/invoices/{self.invoice.pk}/pdf/")
        self.assertEqual(resp.status_code, 404)


class GaplessNumberingTests(TenantAPIMixin, APITestCase):
    """The statutory sequence must have no holes in it.

    Allocation and insert are one transaction, so a number handed out for an
    invoice that then fails to write is given back rather than burned. These
    drive the failure sequentially; a genuinely concurrent version needs a
    backend that honours row locks -- see tests_concurrency.py.
    """

    def setUp(self):
        self.admin = make_user("gap_admin", Role.ADMIN)
        self.plan = Plan.objects.create(name="Monthly", price=Decimal("1180"), duration_days=30)

    def _pay(self, who):
        return record_payment(
            member=who, plan=self.plan, amount=Decimal("1180"), method="cash"
        )

    def _counter(self, on):
        row = InvoiceCounter.objects.filter(financial_year=financial_year_for(on)).first()
        return row.last_number if row else 0

    def test_a_failed_insert_gives_the_number_back(self):
        first = issue_invoice(self._pay(make_user("gap_one")))
        self.assertEqual(first.sequence, 1)

        payment = self._pay(make_user("gap_two"))
        before = self._counter(payment.paid_date)
        with mock.patch.object(
            Invoice.objects, "create", side_effect=IntegrityError("disk full")
        ):
            with self.assertRaises(IntegrityError):
                issue_invoice(payment)

        # The counter is back where it started, not one ahead.
        self.assertEqual(self._counter(payment.paid_date), before)

        third = issue_invoice(self._pay(make_user("gap_three")))
        self.assertEqual(third.sequence, 2)

    def test_the_sequence_has_no_holes_after_a_failure(self):
        for name in ("hole_a", "hole_b"):
            issue_invoice(self._pay(make_user(name)))

        payment = self._pay(make_user("hole_fails"))
        with mock.patch.object(
            Invoice.objects, "create", side_effect=IntegrityError("nope")
        ):
            with self.assertRaises(IntegrityError):
                issue_invoice(payment)

        issue_invoice(self._pay(make_user("hole_c")))

        fy = financial_year_for(timezone.localdate())
        numbers = sorted(
            Invoice.objects.filter(financial_year=fy).values_list("sequence", flat=True)
        )
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)))

    def test_no_invoice_row_survives_a_failed_issue(self):
        payment = self._pay(make_user("gap_orphan"))
        with mock.patch.object(
            Invoice.objects, "create", side_effect=IntegrityError("nope")
        ):
            with self.assertRaises(IntegrityError):
                issue_invoice(payment)
        self.assertFalse(Invoice.objects.filter(payment=payment).exists())

    def test_a_racing_duplicate_returns_the_winners_invoice(self):
        """Two webhook retries that both pass the exists() check at the top.

        The loser's insert trips the payment one-to-one. It must hand back the
        invoice that won rather than raising, and must not leave a hole where
        its own number would have been.
        """
        payment = self._pay(make_user("gap_race"))
        winner = issue_invoice(payment)

        # Force the second caller past the idempotency check, as a concurrent
        # one would get past it for real.
        with mock.patch.object(Invoice.objects, "filter", side_effect=[
            Invoice.objects.none(),                       # the exists() check
            Invoice.objects.filter(payment=payment),      # the recovery lookup
        ]):
            again = issue_invoice(payment)

        self.assertEqual(again.pk, winner.pk)
        self.assertEqual(Invoice.objects.filter(payment=payment).count(), 1)
        self.assertEqual(self._counter(payment.paid_date), winner.sequence)


class IssueEndpointAccessTests(TenantAPIMixin, APITestCase):
    """`/issue/` mints a statutory document, so it is admin-only."""

    def setUp(self):
        self.admin = make_user("iss_admin", Role.ADMIN)
        self.trainer = make_user("iss_trainer", Role.TRAINER)
        self.member = make_user("iss_member")
        self.plan = Plan.objects.create(name="Monthly", price=Decimal("1180"), duration_days=30)
        self.payment = record_payment(
            member=self.member, plan=self.plan, amount=Decimal("1180"), method="cash"
        )
        Invoice.objects.all().delete()
        InvoiceCounter.objects.all().delete()

    def test_a_member_cannot_issue_one(self):
        self.client.force_authenticate(self.member)
        resp = self.client.post("/api/invoices/issue/", {"payment": self.payment.id})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Invoice.objects.exists())

    def test_a_trainer_cannot_issue_one(self):
        self.client.force_authenticate(self.trainer)
        resp = self.client.post("/api/invoices/issue/", {"payment": self.payment.id})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Invoice.objects.exists())

    def test_an_anonymous_caller_cannot_issue_one(self):
        resp = self.client.post("/api/invoices/issue/", {"payment": self.payment.id})
        self.assertIn(resp.status_code, (401, 403))
        self.assertFalse(Invoice.objects.exists())

    def test_a_refused_attempt_does_not_burn_a_number(self):
        self.client.force_authenticate(self.member)
        self.client.post("/api/invoices/issue/", {"payment": self.payment.id})
        self.client.force_authenticate(self.admin)
        resp = self.client.post("/api/invoices/issue/", {"payment": self.payment.id})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["sequence"], 1)

    def test_an_admin_can(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post("/api/invoices/issue/", {"payment": self.payment.id})
        self.assertEqual(resp.status_code, 201)

    def test_a_trainer_sees_no_invoices_at_all(self):
        # A trainer has no member profile, so the member branch of the
        # queryset filters to nothing rather than leaking the whole book.
        issue_invoice(self.payment)
        self.client.force_authenticate(self.trainer)
        self.assertEqual(self.client.get("/api/invoices/").data["count"], 0)

    def test_an_unknown_payment_is_a_404(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post("/api/invoices/issue/", {"payment": 999999})
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(Invoice.objects.exists())
