"""Errors that say too much, and configuration that is weaker than it looks."""

import io
import os
import subprocess
import sys

import openpyxl
from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Role
from crm.models import Enquiry

from .testing import OneGymTestCase

#: What a database error looks like when it reaches the client.
LEAKS = (
    b"IntegrityError",
    b"UNIQUE constraint",
    b"duplicate key",
    b"Traceback",
    b"_per_organisation",
)


class DuplicateValueTests(OneGymTestCase):
    """Each of these was a 500 carrying the database's own error: the audit hit
    all four from the admin screens."""

    def setUp(self):
        super().setUp()
        self.admin = self.person("owner", Role.ADMIN)
        self.client.force_authenticate(self.admin)

    def second_of(self, path, payload):
        first = self.client.post(path, payload, format="json")
        self.assertEqual(first.status_code, 201, first.content)
        return self.client.post(path, payload, format="json")

    def assert_clean_refusal(self, resp, field):
        """A 400 naming the field to change, with nothing from the database in it."""
        self.assertEqual(resp.status_code, 400, resp.content[:300])
        self.assertIn(field, resp.data)
        for marker in LEAKS:
            self.assertNotIn(marker, resp.content)

    def test_a_second_plan_with_the_same_name(self):
        self.assert_clean_refusal(
            self.second_of(
                "/api/billing/plans/", {"name": "Monthly", "price": "999.00", "duration_days": 30}
            ),
            "name",
        )

    def test_a_second_offer_with_the_same_code(self):
        self.assert_clean_refusal(
            self.second_of(
                "/api/billing/discounts/",
                {"code": "SAVE10", "discount_type": "percent", "value": "10"},
            ),
            "code",
        )

    def test_a_second_expense_category_with_the_same_name(self):
        self.assert_clean_refusal(
            self.second_of("/api/expenses/categories/", {"name": "Rent"}), "name"
        )

    def test_a_second_badge_with_the_same_code(self):
        self.assert_clean_refusal(
            self.second_of(
                "/api/gamification/badges/",
                {"code": "ten-visits", "name": "Ten visits", "criterion": "visits", "threshold": 10},
            ),
            "code",
        )


class ForwardedForTests(APITestCase):
    """DRF believed the client's own X-Forwarded-For unless told how many proxies
    sit in front of the app, so every forged address bought a fresh per-IP
    allowance at the login endpoint."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_a_forged_forwarded_for_header_does_not_buy_a_fresh_allowance(self):
        statuses = [
            self.client.post(
                "/api/auth/login/",
                {"username": f"sprayed{n}", "password": "wrong-password"},
                REMOTE_ADDR="198.51.100.7",
                HTTP_X_FORWARDED_FOR=f"10.{n}.0.1",
            ).status_code
            for n in range(15)
        ]
        self.assertIn(429, statuses, "rotating a forged X-Forwarded-For defeated the per-IP limit")


class SpreadsheetFormulaTests(OneGymTestCase):
    """A name beginning with "=" was written into the Excel exports as a live
    formula. Member names are member-controlled and enquiry names come from the
    public website form, so anyone could plant one for the owner to open."""

    PAYLOAD = '=HYPERLINK("http://attacker.example/","Open invoice")'

    def setUp(self):
        super().setUp()
        self.admin = self.person("owner", Role.ADMIN)
        self.client.force_authenticate(self.admin)

    def assert_no_formulas(self, resp):
        self.assertEqual(resp.status_code, 200)
        sheet = openpyxl.load_workbook(io.BytesIO(resp.content)).active
        cells = [cell for row in sheet.iter_rows() for cell in row]
        self.assertTrue(any("HYPERLINK" in str(cell.value) for cell in cells), "payload missing")
        self.assertEqual([cell.coordinate for cell in cells if cell.data_type == "f"], [])

    def test_the_member_export_writes_a_formula_shaped_name_as_text(self):
        self.person("planted", first_name=self.PAYLOAD)
        self.assert_no_formulas(self.client.get("/api/auth/admin/members/export/"))

    def test_the_report_export_writes_a_formula_shaped_lead_as_text(self):
        Enquiry.objects.create(
            name=self.PAYLOAD, phone="9000000003", follow_up_on=timezone.localdate()
        )
        self.assert_no_formulas(
            self.client.post(
                "/api/reports/export/",
                {"source": "enquiries", "fields": ["name", "phone"]},
                format="json",
            )
        )


class ProductionSettingsTests(SimpleTestCase):
    """Settings are read once at import, so each case loads them fresh in a
    child process with the environment a production deploy would have."""

    def load(self, expression, **environment):
        env = {key: value for key, value in os.environ.items() if key != "DJANGO_ADMIN_ENABLED"}
        env.update({"DJANGO_SETTINGS_MODULE": "gymerp.settings", **environment})
        code = (
            "import django; django.setup(); "
            f"from django.conf import settings; print({expression})"
        )
        return subprocess.run(
            [sys.executable, "-c", code],
            cwd=settings.BASE_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )

    def test_production_refuses_to_start_on_the_placeholder_secret_key(self):
        """Every JWT and pending sign-in token is signed with this key; the
        placeholder is published in the repository."""
        for placeholder in ("django-insecure-dev-only-change-me", "change-me-to-a-long-random-string", ""):
            with self.subTest(placeholder=placeholder):
                result = self.load("'started'", DEBUG="False", SECRET_KEY=placeholder)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("SECRET_KEY", result.stderr)

    def test_production_starts_with_a_real_secret_key(self):
        result = self.load("'started'", DEBUG="False", SECRET_KEY="k7" * 32)
        self.assertEqual(result.returncode, 0, result.stderr[-800:])
        self.assertIn("started", result.stdout)

    def test_the_django_admin_is_off_in_production_unless_switched_on(self):
        """It is a password-only console over every gym's data: no second
        factor, no tenant scoping, and none of the sign-in back-off."""
        result = self.load("settings.DJANGO_ADMIN_ENABLED", DEBUG="False", SECRET_KEY="k7" * 32)
        self.assertEqual(result.returncode, 0, result.stderr[-800:])
        self.assertEqual(result.stdout.strip().splitlines()[-1], "False")
