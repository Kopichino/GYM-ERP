"""One gym must not see, change or even name another gym's people.

`tenancy.tests_isolation` proves the scoped managers hold for tenant-owned rows.
These cover what those managers cannot reach: `User` and `MemberProfile` belong
to the platform, not to a gym, so every query that starts from them has to
narrow to "people at this gym" by hand -- and every place that forgot to was a
leak. Each test names the one it closes.
"""

import hashlib
import hmac
import io
import json
import tempfile
from datetime import timedelta
from decimal import Decimal

import openpyxl
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from accounts.models import MemberProfile, MembershipStatus, MfaDevice, Role
from attendance.models import CheckInOut
from billing.models import OrderStatus, Payment, PaymentOrder, Plan
from bodystats.models import BodyMeasurement
from crm.models import Enquiry
from gallery.models import GalleryPost
from schedule_app.models import ClassBooking, ClassSession
from tenancy import context
from tenancy.models import Membership
from workouts.models import WorkoutSplit

from .testing import PASSWORD, TwoGymsTestCase, make_person, png_bytes

TEMP_MEDIA = tempfile.mkdtemp(prefix="ironcore-isolation-")

WEBHOOK_SECRET = "hook_secret"
GATEWAY = {
    "RAZORPAY_KEY_ID": "rzp_test_key",
    "RAZORPAY_KEY_SECRET": "rzp_test_secret",
    "RAZORPAY_WEBHOOK_SECRET": WEBHOOK_SECRET,
}


class OtherGymsPeopleTests(TwoGymsTestCase):
    """Gym A's admin, reading lists and reports built from platform-wide tables."""

    def setUp(self):
        super().setUp()
        self.admin_a = make_person("admin_a", gym=self.gym_a, role=Role.ADMIN)
        self.member_a = make_person("member_a", gym=self.gym_a)
        self.trainer_a = make_person("trainer_a", gym=self.gym_a, role=Role.TRAINER)
        self.member_b = make_person(
            "member_b", gym=self.gym_b, first_name="Beatrix", last_name="Outsider"
        )
        self.trainer_b = make_person(
            "trainer_b", gym=self.gym_b, role=Role.TRAINER, first_name="Theodora"
        )
        with context.scope(self.gym_a):
            self.plan_a = Plan.objects.create(
                name="Monthly", price=Decimal("1000"), duration_days=30
            )
        self.base = self.at(self.gym_a)
        self.sign_in(self.admin_a)

    def test_the_billing_member_list_shows_only_this_gyms_members(self):
        resp = self.client.get(f"{self.base}/billing/admin/members/")
        self.assertEqual(resp.status_code, 200)
        usernames = [row["username"] for row in resp.data["results"]]
        self.assertIn("member_a", usernames)
        self.assertNotIn("member_b", usernames)
        self.assertNotIn(b"Beatrix", resp.content)

    def test_the_billing_export_leaves_out_other_gyms_members(self):
        resp = self.client.get(f"{self.base}/billing/admin/members/export/")
        self.assertEqual(resp.status_code, 200)
        sheet = openpyxl.load_workbook(io.BytesIO(resp.content)).active
        usernames = [row[0] for row in sheet.iter_rows(min_row=2, values_only=True)]
        self.assertIn("member_a", usernames)
        self.assertNotIn("member_b", usernames)

    def test_the_at_risk_call_list_leaves_out_other_gyms_members(self):
        # Long-standing members who have never visited: both are "quiet", so
        # only the gym boundary can keep member_b off gym A's call list.
        MemberProfile.objects.filter(user__in=[self.member_a, self.member_b]).update(
            join_date=timezone.localdate() - timedelta(days=200)
        )
        resp = self.client.get(f"{self.base}/crm/at-risk/")
        self.assertEqual(resp.status_code, 200)
        usernames = [row["username"] for row in resp.data["results"]]
        self.assertIn("member_a", usernames)
        self.assertNotIn("member_b", usernames)

    def test_the_pt_report_leaves_out_other_gyms_trainers(self):
        resp = self.client.get(f"{self.base}/reports/pt-performance/")
        self.assertEqual(resp.status_code, 200)
        trainers = [row["trainer"] for row in resp.data["trainers"]]
        self.assertIn("trainer_a", trainers)
        self.assertNotIn("trainer_b", trainers)

    def test_the_attendance_report_counts_only_this_gyms_members(self):
        resp = self.client.get(f"{self.base}/reports/attendance/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["member_count"], 1)

    def test_the_dashboard_does_not_count_other_gyms_paused_members(self):
        MemberProfile.objects.filter(user=self.member_b).update(
            membership_status=MembershipStatus.PAUSED
        )
        resp = self.client.get(f"{self.base}/reports/kpis/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["paused_members"], 0)

    def test_pricing_a_sale_for_another_gyms_member_is_a_404_that_names_nobody(self):
        resp = self.client.post(
            f"{self.base}/billing/checkout/quote/",
            {"member": self.member_b.pk, "plan": self.plan_a.pk},
        )
        self.assertEqual(resp.status_code, 404)
        self.assertNotIn(b"Beatrix", resp.content)

    def test_a_sale_to_another_gyms_member_records_nothing(self):
        resp = self.client.post(
            f"{self.base}/billing/checkout/",
            {"member": self.member_b.pk, "plan": self.plan_a.pk, "method": "cash"},
        )
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(Payment.unscoped.filter(member=self.member_b).exists())

    def test_recording_a_payment_against_another_gyms_member_is_refused(self):
        resp = self.client.post(
            f"{self.base}/billing/admin/payments/",
            {
                "member": self.member_b.pk,
                "plan": self.plan_a.pk,
                "amount": "1000.00",
                "method": "cash",
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Payment.unscoped.filter(member=self.member_b).exists())

    def test_another_gyms_member_body_stats_cannot_be_read(self):
        resp = self.client.get(f"{self.base}/bodystats/summary/?member={self.member_b.pk}")
        self.assertEqual(resp.status_code, 404)

    def test_another_gyms_member_body_stats_cannot_be_written(self):
        resp = self.client.post(
            f"{self.base}/bodystats/measurements/",
            {
                "user": self.member_b.pk,
                "recorded_on": timezone.localdate().isoformat(),
                "weight_kg": "80.0",
            },
        )
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(BodyMeasurement.unscoped.filter(user=self.member_b).exists())

    def test_another_gyms_member_workout_plan_cannot_be_read(self):
        WorkoutSplit.objects.create(user=self.member_b, name="Beatrix's private split")
        resp = self.client.get(f"{self.base}/workouts/splits/?member={self.member_b.pk}")
        self.assertEqual(resp.status_code, 404)
        self.assertNotIn(b"private split", resp.content)

    def test_another_gyms_trainer_is_neither_bookable_nor_named(self):
        self.sign_in(self.member_a)
        resp = self.client.get(f"{self.base}/pt/slots/?trainer={self.trainer_b.pk}")
        self.assertEqual(resp.status_code, 404)
        self.assertNotIn(b"Theodora", resp.content)

    def test_a_trainer_from_another_gym_cannot_be_assigned_to_a_member(self):
        resp = self.client.patch(
            f"{self.base}/auth/admin/users/{self.member_a.pk}/",
            {"trainer": self.trainer_b.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIsNone(MemberProfile.objects.get(user=self.member_a).trainer_id)


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class SignedInStrangerTests(TwoGymsTestCase):
    """A genuine token from gym B, pointed at gym A's URLs.

    Views guarded only by `IsAuthenticated` never asked whether the caller
    belongs at the gym in the path, so a member anywhere on the platform could
    read and write another gym's gallery, timetable, bookings and call list.
    """

    def setUp(self):
        super().setUp()
        self.member_a = make_person("member_a", gym=self.gym_a)
        self.trainer_a = make_person("trainer_a", gym=self.gym_a, role=Role.TRAINER)
        self.stranger = make_person("stranger", gym=self.gym_b)
        with context.scope(self.gym_a):
            GalleryPost.objects.create(
                uploader=self.member_a,
                media="gallery/a.png",
                media_type="image",
                caption="Gym A members only",
                approved=True,
            )
            self.session = ClassSession.objects.create(
                title="Gym A spin",
                trainer=self.trainer_a,
                date=timezone.localdate() + timedelta(days=1),
                start_time="07:00",
                end_time="08:00",
                capacity=10,
            )
        self.base = self.at(self.gym_a)
        self.sign_in(self.stranger)

    def test_they_cannot_read_the_gallery(self):
        resp = self.client.get(f"{self.base}/gallery/")
        self.assertEqual(resp.status_code, 403)
        self.assertNotIn(b"Gym A members only", resp.content)

    def test_they_cannot_post_into_the_gallery(self):
        resp = self.client.post(
            f"{self.base}/gallery/",
            {
                "media": SimpleUploadedFile("p.png", png_bytes(), content_type="image/png"),
                "media_type": "image",
            },
            format="multipart",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(GalleryPost.unscoped.filter(uploader=self.stranger).exists())

    def test_they_cannot_read_the_timetable(self):
        resp = self.client.get(f"{self.base}/schedule/")
        self.assertEqual(resp.status_code, 403)
        self.assertNotIn(b"Gym A spin", resp.content)

    def test_they_cannot_book_a_class(self):
        resp = self.client.post(f"{self.base}/schedule/{self.session.pk}/book/")
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(ClassBooking.unscoped.filter(member=self.stranger).exists())

    def test_they_cannot_plant_a_lead_in_the_call_list(self):
        resp = self.client.post(
            f"{self.base}/referrals/", {"name": "Planted Lead", "phone": "9000000001"}
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Enquiry.unscoped.filter(name="Planted Lead").exists())

    def test_they_cannot_check_in(self):
        resp = self.client.post(f"{self.base}/attendance/check_in/")
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(CheckInOut.unscoped.filter(user=self.stranger).exists())

    def test_they_cannot_read_the_leaderboard(self):
        resp = self.client.get(f"{self.base}/gamification/leaderboard/")
        self.assertEqual(resp.status_code, 403)

    def test_a_member_of_the_gym_still_gets_in(self):
        """Pins that the refusals above are about standing, not a broken route."""
        self.sign_in(self.member_a)
        resp = self.client.get(f"{self.base}/gallery/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Gym A members only", resp.content)


class PlatformRouteTests(TwoGymsTestCase):
    def test_a_gym_route_called_without_a_gym_is_a_404_not_a_crash(self):
        """No gym in the path used to reach a scoped manager and raise a 500."""
        member = make_person("member_a", gym=self.gym_a)
        self.sign_in(member)
        resp = self.client.get("/api/gallery/")
        self.assertEqual(resp.status_code, 404)


class SharedAccountTests(TwoGymsTestCase):
    """One person with standing at two gyms.

    Gym A's admin manages gym A. Before this, being able to see an account on
    gym A's member list was enough to set its password, change its sign-in
    email, clear its authenticator or delete it outright -- which, for an admin
    of gym B who also trains at gym A, is a takeover of gym B.
    """

    def setUp(self):
        super().setUp()
        self.admin_a = make_person("admin_a", gym=self.gym_a, role=Role.ADMIN)
        self.shared = make_person("shared", gym=self.gym_b, role=Role.ADMIN)
        Membership.objects.create(user=self.shared, tenant=self.gym_a, role=Role.MEMBER)
        self.local = make_person("local", gym=self.gym_a)
        self.base = self.at(self.gym_a)
        self.sign_in(self.admin_a)

    def test_gym_a_cannot_set_the_password_of_an_account_shared_with_gym_b(self):
        resp = self.client.post(
            f"{self.base}/auth/admin/members/{self.shared.pk}/set-password/",
            {"password": "a-brand-new-passphrase-99"},
        )
        self.assertEqual(resp.status_code, 403)
        self.shared.refresh_from_db()
        self.assertTrue(self.shared.check_password(PASSWORD))

    def test_gym_a_cannot_change_the_sign_in_details_of_a_shared_account(self):
        resp = self.client.patch(
            f"{self.base}/auth/admin/users/{self.shared.pk}/",
            {"email": "attacker@example.com", "password": "a-brand-new-passphrase-99"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)
        self.shared.refresh_from_db()
        self.assertEqual(self.shared.email, "shared@example.com")
        self.assertTrue(self.shared.check_password(PASSWORD))

    def test_gym_a_cannot_clear_the_authenticator_of_a_shared_account(self):
        MfaDevice.objects.create(
            user=self.shared, secret="JBSWY3DPEHPK3PXP", confirmed_at=timezone.now()
        )
        resp = self.client.post(f"{self.base}/auth/admin/users/{self.shared.pk}/reset-mfa/")
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(MfaDevice.objects.filter(user=self.shared).exists())

    def test_removing_a_shared_account_only_ends_its_standing_here(self):
        resp = self.client.delete(f"{self.base}/auth/admin/users/{self.shared.pk}/")
        self.assertEqual(resp.status_code, 204)
        self.assertTrue(type(self.shared).objects.filter(pk=self.shared.pk).exists())
        self.assertTrue(
            Membership.objects.filter(
                user=self.shared, tenant=self.gym_b, role=Role.ADMIN, is_active=True
            ).exists()
        )
        self.assertFalse(
            Membership.objects.filter(
                user=self.shared, tenant=self.gym_a, is_active=True
            ).exists()
        )

    def test_an_account_that_belongs_only_here_can_still_be_given_a_password(self):
        """Pins that the refusals above are about sharing, not a broken action."""
        resp = self.client.post(
            f"{self.base}/auth/admin/members/{self.local.pk}/set-password/",
            {"password": "a-brand-new-passphrase-99"},
        )
        self.assertEqual(resp.status_code, 200)
        self.local.refresh_from_db()
        self.assertTrue(self.local.check_password("a-brand-new-passphrase-99"))


class ImportAdoptionTests(TwoGymsTestCase):
    """The importer matched rows to accounts by email across the whole platform,
    then renamed the account and enrolled it here -- after which gym A's admin
    held the set-password and reset-MFA buttons for it."""

    def setUp(self):
        super().setUp()
        self.admin_a = make_person("admin_a", gym=self.gym_a, role=Role.ADMIN)
        self.outsider = make_person("outsider", gym=self.gym_b, first_name="Olive")
        self.base = self.at(self.gym_a)
        self.sign_in(self.admin_a)

    def test_an_import_row_naming_another_gyms_account_does_not_adopt_it(self):
        rows = "First Name,Last Name,Email\nMallory,Takeover,outsider@example.com\n"
        resp = self.client.post(
            f"{self.base}/import/commit/",
            {
                "kind": "members",
                "file": SimpleUploadedFile("m.csv", rows.encode(), content_type="text/csv"),
            },
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertFalse(
            Membership.objects.filter(user=self.outsider, tenant=self.gym_a).exists()
        )
        self.outsider.refresh_from_db()
        self.assertEqual(self.outsider.first_name, "Olive")


@override_settings(**GATEWAY)
class RazorpayWebhookTenantTests(TwoGymsTestCase):
    """Razorpay is configured with one webhook URL for the platform, which names
    no gym -- so the scoped order lookup raised and every capture was a 500."""

    def setUp(self):
        super().setUp()
        self.member_b = make_person("payer_b", gym=self.gym_b)
        with context.scope(self.gym_b):
            plan = Plan.objects.create(name="Quarterly", price=Decimal("1500"), duration_days=90)
            self.order = PaymentOrder.objects.create(
                member=self.member_b,
                plan=plan,
                amount=Decimal("1500.00"),
                order_id="order_GYMB1",
            )

    def capture(self, path, amount_paise=150000, currency="INR"):
        body = json.dumps(
            {
                "event": "payment.captured",
                "payload": {
                    "payment": {
                        "entity": {
                            "id": "pay_GYMB1",
                            "order_id": "order_GYMB1",
                            "amount": amount_paise,
                            "currency": currency,
                            "status": "captured",
                        }
                    }
                },
            }
        )
        signature = hmac.new(WEBHOOK_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        return self.client.post(
            path, data=body, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE=signature
        )

    def test_a_capture_on_the_shared_url_settles_the_order_in_its_own_gym(self):
        resp = self.capture("/api/billing/online/webhook/")
        self.assertEqual(resp.status_code, 200, resp.content)
        order = PaymentOrder.unscoped.get(pk=self.order.pk)
        self.assertEqual(order.status, OrderStatus.PAID)
        self.assertEqual(order.payment.tenant_id, self.gym_b.pk)

    def test_a_capture_for_less_than_the_order_settles_nothing(self):
        resp = self.capture(f"{self.at(self.gym_b)}/billing/online/webhook/", amount_paise=100)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PaymentOrder.unscoped.get(pk=self.order.pk).status, OrderStatus.CREATED)
        self.assertFalse(Payment.unscoped.filter(member=self.member_b).exists())

    def test_a_capture_in_another_currency_settles_nothing(self):
        resp = self.capture("/api/billing/online/webhook/", currency="USD")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Payment.unscoped.filter(member=self.member_b).exists())

    def test_a_replayed_capture_records_one_payment(self):
        for _ in range(3):
            self.assertEqual(self.capture("/api/billing/online/webhook/").status_code, 200)
        self.assertEqual(Payment.unscoped.filter(member=self.member_b).count(), 1)

    def test_an_order_posted_to_another_gyms_url_never_lands_in_that_gym(self):
        self.capture(f"{self.at(self.gym_a)}/billing/online/webhook/")
        self.assertFalse(Payment.unscoped.filter(tenant=self.gym_a).exists())
