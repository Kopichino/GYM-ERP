from datetime import date, time, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin, enrol

from accounts.models import MemberProfile, Role

from .models import Availability, PTSession, SessionStatus, Unavailable
from .services import BookingError, book_session, cancel_session, open_slots, utilisation

User = get_user_model()


def make_user(username, role=Role.MEMBER):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    MemberProfile.objects.get_or_create(user=user)
    enrol(user)
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


class DateParameterTests(TenantAPIMixin, APITestCase):
    """Dates reach these endpoints as query-string text.

    Slots parsed `date` with `date.fromisoformat` and the sessions list handed
    `from` and `to` straight to the ORM, so a malformed date was a 500. It is a
    400 naming the parameter; leaving the date out still means today.
    """

    def setUp(self):
        self.trainer = make_user("datecoach", Role.TRAINER)
        self.member = make_user("datemember")
        self.day = next_weekday(2)
        Availability.objects.create(
            trainer=self.trainer, weekday=2, start_time=time(9), end_time=time(12)
        )
        self.client.force_authenticate(self.member)

    def slots(self, **params):
        return self.client.get("/api/pt/slots/", {"trainer": self.trainer.id, **params})

    def test_a_malformed_date_is_a_400_on_date_not_a_500(self):
        for value in ("not-a-date", "2026-13-45", "2026-02-30", "15/09/2026"):
            with self.subTest(date=value):
                resp = self.slots(date=value)
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertEqual(list(resp.data), ["date"])

    def test_a_valid_date_still_answers_with_its_slots(self):
        resp = self.slots(date=self.day.isoformat())
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["date"], self.day)
        self.assertEqual(len(resp.data["results"]), 3)

    def test_a_blank_or_missing_date_means_today(self):
        # Today is pinned to a Wednesday ahead, so none of its hours have passed
        # whatever time the suite runs.
        with mock.patch("pt.views.timezone.localdate", return_value=self.day):
            for params in ({}, {"date": ""}):
                with self.subTest(params=params):
                    resp = self.slots(**params)
                    self.assertEqual(resp.status_code, 200, resp.content)
                    self.assertEqual(resp.data["date"], self.day)
                    self.assertEqual(len(resp.data["results"]), 3)

    def test_the_sessions_list_refuses_a_malformed_window_with_a_400(self):
        for params, field in (({"from": "not-a-date"}, "from"), ({"to": "2026-13-45"}, "to")):
            with self.subTest(params=params):
                resp = self.client.get("/api/pt/sessions/", params)
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertIn(field, resp.data)

    def test_the_sessions_list_still_filters_by_a_valid_window(self):
        later = self.day + timedelta(days=7)
        for on in (self.day, later):
            book_session(
                trainer=self.trainer, member=self.member, on=on,
                start_time=time(9), end_time=time(10),
            )
        day = self.day.isoformat()
        resp = self.client.get("/api/pt/sessions/", {"from": day, "to": day})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual([row["date"] for row in resp.data["results"]], [day])
        everything = self.client.get("/api/pt/sessions/", {"from": "", "to": ""})
        self.assertEqual(everything.data["count"], 2)


class TrainerParameterTests(TenantAPIMixin, APITestCase):
    """A trainer id reaches these endpoints as client text.

    Handed to the ORM as it came, "abc" or a blank raised a ValueError nobody
    caught -- a 500. A malformed id is a 400 naming `trainer`; a well-formed id
    that matches no trainer is still a 404, and a trainer naming someone else
    is still refused before any lookup.
    """

    MALFORMED = ("abc", "", " ", "0", "-3", "1.5", "7abc")
    OWN_ROWS = ("/api/pt/availability/", "/api/pt/unavailable/")

    def setUp(self):
        self.trainer = make_user("paramcoach", Role.TRAINER)
        self.member = make_user("parammember")
        self.admin = make_user("paramadmin", Role.ADMIN)
        self.day = next_weekday(2)
        Availability.objects.create(
            trainer=self.trainer, weekday=2, start_time=time(9), end_time=time(12)
        )
        Unavailable.objects.create(trainer=self.trainer, date=self.day + timedelta(days=7))

    def slots(self, trainer):
        return self.client.get(
            "/api/pt/slots/", {"trainer": trainer, "date": self.day.isoformat()}
        )

    def test_slots_refuse_a_malformed_trainer_with_a_400(self):
        self.client.force_authenticate(self.member)
        for value in self.MALFORMED:
            with self.subTest(trainer=value):
                resp = self.slots(value)
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertEqual(list(resp.data), ["trainer"])

    def test_slots_for_an_unknown_or_missing_trainer_are_still_a_404(self):
        self.client.force_authenticate(self.member)
        # A member is not a trainer, and an id past any integer column matches
        # no one either.
        for value in ("999999", str(self.member.id), "99999999999999999999"):
            with self.subTest(trainer=value):
                self.assertEqual(self.slots(value).status_code, 404)
        self.assertEqual(self.client.get("/api/pt/slots/").status_code, 404)

    def test_slots_for_a_real_trainer_still_work(self):
        self.client.force_authenticate(self.member)
        resp = self.slots(str(self.trainer.id))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["trainer"], self.trainer.id)
        self.assertEqual(len(resp.data["results"]), 3)

    def test_an_admin_naming_a_malformed_trainer_gets_a_400(self):
        # A blank is left out of these: here it has always meant "my own rows".
        self.client.force_authenticate(self.admin)
        for path in self.OWN_ROWS:
            for value in ("abc", " ", "0", "-3", "1.5"):
                with self.subTest(path=path, trainer=value):
                    resp = self.client.get(path, {"trainer": value})
                    self.assertEqual(resp.status_code, 400, resp.content)
                    self.assertEqual(list(resp.data), ["trainer"])

    def test_an_admin_posting_for_a_malformed_trainer_gets_a_400_and_saves_nothing(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/pt/availability/",
            {"trainer": "abc", "weekday": 3, "start_time": "09:00", "end_time": "10:00"},
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(list(resp.data), ["trainer"])
        self.assertFalse(Availability.objects.filter(weekday=3).exists())

    def test_an_admin_naming_an_unknown_trainer_gets_a_404(self):
        self.client.force_authenticate(self.admin)
        for path in self.OWN_ROWS:
            for value in ("999999", str(self.member.id)):
                with self.subTest(path=path, trainer=value):
                    self.assertEqual(self.client.get(path, {"trainer": value}).status_code, 404)

    def test_an_admin_naming_a_real_trainer_still_sees_their_rows(self):
        self.client.force_authenticate(self.admin)
        for path in self.OWN_ROWS:
            with self.subTest(path=path):
                resp = self.client.get(path, {"trainer": str(self.trainer.id)})
                self.assertEqual(resp.status_code, 200, resp.content)
                self.assertEqual(len(resp.data["results"]), 1)

    def test_a_trainer_naming_anyone_else_is_still_refused_before_any_lookup(self):
        self.client.force_authenticate(self.trainer)
        for value in ("abc", "999999"):
            with self.subTest(trainer=value):
                resp = self.client.get("/api/pt/availability/", {"trainer": value})
                self.assertEqual(resp.status_code, 403, resp.content)
        own = self.client.get("/api/pt/availability/", {"trainer": str(self.trainer.id)})
        self.assertEqual(own.status_code, 200, own.content)
        self.assertEqual(len(own.data["results"]), 1)
