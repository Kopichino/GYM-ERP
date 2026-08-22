from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import CheckInOut

User = get_user_model()


class CheckInOutTests(APITestCase):
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
