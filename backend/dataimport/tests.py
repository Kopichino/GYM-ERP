from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from accounts.models import MembershipStatus, MemberProfile, Role
from instructors.models import Instructor

from .mapping import BILLING, MEMBER, TRAINER, detect_columns
from .services import to_date, to_decimal

User = get_user_model()


class ColumnDetectionTests(TenantAPIMixin, APITestCase):
    """Only GymMaster publishes its export headers, so detection is alias-based
    and has to survive the naming styles the other platforms use."""

    def test_gymmaster_headers(self):
        mapping = detect_columns(
            ["member_firstname", "member_surname", "email", "mobile", "dob", "joindate"], MEMBER
        )
        self.assertEqual(mapping["first_name"], "member_firstname")
        self.assertEqual(mapping["last_name"], "member_surname")
        self.assertEqual(mapping["phone"], "mobile")
        self.assertEqual(mapping["date_of_birth"], "dob")

    def test_spaced_title_case_headers(self):
        mapping = detect_columns(
            ["First Name", "Last Name", "Email Address", "Mobile Number", "Joining Date"], MEMBER
        )
        self.assertEqual(mapping["first_name"], "First Name")
        self.assertEqual(mapping["email"], "Email Address")
        self.assertEqual(mapping["join_date"], "Joining Date")

    def test_billing_and_trainer_headers(self):
        billing = detect_columns(
            ["Member Email", "Package Name", "Amount Paid", "Payment Mode", "Valid To"], BILLING
        )
        self.assertEqual(billing["amount"], "Amount Paid")
        self.assertEqual(billing["plan"], "Package Name")
        self.assertEqual(billing["period_end"], "Valid To")

        trainer = detect_columns(["Trainer Name", "Specialization", "Email"], TRAINER)
        self.assertEqual(trainer["name"], "Trainer Name")
        self.assertEqual(trainer["specialty"], "Specialization")

    def test_a_header_is_claimed_by_only_one_field(self):
        mapping = detect_columns(["Name", "Email"], MEMBER)
        self.assertEqual(len(set(mapping.values())), len(mapping))


class ValueParsingTests(TenantAPIMixin, APITestCase):
    def test_dates_in_mixed_formats(self):
        self.assertEqual(str(to_date("15/03/1995")), "1995-03-15")
        self.assertEqual(str(to_date("2024-06-01")), "2024-06-01")
        self.assertEqual(str(to_date("22.07.1988")), "1988-07-22")
        self.assertIsNone(to_date("not a date"))

    def test_amounts_with_currency_symbols(self):
        self.assertEqual(str(to_decimal("₹1,800.00")), "1800.00")
        self.assertEqual(str(to_decimal("$1,234.56")), "1234.56")
        self.assertIsNone(to_decimal("abc"))


class ImportEndpointTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin", email="a@example.com", password="pass12345", role=Role.ADMIN
        )
        self.member = User.objects.create_user(
            username="member", email="m@example.com", password="pass12345"
        )
        MemberProfile.objects.get_or_create(user=self.member)

    def _csv(self, text):
        return SimpleUploadedFile("import.csv", text.encode(), content_type="text/csv")

    MEMBERS_CSV = (
        "member_firstname,member_surname,email,mobile,joindate,status\n"
        "Arjun,Sharma,arjun@example.com,9876543210,01/06/2024,Active\n"
        "Priya,Nair,priya@example.com,9876500011,15/01/2023,Frozen\n"
    )

    def test_import_requires_admin(self):
        for user in (self.member, None):
            if user:
                self.client.force_authenticate(user)
            else:
                self.client.force_authenticate(None)
            resp = self.client.post(
                "/api/import/preview/", {"kind": "members", "file": self._csv(self.MEMBERS_CSV)}
            )
            self.assertIn(resp.status_code, (401, 403))

    def test_preview_writes_nothing(self):
        self.client.force_authenticate(self.admin)
        before = User.objects.count()
        resp = self.client.post(
            "/api/import/preview/", {"kind": "members", "file": self._csv(self.MEMBERS_CSV)}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["total_rows"], 2)
        self.assertEqual(resp.data["create_count"], 2)
        self.assertEqual(User.objects.count(), before)

    def test_commit_creates_members_with_parsed_values(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/import/commit/", {"kind": "members", "file": self._csv(self.MEMBERS_CSV)}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["created"], 2)

        arjun = User.objects.get(email="arjun@example.com")
        self.assertEqual(arjun.role, Role.MEMBER)
        self.assertEqual(arjun.first_name, "Arjun")
        self.assertEqual(str(arjun.profile.join_date), "2024-06-01")
        # Imported accounts can't be logged into until a password is set.
        self.assertFalse(arjun.has_usable_password())

        priya = User.objects.get(email="priya@example.com")
        self.assertEqual(priya.profile.membership_status, MembershipStatus.PAUSED)

    def test_reimport_updates_instead_of_duplicating(self):
        self.client.force_authenticate(self.admin)
        payload = {"kind": "members", "file": self._csv(self.MEMBERS_CSV)}
        self.client.post("/api/import/commit/", payload)
        resp = self.client.post(
            "/api/import/commit/", {"kind": "members", "file": self._csv(self.MEMBERS_CSV)}
        )
        self.assertEqual(resp.data["created"], 0)
        self.assertEqual(resp.data["updated"], 2)
        self.assertEqual(User.objects.filter(email="arjun@example.com").count(), 1)

    def test_trainer_import_creates_login_account(self):
        self.client.force_authenticate(self.admin)
        csv = "Trainer Name,Email,Specialization\nTara Coach,tara@example.com,Strength\n"
        resp = self.client.post("/api/import/commit/", {"kind": "trainers", "file": self._csv(csv)})
        self.assertEqual(resp.data["created"], 1)

        instructor = Instructor.objects.get(name="Tara Coach")
        self.assertIsNotNone(instructor.user)
        self.assertEqual(instructor.user.role, Role.TRAINER)
        self.assertFalse(instructor.user.is_staff)

    def test_billing_row_without_matching_member_is_skipped(self):
        self.client.force_authenticate(self.admin)
        csv = (
            "Member Email,Package Name,Amount Paid,Payment Mode,Payment Date\n"
            "nobody@example.com,Monthly,1500,Cash,01/01/2024\n"
        )
        resp = self.client.post("/api/import/commit/", {"kind": "billing", "file": self._csv(csv)})
        self.assertEqual(resp.data["created"], 0)
        self.assertEqual(resp.data["skipped"], 1)

    def test_unreadable_file_is_rejected_with_a_message(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/import/preview/",
            {"kind": "members", "file": SimpleUploadedFile("x.pdf", b"%PDF-1.4")},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Unsupported file type", resp.data["detail"])
