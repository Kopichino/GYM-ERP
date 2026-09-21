"""Expenses are admin-only, and the P&L depends on the totals here.

Two things get covered: that nobody but an admin can reach any of it -- what
the gym spends is not a member's or a trainer's business -- and that the
summary adds up to the same figure the ledger holds, since reports subtracts
this from revenue rather than storing a margin anywhere.
"""

import io
from datetime import date, timedelta
from decimal import Decimal

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from accounts.models import MemberProfile, Role

from .models import Expense, ExpenseCategory

User = get_user_model()


def make_user(username, role=Role.MEMBER):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    if role == Role.MEMBER:
        MemberProfile.objects.get_or_create(user=user)
    user.refresh_from_db()
    return user


class ExpenseAccessTests(TenantAPIMixin, APITestCase):
    """Every route on the app, against every role that is not an admin."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user("exp_admin", role=Role.ADMIN)
        cls.trainer = make_user("exp_trainer", role=Role.TRAINER)
        cls.member = make_user("exp_member")
        cls.category = ExpenseCategory.objects.create(name="Rent")
        cls.expense = Expense.objects.create(
            category=cls.category, amount=Decimal("25000.00"), vendor="Landlord"
        )

    def _routes(self):
        return [
            ("get", "/api/expenses/"),
            ("get", f"/api/expenses/{self.expense.id}/"),
            ("get", "/api/expenses/summary/"),
            ("get", "/api/expenses/categories/"),
            ("get", f"/api/expenses/categories/{self.category.id}/"),
        ]

    def test_a_member_is_refused_everywhere(self):
        self.client.force_authenticate(self.member)
        for method, url in self._routes():
            with self.subTest(url=url):
                self.assertEqual(getattr(self.client, method)(url).status_code, 403)

    def test_a_trainer_is_refused_everywhere(self):
        # A trainer sees their own earnings, not the gym's cost base.
        self.client.force_authenticate(self.trainer)
        for method, url in self._routes():
            with self.subTest(url=url):
                self.assertEqual(getattr(self.client, method)(url).status_code, 403)

    def test_an_anonymous_caller_is_refused(self):
        for method, url in self._routes():
            with self.subTest(url=url):
                self.assertIn(getattr(self.client, method)(url).status_code, (401, 403))

    def test_a_member_cannot_write_either(self):
        self.client.force_authenticate(self.member)
        payload = {"category": self.category.id, "amount": "100.00"}
        self.assertEqual(self.client.post("/api/expenses/", payload).status_code, 403)
        self.assertEqual(
            self.client.patch(f"/api/expenses/{self.expense.id}/", {"vendor": "x"}).status_code,
            403,
        )
        self.assertEqual(
            self.client.delete(f"/api/expenses/{self.expense.id}/").status_code, 403
        )
        self.assertEqual(
            self.client.post("/api/expenses/categories/", {"name": "Sneaky"}).status_code, 403
        )

    def test_a_refused_write_changes_nothing(self):
        self.client.force_authenticate(self.trainer)
        self.client.delete(f"/api/expenses/{self.expense.id}/")
        self.client.post("/api/expenses/categories/", {"name": "Sneaky"})
        self.assertTrue(Expense.objects.filter(pk=self.expense.pk).exists())
        self.assertFalse(ExpenseCategory.objects.filter(name="Sneaky").exists())

    def test_an_admin_gets_through(self):
        self.client.force_authenticate(self.admin)
        for method, url in self._routes():
            with self.subTest(url=url):
                self.assertEqual(getattr(self.client, method)(url).status_code, 200)


class ExpenseRecordingTests(TenantAPIMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user("rec_admin", role=Role.ADMIN)
        cls.category = ExpenseCategory.objects.create(name="Equipment")

    def setUp(self):
        self.client.force_authenticate(self.admin)

    def test_the_recorder_is_taken_from_the_token_not_the_body(self):
        # `recorded_by` is read-only, so an admin cannot file spending under
        # someone else's name, deliberately or by accident.
        other = make_user("rec_other", role=Role.ADMIN)
        resp = self.client.post(
            "/api/expenses/",
            {"category": self.category.id, "amount": "500.00", "recorded_by": other.id},
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Expense.objects.get(pk=resp.data["id"]).recorded_by, self.admin)

    def test_a_category_in_use_cannot_be_deleted(self):
        # PROTECT on the FK: deleting "Rent" would orphan every rent payment
        # and silently drop them out of the P&L. The refusal reaches the admin
        # as a readable 400, not a ProtectedError escaping as a 500.
        expense = Expense.objects.create(category=self.category, amount=Decimal("100"))
        resp = self.client.delete(f"/api/expenses/categories/{self.category.id}/")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("detail", resp.data)
        self.assertTrue(ExpenseCategory.objects.filter(pk=self.category.pk).exists())
        self.assertTrue(Expense.objects.filter(pk=expense.pk, category=self.category).exists())

    def test_an_unused_category_can_be_deleted(self):
        spare = ExpenseCategory.objects.create(name="Retired line item")
        resp = self.client.delete(f"/api/expenses/categories/{spare.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(ExpenseCategory.objects.filter(pk=spare.pk).exists())

    def test_the_category_count_reflects_its_expenses(self):
        Expense.objects.create(category=self.category, amount=Decimal("100"))
        Expense.objects.create(category=self.category, amount=Decimal("200"))
        row = self.client.get("/api/expenses/categories/").data["results"][0]
        self.assertEqual(row["expense_count"], 2)


class ExpenseFilterTests(TenantAPIMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user("filt_admin", role=Role.ADMIN)
        cls.rent = ExpenseCategory.objects.create(name="Rent")
        cls.kit = ExpenseCategory.objects.create(name="Equipment")
        cls.today = date(2026, 3, 15)
        Expense.objects.create(category=cls.rent, amount=Decimal("25000"), spent_on=cls.today)
        Expense.objects.create(
            category=cls.kit, amount=Decimal("4000"), spent_on=cls.today - timedelta(days=40)
        )
        Expense.objects.create(
            category=cls.kit, amount=Decimal("1000"), spent_on=cls.today - timedelta(days=5)
        )

    def setUp(self):
        self.client.force_authenticate(self.admin)

    def test_filtering_by_category_narrows_the_list(self):
        resp = self.client.get(f"/api/expenses/?category={self.kit.id}")
        self.assertEqual(resp.data["count"], 2)

    def test_a_date_window_is_inclusive_at_both_ends(self):
        start = (self.today - timedelta(days=5)).isoformat()
        resp = self.client.get(f"/api/expenses/?from={start}&to={self.today.isoformat()}")
        self.assertEqual(resp.data["count"], 2)

    def test_the_summary_totals_the_filtered_window_only(self):
        start = (self.today - timedelta(days=5)).isoformat()
        data = self.client.get(
            f"/api/expenses/summary/?from={start}&to={self.today.isoformat()}"
        ).data
        # 25000 rent + 1000 kit; the 40-day-old 4000 is outside the window.
        self.assertEqual(Decimal(str(data["total"])), Decimal("26000"))
        self.assertEqual(data["count"], 2)

    def test_the_summary_splits_by_category_worst_first(self):
        data = self.client.get("/api/expenses/summary/").data
        self.assertEqual(
            [(row["category"], Decimal(str(row["total"]))) for row in data["by_category"]],
            [("Rent", Decimal("25000")), ("Equipment", Decimal("5000"))],
        )

    def test_the_summary_adds_up_to_the_ledger(self):
        # Computed independently here rather than trusting the endpoint's own
        # arithmetic: reports subtracts this figure from revenue.
        expected = sum(e.amount for e in Expense.objects.all())
        data = self.client.get("/api/expenses/summary/").data
        self.assertEqual(Decimal(str(data["total"])), expected)
        self.assertEqual(
            sum(Decimal(str(row["total"])) for row in data["by_category"]), expected
        )

    def test_an_empty_window_is_an_honest_zero(self):
        data = self.client.get("/api/expenses/summary/?from=2030-01-01&to=2030-01-02").data
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["by_category"], [])

    # -- the window itself, read the way every report reads one

    def test_a_malformed_date_is_a_400_on_that_parameter_not_a_500(self):
        for path in ("/api/expenses/", "/api/expenses/summary/"):
            for params, field in (("from=2026-13-45", "from"), ("to=not-a-date", "to")):
                with self.subTest(path=path, params=params):
                    resp = self.client.get(f"{path}?{params}")
                    self.assertEqual(resp.status_code, 400, resp.content)
                    self.assertIn(field, resp.data)

    def test_a_to_date_before_the_from_date_is_refused_not_answered_with_nothing(self):
        backwards = f"from={self.today.isoformat()}&to={(self.today - timedelta(days=1)).isoformat()}"
        for path in ("/api/expenses/", "/api/expenses/summary/"):
            with self.subTest(path=path):
                resp = self.client.get(f"{path}?{backwards}")
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertEqual(
                    [str(m) for m in resp.data["to"]], ["The end date is before the start date."]
                )

    def test_a_same_day_window_still_works(self):
        day = self.today.isoformat()
        resp = self.client.get(f"/api/expenses/summary/?from={day}&to={day}")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["count"], 1)


class ReceiptUploadTests(TenantAPIMixin, APITestCase):
    """`receipt` is a bare FileField, so nothing about it is checked for free.

    The ImageFields elsewhere in the project (profile photo, gym logo, badge
    art) are verified through Pillow by Django itself, so a renamed executable
    is refused there without any code of ours. A FileField gets none of that --
    whatever is posted is written and then served back from Cloudinary.
    """

    def setUp(self):
        self.admin = make_user("receipt_admin", role=Role.ADMIN)
        self.category = ExpenseCategory.objects.create(name="Utilities")
        self.client.force_authenticate(self.admin)

    def _post(self, upload):
        return self.client.post(
            "/api/expenses/",
            {"category": self.category.id, "amount": "500.00", "receipt": upload},
            format="multipart",
        )

    def test_a_pdf_receipt_is_accepted(self):
        pdf = SimpleUploadedFile("bill.pdf", b"%PDF-1.4 fake", content_type="application/pdf")
        self.assertEqual(self._post(pdf).status_code, 201)

    def test_a_photo_of_a_bill_is_accepted(self):
        # A real (tiny) JPEG. JPEG magic bytes in front of anything else are the
        # classic polyglot, so a receipt photo has to decode as an image.
        buffer = io.BytesIO()
        Image.new("RGB", (4, 4), "white").save(buffer, "JPEG")
        photo = SimpleUploadedFile("bill.jpg", buffer.getvalue(), content_type="image/jpeg")
        self.assertEqual(self._post(photo).status_code, 201)

    def test_an_executable_is_refused(self):
        exe = SimpleUploadedFile(
            "invoice.exe", b"MZ\x90\x00", content_type="application/x-msdownload"
        )
        resp = self._post(exe)
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Expense.objects.exists())

    def test_a_script_disguised_by_extension_is_refused(self):
        sh = SimpleUploadedFile("receipt.sh", b"#!/bin/sh\nrm -rf /", content_type="text/x-sh")
        self.assertEqual(self._post(sh).status_code, 400)

    def test_an_html_file_is_refused(self):
        # Served back from storage, an HTML file is a stored-XSS delivery
        # vehicle on whatever origin the media is hosted from.
        html = SimpleUploadedFile(
            "receipt.html", b"<script>alert(1)</script>", content_type="text/html"
        )
        self.assertEqual(self._post(html).status_code, 400)

    def test_an_oversized_file_is_refused(self):
        big = SimpleUploadedFile(
            "huge.pdf", b"x" * (11 * 1024 * 1024), content_type="application/pdf"
        )
        resp = self._post(big)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("limit", str(resp.data).lower())

    def test_an_expense_without_a_receipt_is_still_fine(self):
        resp = self.client.post(
            "/api/expenses/", {"category": self.category.id, "amount": "500.00"}
        )
        self.assertEqual(resp.status_code, 201)
