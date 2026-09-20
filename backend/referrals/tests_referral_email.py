"""The email on a referral: checked by the server, and refused on the field.

The audit's "malformed email fails silently" was the page -- it answered every
refusal with "Check the name and try again", beside the button rather than the
field. The server was already refusing a malformed address with a field error.
These pin that contract, which the page now relies on to show the reason next to
the email box.

There is no rule against referring the same address twice: a member may
mention a friend again, and the front desk sees both. That is pinned as it is
rather than invented here.
"""

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from accounts.models import MemberProfile, Role
from core.testing import TenantAPIMixin
from crm.models import Enquiry

from .models import Referral

User = get_user_model()

INVALID = "Enter a valid email address."


class ReferralEmailTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.member = User.objects.create_user(
            username="referrer", email="referrer@example.com", password="pass12345", role=Role.MEMBER
        )
        MemberProfile.objects.get_or_create(user=self.member)
        self.member_for(self.member, Role.MEMBER)
        self.client.force_authenticate(self.member)

    def refer(self, **fields):
        return self.client.post("/api/referrals/", {"name": "Friend", **fields}, format="json")

    def test_a_valid_email_is_saved(self):
        resp = self.refer(email="friend@example.com")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Referral.objects.get().email, "friend@example.com")

    def test_a_malformed_email_is_refused_on_the_field_and_nothing_is_saved(self):
        for value in ("not-an-email", "friend@", "@example.com", "two words@example.com", "a@b@c.com"):
            with self.subTest(email=value):
                resp = self.refer(email=value, phone="9000000009")
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertEqual([str(m) for m in resp.data["email"]], [INVALID])
                self.assertNotIn(b"Traceback", resp.content)
        self.assertFalse(Referral.objects.exists())
        # The call-back queue gets nothing either: the lead is raised with the referral.
        self.assertFalse(Enquiry.objects.exists())

    def test_leaving_the_email_out_is_fine(self):
        for payload in ({}, {"email": ""}):
            with self.subTest(payload=payload):
                self.assertEqual(self.refer(**payload).status_code, 201)
        self.assertEqual(set(Referral.objects.values_list("email", flat=True)), {""})

    def test_spaces_around_an_email_are_trimmed(self):
        resp = self.refer(email="  friend@example.com  ")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Referral.objects.get().email, "friend@example.com")

    def test_an_email_of_only_spaces_counts_as_none(self):
        resp = self.refer(email="   ")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Referral.objects.get().email, "")

    def test_referring_the_same_address_twice_is_allowed(self):
        self.assertEqual(self.refer(email="friend@example.com").status_code, 201)
        self.assertEqual(self.refer(email="friend@example.com").status_code, 201)
        self.assertEqual(Referral.objects.filter(email="friend@example.com").count(), 2)

    def test_a_name_is_still_required(self):
        resp = self.client.post("/api/referrals/", {"name": "", "email": "friend@example.com"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("name", resp.data)

    # -- the phone, which becomes a call-back lead

    def test_a_phone_that_cannot_be_called_is_refused_and_raises_no_lead(self):
        """A referral with a phone raises a front-desk enquiry. The enquiry form
        refuses a number with too few digits to dial, so the referral must too --
        otherwise the call-back queue gets a lead nobody can ring."""
        for value in ("abc", "12", "call me"):
            with self.subTest(phone=value):
                resp = self.refer(phone=value)
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertIn("phone", resp.data)
                self.assertNotIn(b"Traceback", resp.content)
        self.assertFalse(Referral.objects.exists())
        self.assertFalse(Enquiry.objects.exists())

    def test_a_dialable_phone_is_saved_and_raises_a_lead(self):
        for value in ("+91 90000 00002", "9000000009", "(022) 2345-6789"):
            with self.subTest(phone=value):
                resp = self.refer(phone=value)
                self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Referral.objects.count(), 3)
        self.assertEqual(Enquiry.objects.count(), 3)

    def test_leaving_the_phone_out_is_fine_and_raises_no_lead(self):
        for payload in ({}, {"phone": ""}, {"phone": "   "}):
            with self.subTest(payload=payload):
                self.assertEqual(self.refer(**payload).status_code, 201)
        self.assertFalse(Enquiry.objects.exists())

    def test_signing_in_is_required(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.refer(email="friend@example.com").status_code, 401)
        self.assertFalse(Referral.objects.exists())
