"""The admin member list and account management, confined to one gym."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase

from accounts.models import MemberProfile, Role
from core.testing import TenantAPIMixin

User = get_user_model()

STRONG = "Gym!Member-2026"


def make(username, role, password="pass12345"):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password=password, role=role
    )
    MemberProfile.objects.get_or_create(user=user)
    return user


class MemberPasswordTests(TenantAPIMixin, APITestCase):
    """An admin giving a member a password -- mostly for imported accounts."""

    def setUp(self):
        cache.clear()
        self.admin = make("boss", Role.ADMIN)
        self.member = make("imported_member", Role.MEMBER, password=None)
        # Authenticating enrols an account at this test's gym, which is what
        # makes `imported_member` a member here.
        self.client.force_authenticate(self.member)
        self.client.force_authenticate(self.admin)

    def test_the_list_says_who_cannot_log_in_yet(self):
        resp = self.client.get("/api/auth/admin/members/")
        row = next(r for r in resp.data["results"] if r["id"] == self.member.id)
        self.assertFalse(row["has_password"])

    def test_an_admin_sets_a_password_for_a_member_here(self):
        resp = self.client.post(
            f"/api/auth/admin/members/{self.member.id}/set-password/",
            {"password": STRONG},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.member.refresh_from_db()
        self.assertTrue(self.member.check_password(STRONG))

    def test_a_weak_password_is_refused(self):
        resp = self.client.post(
            f"/api/auth/admin/members/{self.member.id}/set-password/",
            {"password": "123"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("password", resp.data)


class MemberScopingTests(TenantAPIMixin, APITestCase):
    """`User` spans every gym, so these endpoints have to filter by membership.

    Filtering on `role` alone listed every member on the platform, and let an
    admin here edit, delete, or set the password of an account at another gym.
    """

    def setUp(self):
        cache.clear()
        self.admin = make("boss_scope", Role.ADMIN)
        # Never authenticated in this test, so never enrolled here: an account
        # that belongs to some other gym, as far as this one is concerned.
        self.stranger = make("elsewhere_member", Role.MEMBER)
        self.client.force_authenticate(self.admin)

    def test_a_member_of_another_gym_is_not_listed(self):
        resp = self.client.get("/api/auth/admin/members/")
        self.assertNotIn(self.stranger.id, [r["id"] for r in resp.data["results"]])

    def test_nor_can_their_password_be_set(self):
        resp = self.client.post(
            f"/api/auth/admin/members/{self.stranger.id}/set-password/",
            {"password": STRONG},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)
        self.stranger.refresh_from_db()
        self.assertFalse(self.stranger.check_password(STRONG))

    def test_nor_reached_through_the_general_account_endpoint(self):
        url = f"/api/auth/admin/users/{self.stranger.id}/"
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.patch(url, {"password": STRONG}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)
        self.assertTrue(User.objects.filter(pk=self.stranger.pk).exists())


class SignupEnrolmentTests(TenantAPIMixin, APITestCase):
    """Signing up is joining this gym.

    Access is read off Membership, so an account created without one could log
    in and see nothing -- which is what self-signup produced while it was sent
    with no gym in its path.
    """

    def setUp(self):
        cache.clear()

    def test_a_new_signup_is_a_member_of_this_gym(self):
        resp = self.client.post(
            "/api/auth/signup/",
            {"username": "newbie", "email": "newbie@example.com", "password": STRONG},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        newbie = User.objects.get(username="newbie")
        self.assertTrue(newbie.memberships.filter(tenant=self.tenant, role=Role.MEMBER).exists())
