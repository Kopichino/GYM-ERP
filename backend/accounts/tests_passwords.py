"""Forgotten, reset and changed passwords."""

import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import Role

User = get_user_model()

STRONG = "Iron!Core-2026"
OTHER_STRONG = "Brand!New-2026"


def link_parts(body):
    match = re.search(r"uid=([^&\s]+)&token=([^\s]+)", body)
    assert match, body
    return match.group(1), match.group(2)


class ForgotPasswordTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="asha", email="asha@example.com", password=STRONG, role=Role.MEMBER
        )

    def forgot(self, email):
        return self.client.post("/api/auth/password/forgot/", {"email": email}, format="json")

    def test_a_known_email_is_sent_a_link(self):
        resp = self.forgot("ASHA@example.com")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["asha@example.com"])
        self.assertIn(f"{settings.FRONTEND_URL}/reset-password?uid=", mail.outbox[0].body)

    def test_an_unknown_email_gets_the_same_answer_and_no_mail(self):
        """Otherwise this page is a way to find out who is a member."""
        known = self.forgot("asha@example.com")
        unknown = self.forgot("nobody@example.com")
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.data, unknown.data)
        self.assertEqual(len(mail.outbox), 1)

    def test_an_imported_account_with_no_password_can_set_its_first_one(self):
        """Django's own reset form skips unusable passwords -- exactly the
        accounts an import creates -- which is why this flow does not use it."""
        imported = User.objects.create_user(
            username="imported", email="imported@example.com", password=None, role=Role.MEMBER
        )
        self.assertFalse(imported.has_usable_password())

        self.forgot("imported@example.com")
        uid, token = link_parts(mail.outbox[0].body)
        resp = self.client.post(
            "/api/auth/password/reset/",
            {"uid": uid, "token": token, "password": STRONG},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        imported.refresh_from_db()
        self.assertTrue(imported.check_password(STRONG))

    def test_a_placeholder_import_address_is_never_mailed(self):
        User.objects.create_user(
            username="phoneonly", email="phoneonly@imported.local", password=None, role=Role.MEMBER
        )
        resp = self.forgot("phoneonly@imported.local")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)


class ResetPasswordTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="ravi", email="ravi@example.com", password=STRONG, role=Role.TRAINER
        )
        self.client.post("/api/auth/password/forgot/", {"email": "ravi@example.com"}, format="json")
        self.uid, self.token = link_parts(mail.outbox[0].body)

    def reset(self, password=OTHER_STRONG, token=None):
        return self.client.post(
            "/api/auth/password/reset/",
            {"uid": self.uid, "token": token or self.token, "password": password},
            format="json",
        )

    def test_the_link_sets_a_new_password(self):
        self.assertEqual(self.reset().status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OTHER_STRONG))

    def test_the_link_works_only_once(self):
        """Single use without bookkeeping: the token is derived from the
        password hash, which the first use changes."""
        self.assertEqual(self.reset().status_code, 200)
        self.assertEqual(self.reset(password="Third!Try-2026").status_code, 400)

    def test_a_tampered_token_is_refused(self):
        self.assertEqual(self.reset(token="not-a-real-token").status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(STRONG))

    def test_a_weak_password_is_refused_with_the_reason(self):
        resp = self.reset(password="123")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("password", resp.data)

    def test_a_reset_ends_existing_sessions(self):
        """A reset is how you lock out whoever took the account."""
        RefreshToken.for_user(self.user)
        self.assertEqual(self.reset().status_code, 200)
        self.assertTrue(BlacklistedToken.objects.filter(token__user=self.user).exists())


class ChangePasswordTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="priya", email="priya@example.com", password=STRONG, role=Role.MEMBER
        )

    def change(self, current, new):
        return self.client.post(
            "/api/auth/password/change/",
            {"current_password": current, "new_password": new},
            format="json",
        )

    def test_signing_in_is_required(self):
        self.assertEqual(self.change(STRONG, OTHER_STRONG).status_code, 401)

    def test_the_current_password_must_be_right(self):
        self.client.force_authenticate(self.user)
        resp = self.change("wrong-password", OTHER_STRONG)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("current_password", resp.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(STRONG))

    def test_a_change_keeps_this_session_and_ends_the_others(self):
        old_session = RefreshToken.for_user(self.user)
        self.client.force_authenticate(self.user)

        resp = self.change(STRONG, OTHER_STRONG)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)
        self.assertIn(settings.JWT_REFRESH_COOKIE_NAME, resp.cookies)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OTHER_STRONG))
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=old_session["jti"]).exists())
