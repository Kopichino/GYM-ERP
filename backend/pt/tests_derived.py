"""Open slots at the endpoint, checked against slots worked out independently.

Availability is never stored as a slot table -- it is the trainer's weekly
window, minus blocked days, minus what is booked, recomputed on every read. So
the test that matters is not "does /slots/ answer 200" but "does it answer with
exactly the hours that are genuinely free", and the expected list here is built
from the window rather than copied from the response.
"""

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin, enrol

from accounts.models import MemberProfile, Role

from .models import Availability, SessionStatus, Unavailable
from .services import book_session, cancel_session

User = get_user_model()


def make_user(username, role=Role.MEMBER):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    if role == Role.MEMBER:
        MemberProfile.objects.get_or_create(user=user)
    enrol(user)
    return user


def next_weekday(weekday):
    day = timezone.localdate() + timedelta(days=1)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day


class OpenSlotsEndpointTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.trainer = make_user("slots_coach", Role.TRAINER)
        self.member = make_user("slots_member")
        self.day = next_weekday(2)  # a Wednesday, always in the future
        self.client.force_authenticate(self.member)

    def _window(self, start, end, weekday=2, trainer=None):
        return Availability.objects.create(
            trainer=trainer or self.trainer,
            weekday=weekday,
            start_time=start,
            end_time=end,
        )

    def _slots(self, on=None, trainer=None):
        resp = self.client.get(
            f"/api/pt/slots/?trainer={(trainer or self.trainer).id}&date={(on or self.day).isoformat()}"
        )
        self.assertEqual(resp.status_code, 200)
        return [row["start_time"] for row in resp.data["results"]]

    @staticmethod
    def _expected_hours(start_hour, end_hour, taken=()):
        """Every whole hour that fits in the window, less the taken ones."""
        return [
            f"{hour:02d}:00:00"
            for hour in range(start_hour, end_hour)
            if hour not in taken
        ]

    def test_a_window_becomes_the_hours_that_fit_in_it(self):
        self._window(time(9), time(12))
        # 09:00, 10:00, 11:00 -- 12:00 would end at 13:00, outside the window.
        self.assertEqual(self._slots(), self._expected_hours(9, 12))

    def test_a_tail_too_short_to_sell_is_dropped(self):
        self._window(time(9), time(10, 30))
        # The half hour after 10:00 cannot hold an hour-long session.
        self.assertEqual(self._slots(), self._expected_hours(9, 10))

    def test_a_booked_hour_disappears_from_the_list(self):
        self._window(time(9), time(13))
        book_session(
            trainer=self.trainer,
            member=self.member,
            on=self.day,
            start_time=time(10),
            end_time=time(11),
        )
        self.assertEqual(self._slots(), self._expected_hours(9, 13, taken={10}))

    def test_cancelling_puts_the_hour_back(self):
        self._window(time(9), time(13))
        session = book_session(
            trainer=self.trainer,
            member=self.member,
            on=self.day,
            start_time=time(10),
            end_time=time(11),
        )
        cancel_session(session)
        self.assertEqual(self._slots(), self._expected_hours(9, 13))

    def test_a_blocked_day_offers_nothing_at_all(self):
        self._window(time(9), time(17))
        Unavailable.objects.create(trainer=self.trainer, date=self.day)
        self.assertEqual(self._slots(), [])

    def test_two_windows_on_one_day_both_contribute(self):
        self._window(time(9), time(11))
        self._window(time(15), time(17))
        self.assertEqual(
            self._slots(), self._expected_hours(9, 11) + self._expected_hours(15, 17)
        )

    def test_the_list_comes_back_in_time_order(self):
        # Created out of order on purpose: the response must be sorted, since
        # the member portal renders it straight down the page.
        self._window(time(15), time(17))
        self._window(time(9), time(11))
        self.assertEqual(self._slots(), sorted(self._slots()))

    def test_another_trainers_window_is_not_offered(self):
        other = make_user("slots_coach2", Role.TRAINER)
        self._window(time(9), time(12))
        self._window(time(14), time(17), trainer=other)

        self.assertEqual(self._slots(), self._expected_hours(9, 12))
        self.assertEqual(self._slots(trainer=other), self._expected_hours(14, 17))

    def test_a_window_on_another_weekday_is_not_offered(self):
        self._window(time(9), time(12), weekday=(self.day.weekday() + 1) % 7)
        self.assertEqual(self._slots(), [])

    def test_an_inactive_window_offers_nothing(self):
        window = self._window(time(9), time(12))
        Availability.objects.filter(pk=window.pk).update(is_active=False)
        self.assertEqual(self._slots(), [])

    def test_a_day_in_the_past_offers_nothing(self):
        self._window(time(9), time(17))
        past = timezone.localdate() - timedelta(days=7)
        while past.weekday() != 2:
            past -= timedelta(days=1)
        self.assertEqual(self._slots(on=past), [])

    def test_the_booked_session_is_the_one_that_vanished(self):
        # Ties the two halves together: the hour missing from the list is the
        # same hour the session table says is sold.
        self._window(time(9), time(13))
        session = book_session(
            trainer=self.trainer,
            member=self.member,
            on=self.day,
            start_time=time(11),
            end_time=time(12),
        )
        offered = set(self._slots())
        self.assertNotIn("11:00:00", offered)
        self.assertEqual(session.status, SessionStatus.BOOKED)
        self.assertEqual(len(offered), 3)  # 9, 10, 12
