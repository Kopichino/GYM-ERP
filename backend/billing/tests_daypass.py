from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from accounts.models import MemberProfile, Role
from attendance.models import CheckInOut
from attendance.services import AttendanceError, open_visit, toggle_guest_visit

from .models import DayPass

User = get_user_model()
TODAY = timezone.localdate()


def make_user(username, role=Role.MEMBER):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    MemberProfile.objects.get_or_create(user=user)
    return user


class DayPassVisitTests(TenantAPIMixin, APITestCase):
    """Guests share the attendance table, and the member rule is untouched."""

    def setUp(self):
        self.guest = DayPass.objects.create(name="Walk-in Wendy", amount=Decimal("300"))
        self.member = make_user("passmember")

    def test_a_guest_visit_has_no_user(self):
        record, action = toggle_guest_visit(self.guest)
        self.assertEqual(action, "in")
        self.assertIsNone(record.user)
        self.assertEqual(record.day_pass, self.guest)

    def test_one_tap_in_the_next_tap_out(self):
        toggle_guest_visit(self.guest)
        record, action = toggle_guest_visit(self.guest)
        self.assertEqual(action, "out")
        self.assertIsNotNone(record.check_out_time)
        self.assertEqual(CheckInOut.objects.filter(day_pass=self.guest).count(), 1)

    def test_a_pass_cannot_hold_two_visits_open(self):
        CheckInOut.objects.create(day_pass=self.guest)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CheckInOut.objects.create(day_pass=self.guest)

    def test_two_different_guests_can_both_be_in(self):
        other = DayPass.objects.create(name="Walk-in Wally")
        toggle_guest_visit(self.guest)
        toggle_guest_visit(other)
        self.assertEqual(CheckInOut.objects.filter(check_out_time__isnull=True).count(), 2)

    def test_the_member_rule_is_unchanged(self):
        """The whole point of the nullable column: NULLs are distinct, so guest
        rows never participate in the member index."""
        open_visit(self.member)
        with self.assertRaises(AttendanceError):
            open_visit(self.member)

    def test_guests_in_the_building_do_not_block_a_member_checking_in(self):
        toggle_guest_visit(self.guest)
        toggle_guest_visit(DayPass.objects.create(name="Another"))
        record = open_visit(self.member)
        self.assertIsNotNone(record.id)

    def test_a_visit_must_belong_to_exactly_one_of_the_two(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CheckInOut.objects.create()

    def test_a_visit_cannot_belong_to_both(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CheckInOut.objects.create(user=self.member, day_pass=self.guest)

    def test_guest_visits_are_counted_in_the_gym_total(self):
        """Occupancy would under-report footfall if they lived elsewhere."""
        open_visit(self.member)
        toggle_guest_visit(self.guest)
        self.assertEqual(CheckInOut.objects.filter(check_out_time__isnull=True).count(), 2)

    def test_deleting_the_pass_takes_its_visits_with_it(self):
        toggle_guest_visit(self.guest)
        self.guest.delete()
        self.assertFalse(CheckInOut.objects.filter(day_pass__isnull=False).exists())


class DayPassApiTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = make_user("passadmin", Role.ADMIN)
        self.member = make_user("nosypassmember")
        self.client.force_authenticate(self.admin)

    def test_the_desk_issues_a_pass(self):
        resp = self.client.post(
            "/api/billing/day-passes/",
            {"name": "Ravi Guest", "phone": "+91 90000 00000", "amount": "300", "method": "cash"},
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["issued_by_name"], "passadmin")
        self.assertTrue(resp.data["is_valid_today"])
        self.assertFalse(resp.data["checked_in"])

    def test_members_cannot_see_the_day_pass_book(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get("/api/billing/day-passes/").status_code, 403)

    def test_checking_a_guest_in_and_out(self):
        created = self.client.post("/api/billing/day-passes/", {"name": "Guest"}).data
        first = self.client.post(f"/api/billing/day-passes/{created['id']}/check_in/")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.data["action"], "in")
        self.assertEqual(first.data["record"]["who"], "Guest")

        second = self.client.post(f"/api/billing/day-passes/{created['id']}/check_in/")
        self.assertEqual(second.data["action"], "out")

    def test_a_pass_for_another_day_is_refused(self):
        stale = DayPass.objects.create(name="Yesterday", valid_on=TODAY - timedelta(days=1))
        resp = self.client.post(f"/api/billing/day-passes/{stale.id}/check_in/")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("not today", resp.data["detail"])
        self.assertFalse(CheckInOut.objects.filter(day_pass=stale).exists())

    def test_the_book_can_be_read_for_one_day(self):
        DayPass.objects.create(name="Today")
        DayPass.objects.create(name="Last week", valid_on=TODAY - timedelta(days=7))
        resp = self.client.get(f"/api/billing/day-passes/?on={TODAY}")
        self.assertEqual(resp.data["count"], 1)

    def test_whether_a_guest_is_in_is_derived_not_flagged(self):
        created = self.client.post("/api/billing/day-passes/", {"name": "Guest"}).data
        self.client.post(f"/api/billing/day-passes/{created['id']}/check_in/")

        row = self.client.get(f"/api/billing/day-passes/{created['id']}/").data
        self.assertTrue(row["checked_in"])
        self.assertEqual(row["visit_count"], 1)

        self.client.post(f"/api/billing/day-passes/{created['id']}/check_in/")
        row = self.client.get(f"/api/billing/day-passes/{created['id']}/").data
        self.assertFalse(row["checked_in"])
        self.assertEqual(row["visit_count"], 1)
