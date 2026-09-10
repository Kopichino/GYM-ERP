from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from accounts.models import Role

from . import qr
from .models import CheckInMethod, CheckInOut

User = get_user_model()


class CheckInOutTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="member", email="m@example.com", password="pass12345")
        self.other = User.objects.create_user(username="other", email="o@example.com", password="pass12345")
        self.client.force_authenticate(self.user)

    def test_check_in_then_check_out(self):
        resp = self.client.post("/api/attendance/check_in/")
        self.assertEqual(resp.status_code, 201)
        self.assertIsNone(resp.data["check_out_time"])

        resp = self.client.post("/api/attendance/check_out/")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(resp.data["check_out_time"])

    def test_double_check_in_rejected(self):
        self.client.post("/api/attendance/check_in/")
        resp = self.client.post("/api/attendance/check_in/")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(CheckInOut.objects.filter(user=self.user, check_out_time__isnull=True).count(), 1)

    def test_check_out_without_open_record_rejected(self):
        resp = self.client.post("/api/attendance/check_out/")
        self.assertEqual(resp.status_code, 400)

    def test_current_is_204_when_not_checked_in(self):
        resp = self.client.get("/api/attendance/current/")
        self.assertEqual(resp.status_code, 204)

    def test_member_cannot_see_another_members_history(self):
        CheckInOut.objects.create(user=self.other)
        resp = self.client.get("/api/attendance/")
        ids = [row["id"] for row in resp.data["results"]]
        self.assertNotIn(CheckInOut.objects.get(user=self.other).id, ids)

    def test_two_users_can_each_have_one_open_checkin(self):
        self.client.post("/api/attendance/check_in/")
        self.client.force_authenticate(self.other)
        resp = self.client.post("/api/attendance/check_in/")
        self.assertEqual(resp.status_code, 201)


class QrCheckInTests(TenantAPIMixin, APITestCase):
    """The rotating front-desk code. Nothing is stored, so these tests move the
    clock rather than inspecting a table."""

    def setUp(self):
        self.member = User.objects.create_user(
            username="qrmember", email="qr@example.com", password="pass12345"
        )
        self.admin = User.objects.create_user(
            username="qradmin", email="qra@example.com", password="pass12345", role=Role.ADMIN
        )

    def test_kiosk_code_is_admin_only(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get("/api/attendance/qr_token/").status_code, 403)

        self.client.force_authenticate(self.admin)
        resp = self.client.get("/api/attendance/qr_token/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["token"])
        self.assertEqual(resp.data["rotate_seconds"], qr.WINDOW_SECONDS)

    def test_scan_checks_in_then_out(self):
        token, _ = qr.current_token()
        self.client.force_authenticate(self.member)

        resp = self.client.post("/api/attendance/qr-scan/", {"token": token})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["action"], "in")
        self.assertEqual(resp.data["record"]["method"], CheckInMethod.QR)

        resp = self.client.post("/api/attendance/qr-scan/", {"token": token})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["action"], "out")
        # Still exactly one visit -- the second scan closed the first, it did
        # not open a second.
        self.assertEqual(CheckInOut.objects.filter(user=self.member).count(), 1)

    def test_wrong_code_is_rejected(self):
        self.client.force_authenticate(self.member)
        resp = self.client.post("/api/attendance/qr-scan/", {"token": "not-a-real-code"})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(CheckInOut.objects.filter(user=self.member).exists())

    def test_stale_code_is_rejected(self):
        """A photographed code stops working once its window has rolled past."""
        stale, _ = qr.current_token()
        later = timezone.now() + timedelta(seconds=qr.WINDOW_SECONDS * (qr.GRACE_WINDOWS + 2))
        self.assertFalse(qr.is_valid(stale, now=later))

    def test_previous_window_still_accepted(self):
        """Scanning at :59 and posting at :01 must not fail."""
        token, _ = qr.current_token()
        just_after = timezone.now() + timedelta(seconds=qr.WINDOW_SECONDS)
        self.assertTrue(qr.is_valid(token, now=just_after))

    def test_scan_requires_a_logged_in_member(self):
        resp = self.client.post("/api/attendance/qr-scan/", {"token": qr.current_token()[0]})
        self.assertEqual(resp.status_code, 401)
