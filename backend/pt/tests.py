from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from accounts.models import MemberProfile, Role

from .models import Availability, PTSession, SessionStatus, Unavailable
from .services import BookingError, book_session, cancel_session, open_slots, utilisation

User = get_user_model()


def make_user(username, role=Role.MEMBER):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    MemberProfile.objects.get_or_create(user=user)
    return user


def next_weekday(weekday, after=None):
    """The next date with this weekday, at least a day away, so tests are never
    tripped up by a slot that has already passed today."""
    day = (after or timezone.localdate()) + timedelta(days=1)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day


class SlotDerivationTests(TenantAPIMixin, APITestCase):
    """Open slots are computed, never stored."""

    def setUp(self):
        self.trainer = make_user("slotcoach", Role.TRAINER)
        self.member = make_user("slotmember")
        self.day = next_weekday(2)  # a Wednesday
        Availability.objects.create(
            trainer=self.trainer, weekday=2, start_time=time(9), end_time=time(12)
        )

    def test_a_window_is_sliced_into_bookable_hours(self):
        slots = open_slots(self.trainer, self.day)
        self.assertEqual(
            [s["start_time"] for s in slots], [time(9), time(10), time(11)]
        )

    def test_a_tail_too_short_to_sell_is_dropped(self):
        Availability.objects.all().delete()
        Availability.objects.create(
            trainer=self.trainer, weekday=2, start_time=time(9), end_time=time(10, 30)
        )
        slots = open_slots(self.trainer, self.day)
        self.assertEqual([s["start_time"] for s in slots], [time(9)])

    def test_a_booked_slot_disappears(self):
        book_session(
            trainer=self.trainer,
            member=self.member,
            on=self.day,
            start_time=time(10),
            end_time=time(11),
        )
        starts = [s["start_time"] for s in open_slots(self.trainer, self.day)]
        self.assertEqual(starts, [time(9), time(11)])

    def test_cancelling_puts_the_slot_back(self):
        session = book_session(
            trainer=self.trainer,
            member=self.member,
            on=self.day,
            start_time=time(10),
            end_time=time(11),
        )
        cancel_session(session)
        starts = [s["start_time"] for s in open_slots(self.trainer, self.day)]
        self.assertIn(time(10), starts)

    def test_a_blocked_day_offers_nothing(self):
        Unavailable.objects.create(trainer=self.trainer, date=self.day, reason="Leave")
        self.assertEqual(open_slots(self.trainer, self.day), [])

    def test_the_weekly_pattern_survives_a_day_off(self):
        """A holiday must not cost the trainer every future Wednesday."""
        Unavailable.objects.create(trainer=self.trainer, date=self.day)
        following = self.day + timedelta(days=7)
        self.assertEqual(len(open_slots(self.trainer, following)), 3)

    def test_another_weekday_offers_nothing(self):
        self.assertEqual(open_slots(self.trainer, self.day + timedelta(days=1)), [])

    def test_slots_earlier_today_are_not_offered(self):
        today = timezone.localdate()
        Availability.objects.create(
            trainer=self.trainer, weekday=today.weekday(), start_time=time(0), end_time=time(23)
        )
        now = timezone.localtime().replace(hour=12, minute=0)
        starts = [s["start_time"] for s in open_slots(self.trainer, today, now=now)]
        self.assertTrue(all(s > time(12) for s in starts))


class BookingTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.trainer = make_user("bookcoach", Role.TRAINER)
        self.other_trainer = make_user("othercoach", Role.TRAINER)
        self.member = make_user("bookmember")
        self.rival = make_user("rivalmember")
        self.day = next_weekday(2)
        for trainer in (self.trainer, self.other_trainer):
            Availability.objects.create(
                trainer=trainer, weekday=2, start_time=time(9), end_time=time(12)
            )

    def book(self, member=None, trainer=None, start=9, end=10, on=None):
        return book_session(
            trainer=trainer or self.trainer,
            member=member or self.member,
            on=on or self.day,
            start_time=time(start),
            end_time=time(end),
        )

    def test_a_slot_can_only_be_sold_once(self):
        self.book()
        with self.assertRaises(BookingError) as caught:
            self.book(member=self.rival)
        self.assertIn("just been taken", str(caught.exception))

    def test_the_index_backs_the_service_up(self):
        self.book()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PTSession.objects.create(
                    trainer=self.trainer,
                    member=self.rival,
                    date=self.day,
                    start_time=time(9),
                    end_time=time(10),
                )

    def test_a_cancelled_booking_does_not_block_the_slot(self):
        cancel_session(self.book())
        self.assertIsNotNone(self.book(member=self.rival).id)

    def test_a_member_cannot_be_with_two_trainers_at_once(self):
        self.book()
        with self.assertRaises(BookingError) as caught:
            self.book(trainer=self.other_trainer)
        self.assertIn("already have a session", str(caught.exception))

    def test_a_time_outside_the_trainers_hours_is_refused(self):
        with self.assertRaises(BookingError) as caught:
            self.book(start=15, end=16)
        self.assertIn("outside the trainer", str(caught.exception))

    def test_a_blocked_day_is_refused(self):
        Unavailable.objects.create(trainer=self.trainer, date=self.day)
        with self.assertRaises(BookingError):
            self.book()

    def test_a_day_that_has_passed_is_refused(self):
        with self.assertRaises(BookingError) as caught:
            self.book(on=timezone.localdate() - timedelta(days=1))
        self.assertIn("been and gone", str(caught.exception))

    def test_a_trainer_cannot_book_themselves(self):
        with self.assertRaises(BookingError):
            self.book(member=self.trainer)

    def test_two_trainers_can_be_booked_for_the_same_hour(self):
        self.book()
        self.assertIsNotNone(self.book(member=self.rival, trainer=self.other_trainer).id)


class UtilisationTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.trainer = make_user("utilcoach", Role.TRAINER)
        self.member = make_user("utilmember")
        self.day = next_weekday(2)
        Availability.objects.create(
            trainer=self.trainer, weekday=2, start_time=time(9), end_time=time(12)
        )

    def test_booked_against_offered(self):
        book_session(
            trainer=self.trainer,
            member=self.member,
            on=self.day,
            start_time=time(9),
            end_time=time(10),
        )
        booked, offered = utilisation(self.trainer, self.day, self.day)
        self.assertEqual((booked, offered), (1.0, 3.0))

    def test_a_blocked_day_is_not_counted_as_offered(self):
        Unavailable.objects.create(trainer=self.trainer, date=self.day)
        booked, offered = utilisation(self.trainer, self.day, self.day)
        self.assertEqual(offered, 0.0)

    def test_a_cancelled_session_is_not_counted_as_booked(self):
        session = book_session(
            trainer=self.trainer,
            member=self.member,
            on=self.day,
            start_time=time(9),
            end_time=time(10),
        )
        cancel_session(session)
        booked, _ = utilisation(self.trainer, self.day, self.day)
        self.assertEqual(booked, 0.0)


class PTApiTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.trainer = make_user("apicoach", Role.TRAINER)
        self.member = make_user("apimember")
        self.other = make_user("apiother")
        self.admin = make_user("apiptadmin", Role.ADMIN)
        self.day = next_weekday(2)
        self.client.force_authenticate(self.trainer)
        self.client.post(
            "/api/pt/availability/",
            {"weekday": 2, "start_time": "09:00", "end_time": "12:00"},
        )

    def test_a_trainer_sets_their_own_hours(self):
        self.assertEqual(Availability.objects.filter(trainer=self.trainer).count(), 1)

    def test_a_trainer_cannot_set_someone_elses(self):
        other = make_user("victimcoach", Role.TRAINER)
        resp = self.client.post(
            "/api/pt/availability/",
            {"trainer": other.id, "weekday": 3, "start_time": "09:00", "end_time": "10:00"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_a_member_sees_the_open_slots(self):
        self.client.force_authenticate(self.member)
        resp = self.client.get(f"/api/pt/slots/?trainer={self.trainer.id}&date={self.day}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["results"]), 3)

    def test_a_member_books_a_slot(self):
        self.client.force_authenticate(self.member)
        resp = self.client.post(
            "/api/pt/sessions/",
            {
                "trainer": self.trainer.id,
                "member": self.member.id,
                "date": str(self.day),
                "start_time": "09:00",
                "end_time": "10:00",
            },
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["status"], "booked")
        self.assertEqual(resp.data["trainer_name"], "apicoach")

    def test_a_member_cannot_book_on_someone_elses_behalf(self):
        self.client.force_authenticate(self.member)
        resp = self.client.post(
            "/api/pt/sessions/",
            {
                "trainer": self.trainer.id,
                "member": self.other.id,
                "date": str(self.day),
                "start_time": "09:00",
                "end_time": "10:00",
            },
        )
        self.assertEqual(resp.status_code, 403)

    def test_a_taken_slot_comes_back_readably(self):
        book_session(
            trainer=self.trainer,
            member=self.other,
            on=self.day,
            start_time=time(9),
            end_time=time(10),
        )
        self.client.force_authenticate(self.member)
        resp = self.client.post(
            "/api/pt/sessions/",
            {
                "trainer": self.trainer.id,
                "member": self.member.id,
                "date": str(self.day),
                "start_time": "09:00",
                "end_time": "10:00",
            },
        )
        self.assertEqual(resp.status_code, 400)
        # The service's wording, not DRF's "must make a unique set".
        self.assertIn("just been taken", resp.data["detail"])

    def test_a_member_sees_only_their_own_sessions(self):
        book_session(
            trainer=self.trainer, member=self.other, on=self.day,
            start_time=time(9), end_time=time(10),
        )
        book_session(
            trainer=self.trainer, member=self.member, on=self.day,
            start_time=time(10), end_time=time(11),
        )
        self.client.force_authenticate(self.member)
        resp = self.client.get("/api/pt/sessions/")
        self.assertEqual(resp.data["count"], 1)

    def test_a_trainer_sees_their_whole_diary(self):
        book_session(
            trainer=self.trainer, member=self.other, on=self.day,
            start_time=time(9), end_time=time(10),
        )
        book_session(
            trainer=self.trainer, member=self.member, on=self.day,
            start_time=time(10), end_time=time(11),
        )
        self.client.force_authenticate(self.trainer)
        self.assertEqual(self.client.get("/api/pt/sessions/").data["count"], 2)

    def test_a_member_can_cancel_their_own(self):
        session = book_session(
            trainer=self.trainer, member=self.member, on=self.day,
            start_time=time(9), end_time=time(10),
        )
        self.client.force_authenticate(self.member)
        resp = self.client.post(f"/api/pt/sessions/{session.id}/cancel/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "cancelled")

    def test_only_the_trainer_closes_a_session_off(self):
        session = book_session(
            trainer=self.trainer, member=self.member, on=self.day,
            start_time=time(9), end_time=time(10),
        )
        self.client.force_authenticate(self.member)
        self.assertEqual(
            self.client.post(f"/api/pt/sessions/{session.id}/complete/").status_code, 403
        )

        self.client.force_authenticate(self.trainer)
        resp = self.client.post(
            f"/api/pt/sessions/{session.id}/complete/", {"is_paid": True}
        )
        self.assertEqual(resp.data["status"], "completed")
        self.assertTrue(resp.data["is_paid"])

    def test_a_no_show_is_recorded_as_one(self):
        session = book_session(
            trainer=self.trainer, member=self.member, on=self.day,
            start_time=time(9), end_time=time(10),
        )
        self.client.force_authenticate(self.trainer)
        resp = self.client.post(
            f"/api/pt/sessions/{session.id}/complete/", {"no_show": True}
        )
        self.assertEqual(resp.data["status"], "no_show")

    def test_status_cannot_be_set_straight_from_a_patch(self):
        session = book_session(
            trainer=self.trainer, member=self.member, on=self.day,
            start_time=time(9), end_time=time(10),
        )
        self.client.force_authenticate(self.member)
        self.client.patch(f"/api/pt/sessions/{session.id}/", {"status": "completed"})
        session.refresh_from_db()
        self.assertEqual(session.status, SessionStatus.BOOKED)
