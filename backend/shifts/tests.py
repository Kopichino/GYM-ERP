from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.db.utils import IntegrityError
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from accounts.models import MemberProfile, Role

from .models import Position, Shift
from .services import ShiftError, on_floor, save_shift

User = get_user_model()
TODAY = timezone.localdate()


def make_user(username, role=Role.TRAINER):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    MemberProfile.objects.get_or_create(user=user)
    return user


class ShiftRuleTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.ravi = make_user("ravi")
        self.meera = make_user("meera")

    def add(self, staff, start, end, date=None, position=Position.FLOOR):
        return save_shift(
            staff=staff,
            date=date or TODAY,
            start_time=time(start),
            end_time=time(end),
            position=position,
        )

    def test_a_shift_is_stored_with_its_length_derived(self):
        shift = self.add(self.ravi, 6, 14)
        self.assertEqual(shift.hours, 8.0)

    def test_the_same_person_cannot_be_in_two_places_at_once(self):
        self.add(self.ravi, 6, 14)
        with self.assertRaises(ShiftError) as caught:
            self.add(self.ravi, 12, 20)
        self.assertIn("already on", str(caught.exception))

    def test_a_handover_is_not_a_clash(self):
        """One finishing at 14:00 and the next starting at 14:00 is a handover."""
        self.add(self.ravi, 6, 14)
        self.add(self.ravi, 14, 22)
        self.assertEqual(Shift.objects.filter(staff=self.ravi).count(), 2)

    def test_two_people_can_share_a_slot(self):
        self.add(self.ravi, 6, 14)
        self.add(self.meera, 6, 14)
        self.assertEqual(Shift.objects.count(), 2)

    def test_the_same_person_can_work_the_same_hours_on_another_day(self):
        self.add(self.ravi, 6, 14)
        self.add(self.ravi, 6, 14, date=TODAY + timedelta(days=1))
        self.assertEqual(Shift.objects.filter(staff=self.ravi).count(), 2)

    def test_a_shift_that_ends_before_it_starts_is_refused(self):
        with self.assertRaises(ShiftError):
            self.add(self.ravi, 20, 6)

    def test_the_database_refuses_a_backwards_shift_too(self):
        """The service check is convenience; the constraint is the guarantee."""
        with self.assertRaises(IntegrityError):
            Shift.objects.create(
                staff=self.ravi, date=TODAY, start_time=time(20), end_time=time(6)
            )

    def test_editing_a_shift_does_not_clash_with_itself(self):
        shift = self.add(self.ravi, 6, 14)
        save_shift(
            staff=self.ravi,
            date=TODAY,
            start_time=time(7),
            end_time=time(15),
            position=Position.FLOOR,
            instance=shift,
        )
        shift.refresh_from_db()
        self.assertEqual(shift.start_time, time(7))

    def test_position_is_separate_from_role(self):
        """A trainer can cover the desk without becoming an admin."""
        shift = self.add(self.ravi, 6, 14, position=Position.FRONT_DESK)
        self.assertEqual(shift.position, Position.FRONT_DESK)
        self.assertEqual(shift.staff.role, Role.TRAINER)


class OnFloorTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.ravi = make_user("onfloorravi")
        self.meera = make_user("onfloormeera")

    def test_only_whoever_is_rostered_right_now(self):
        now = timezone.localtime()
        # A window that certainly contains now, and one that certainly doesn't.
        save_shift(
            staff=self.ravi,
            date=now.date(),
            start_time=time(0, 1),
            end_time=time(23, 59),
            position=Position.FLOOR,
        )
        save_shift(
            staff=self.meera,
            date=now.date() + timedelta(days=1),
            start_time=time(9),
            end_time=time(17),
            position=Position.FLOOR,
        )

        names = [s.staff.username for s in on_floor(now)]
        self.assertEqual(names, ["onfloorravi"])

    def test_nobody_on_is_an_empty_answer_not_an_error(self):
        self.assertEqual(list(on_floor()), [])


class ShiftApiTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = make_user("rotaadmin", Role.ADMIN)
        self.trainer = make_user("rotacoach")
        self.member = make_user("rotamember", Role.MEMBER)

    def payload(self, staff, start="06:00", end="14:00", date=None):
        return {
            "staff": staff.id,
            "date": str(date or TODAY),
            "start_time": start,
            "end_time": end,
            "position": Position.FLOOR,
        }

    def test_only_an_admin_writes_the_rota(self):
        self.client.force_authenticate(self.trainer)
        resp = self.client.post("/api/shifts/", self.payload(self.trainer))
        self.assertEqual(resp.status_code, 403)

    def test_an_admin_can(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post("/api/shifts/", self.payload(self.trainer))
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["hours"], 8.0)
        self.assertEqual(resp.data["staff_name"], "rotacoach")

    def test_a_clash_comes_back_readably_rather_than_as_a_500(self):
        self.client.force_authenticate(self.admin)
        self.client.post("/api/shifts/", self.payload(self.trainer))
        resp = self.client.post(
            "/api/shifts/", self.payload(self.trainer, start="12:00", end="20:00")
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("already on", str(resp.data))

    def test_anyone_signed_in_can_read_who_is_on(self):
        self.client.force_authenticate(self.member)
        resp = self.client.get("/api/shifts/on_floor/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("count", resp.data)

    def test_mine_returns_only_upcoming_shifts_for_the_caller(self):
        self.client.force_authenticate(self.admin)
        self.client.post("/api/shifts/", self.payload(self.trainer))
        self.client.post(
            "/api/shifts/", self.payload(self.admin, date=TODAY + timedelta(days=1))
        )
        # A shift that has already been and gone.
        Shift.objects.create(
            staff=self.trainer,
            date=TODAY - timedelta(days=3),
            start_time=time(6),
            end_time=time(14),
        )

        self.client.force_authenticate(self.trainer)
        resp = self.client.get("/api/shifts/mine/")
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["date"], str(TODAY))

    def test_the_rota_can_be_read_a_week_at_a_time(self):
        self.client.force_authenticate(self.admin)
        self.client.post("/api/shifts/", self.payload(self.trainer))
        self.client.post(
            "/api/shifts/", self.payload(self.trainer, date=TODAY + timedelta(days=10))
        )

        resp = self.client.get(
            f"/api/shifts/?from={TODAY}&to={TODAY + timedelta(days=6)}"
        )
        self.assertEqual(resp.data["count"], 1)

    def test_positions_are_offered_to_the_form(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get("/api/shifts/positions/")
        values = [row["value"] for row in resp.data]
        self.assertIn("front_desk", values)

    def test_a_backwards_shift_is_refused_before_it_reaches_the_database(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/shifts/", self.payload(self.trainer, start="20:00", end="06:00")
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("end_time", resp.data)
