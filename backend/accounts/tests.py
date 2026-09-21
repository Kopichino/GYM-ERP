from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from .models import MemberProfile, Role

User = get_user_model()


class SignupTests(TenantAPIMixin, APITestCase):
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


class LoginRefreshTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="member", email="m@example.com", password="pass12345")

    # Two-step sign-in off, so the password alone opens a session: this is about
    # how a session is delivered. tests_mfa covers the same for the two-step path.
    @override_settings(MFA_REQUIRED=False)
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


class AdminMemberEndpointsTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin", email="a@example.com", password="pass12345", role=Role.ADMIN
        )
        self.trainer = User.objects.create_user(
            username="trainer", email="t@example.com", password="pass12345", role=Role.TRAINER
        )
        self.member = User.objects.create_user(
            username="member", email="m@example.com", password="pass12345"
        )
        # Made in setUp, after the mixin has already enrolled everyone, so none
        # of these is anybody at this gym until enrolled here. The member list
        # is scoped to members of this gym, and an unenrolled one is correctly
        # not on it.
        for user in (self.admin, self.trainer, self.member):
            self.member_for(user, user.role)

    def test_member_list_requires_admin(self):
        for user in (self.member, self.trainer):
            self.client.force_authenticate(user)
            resp = self.client.get("/api/auth/admin/members/")
            self.assertEqual(resp.status_code, 403)

    def test_admin_can_list_and_export_members(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get("/api/auth/admin/members/")
        self.assertEqual(resp.status_code, 200)
        usernames = [m["username"] for m in resp.data["results"]]
        self.assertIn("member", usernames)
        # Only role=member belongs on the member list.
        self.assertNotIn("admin", usernames)
        self.assertNotIn("trainer", usernames)

        resp = self.client.get("/api/auth/admin/members/export/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


class RoleTests(TenantAPIMixin, APITestCase):
    def test_is_staff_is_platform_staff_not_gym_admin(self):
        """`is_staff` stopped mirroring role==ADMIN, deliberately.

        It gates Django's own /admin/, which is not tenant-scoped and shows
        every gym's data at once. Mirroring it from a gym-level role would have
        handed each gym owner a console over all the others the moment a second
        gym existed.
        """
        admin = User.objects.create_user(
            username="a", email="a@example.com", password="pass12345", role=Role.ADMIN
        )
        trainer = User.objects.create_user(
            username="t", email="t@example.com", password="pass12345", role=Role.TRAINER
        )
        member = User.objects.create_user(username="m", email="m@example.com", password="pass12345")

        for user in (admin, trainer, member):
            self.assertFalse(user.is_staff, user.username)

    def test_a_superuser_still_gets_it(self):
        """Otherwise createsuperuser produces an account that cannot reach
        the very console it was made for."""
        root = User.objects.create_superuser(
            username="root", email="root@example.com", password="pass12345"
        )
        self.assertTrue(root.is_staff)

    def test_signup_always_creates_a_member(self):
        self.client.post(
            "/api/auth/signup/",
            {
                "username": "sneaky",
                "email": "s@example.com",
                "password": "StrongPass123!",
                "role": "admin",
            },
        )
        user = User.objects.get(username="sneaky")
        self.assertEqual(user.role, Role.MEMBER)
        self.assertFalse(user.is_staff)
