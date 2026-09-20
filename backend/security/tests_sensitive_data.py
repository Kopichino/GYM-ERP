"""What the API hands back about an account never includes a secret.

The write side is pinned elsewhere (`tests_object_access.MassAssignmentPins`).
This is the read side: the password hash, the authenticator's shared secret and
the recovery-code hashes live on the same rows these endpoints serialize, so a
serializer that grew a `fields = "__all__"` would hand them to the browser.
Each endpoint that returns account data is read for real, and its raw body is
searched for every secret the account holds.
"""

from django.utils import timezone

from accounts import mfa
from accounts.models import MfaDevice, MfaRecoveryCode, Role

from .testing import OneGymTestCase

TOTP_SECRET = "JBSWY3DPEHPK3PXP"
RECOVERY_CODE = "ABCD-EFGH-2345"


class AccountReadLeakTests(OneGymTestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.person("owner", Role.ADMIN)
        self.member = self.person("private_member")
        MfaDevice.objects.create(user=self.member, secret=TOTP_SECRET, confirmed_at=timezone.now())
        MfaRecoveryCode.objects.create(
            user=self.member, code_hash=mfa.hash_recovery_code(RECOVERY_CODE)
        )
        self.member.refresh_from_db()

    def assert_holds_no_secret(self, resp):
        self.assertEqual(resp.status_code, 200, resp.content[:200])
        body = resp.content.decode()
        for secret in (
            self.member.password,
            TOTP_SECRET,
            mfa.hash_recovery_code(RECOVERY_CODE),
            "pbkdf2_",
            "argon2",
            "code_hash",
            "pending_secret",
        ):
            self.assertNotIn(secret, body)

    def test_a_member_reading_their_own_account(self):
        self.client.force_authenticate(self.member)
        self.assert_holds_no_secret(self.client.get("/api/auth/me/"))

    def test_their_two_step_status(self):
        self.client.force_authenticate(self.member)
        self.assert_holds_no_secret(self.client.get("/api/auth/mfa/"))

    def test_an_admin_listing_and_reading_accounts(self):
        self.client.force_authenticate(self.admin)
        self.assert_holds_no_secret(self.client.get("/api/auth/admin/users/"))
        self.assert_holds_no_secret(self.client.get(f"/api/auth/admin/users/{self.member.pk}/"))
        self.assert_holds_no_secret(self.client.get("/api/auth/admin/members/"))
