from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import MemberProfile

User = get_user_model()


class SignupTests(APITestCase):
    def test_signup_creates_user_and_profile(self):
        resp = self.client.post(
            "/api/auth/signup/",
            {"username": "newmember", "email": "n@example.com", "password": "StrongPass123!"},
        )
        self.assertEqual(resp.status_code, 201)
        user = User.objects.get(username="newmember")
        self.assertTrue(user.check_password("StrongPass123!"))
        self.assertTrue(MemberProfile.objects.filter(user=user).exists())

    def test_signup_rejects_weak_password(self):
        resp = self.client.post(
            "/api/auth/signup/",
            {"username": "weakpw", "email": "w@example.com", "password": "123"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(User.objects.filter(username="weakpw").exists())


class LoginRefreshTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="member", email="m@example.com", password="pass12345")

    def test_login_sets_httponly_refresh_cookie_not_in_body(self):
        resp = self.client.post("/api/auth/login/", {"username": "member", "password": "pass12345"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)
        self.assertNotIn("refresh", resp.data)
        self.assertIn("refresh_token", resp.cookies)
        self.assertTrue(resp.cookies["refresh_token"]["httponly"])

    def test_refresh_without_cookie_rejected(self):
        resp = self.client.post("/api/auth/refresh/")
        self.assertEqual(resp.status_code, 401)


class AdminMemberEndpointsTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="admin", email="a@example.com", password="pass12345", is_staff=True)
        self.member = User.objects.create_user(username="member", email="m@example.com", password="pass12345")

    def test_member_list_requires_staff(self):
        self.client.force_authenticate(self.member)
        resp = self.client.get("/api/auth/admin/members/")
        self.assertEqual(resp.status_code, 403)

    def test_staff_can_list_and_export_members(self):
        self.client.force_authenticate(self.staff)
        resp = self.client.get("/api/auth/admin/members/")
        self.assertEqual(resp.status_code, 200)
        usernames = [m["username"] for m in resp.data["results"]]
        self.assertIn("member", usernames)
        self.assertNotIn("admin", usernames)  # staff excluded from the member list

        resp = self.client.get("/api/auth/admin/members/export/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
