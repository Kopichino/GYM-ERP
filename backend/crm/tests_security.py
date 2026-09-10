"""Lead conversion sets a first password, so it has to hold the password line.

Signup and admin account creation both run the configured validators. Turning a
lead into a member is a third route to a first password, and it was the one
that did not -- so "123456" was accepted here and refused everywhere else. A
weak password on a converted lead is exactly as useful to an attacker as a weak
one on a signup, and the member never chose it.
"""

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Role
from core.testing import TenantAPIMixin

from .models import Enquiry
from .services import ConversionError, convert

User = get_user_model()

GOOD_PASSWORD = "correct-horse-battery-42"


class ConversionPasswordTests(TenantAPIMixin, APITestCase):
    def _enquiry(self, name="Asha Rao"):
        return Enquiry.objects.create(
            name=name, phone="9876500000", follow_up_on=timezone.localdate()
        )

    def test_a_short_password_is_refused(self):
        with self.assertRaises(ConversionError):
            convert(self._enquiry(), username="asha", password="123456")

    def test_a_common_password_is_refused(self):
        with self.assertRaises(ConversionError):
            convert(self._enquiry("Ben Ray"), username="ben", password="password")

    def test_an_entirely_numeric_password_is_refused(self):
        with self.assertRaises(ConversionError):
            convert(self._enquiry("Cara Nair"), username="cara", password="83926104")

    def test_the_refusal_says_why(self):
        # It reaches an admin at the desk, so it has to be readable rather than
        # a bare "invalid".
        with self.assertRaises(ConversionError) as caught:
            convert(self._enquiry("Dev Iyer"), username="dev", password="123456")
        self.assertIn("too short", str(caught.exception).lower())

    def test_no_account_is_left_behind_by_a_refusal(self):
        with self.assertRaises(ConversionError):
            convert(self._enquiry("Eva Shah"), username="eva", password="123456")
        self.assertFalse(User.objects.filter(username="eva").exists())

    def test_a_strong_password_still_converts(self):
        user = convert(self._enquiry("Farah Ali"), username="farah", password=GOOD_PASSWORD)
        self.assertEqual(user.role, Role.MEMBER)
        self.assertTrue(user.check_password(GOOD_PASSWORD))

    def test_converting_without_a_password_is_still_allowed(self):
        # The ordinary case: the account opens with no usable password and the
        # member sets their own later. Validation must not break that.
        user = convert(self._enquiry("Gita Menon"), username="gita")
        self.assertFalse(user.has_usable_password())
