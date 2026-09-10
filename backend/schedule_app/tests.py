from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from accounts.models import MemberProfile, Role
from instructors.models import Instructor

from .models import BookingStatus, ClassBooking, ClassSession
from .services import BookingError, book, cancel

User = get_user_model()


def make_user(username, role=Role.MEMBER):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    MemberProfile.objects.get_or_create(user=user)
    return user


def make_class(capacity=2, days_ahead=3, instructor=None):
    return ClassSession.objects.create(
        title="Spin",
        instructor=instructor,
        date=date.today() + timedelta(days=days_ahead),
        start_time=time(18, 0),
        end_time=time(19, 0),
        capacity=capacity,
    )


class BookingRuleTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.session = make_class(capacity=2)
        self.a = make_user("alice")
        self.b = make_user("bob")
        self.c = make_user("carol")

    def test_booking_takes_a_seat(self):
        booking = book(self.session.pk, self.a)
        self.assertEqual(booking.status, BookingStatus.BOOKED)
        self.assertIsNone(booking.position)

    def test_double_booking_is_refused(self):
        book(self.session.pk, self.a)
        with self.assertRaises(BookingError):
            book(self.session.pk, self.a)

    def test_capacity_pushes_the_overflow_onto_the_waitlist(self):
        book(self.session.pk, self.a)
        book(self.session.pk, self.b)
        third = book(self.session.pk, self.c)

        self.assertEqual(third.status, BookingStatus.WAITLISTED)
        self.assertEqual(third.position, 1)
        self.assertEqual(
            self.session.bookings.filter(status=BookingStatus.BOOKED).count(), 2
        )

    def test_capacity_is_never_exceeded(self):
        for i in range(6):
            book(self.session.pk, make_user(f"m{i}"))
        self.assertLessEqual(
            self.session.bookings.filter(status=BookingStatus.BOOKED).count(),
            self.session.capacity,
        )

    def test_cancelling_promotes_the_first_waitlister(self):
        book(self.session.pk, self.a)
        book(self.session.pk, self.b)
        book(self.session.pk, self.c)  # waitlisted

        _, promoted = cancel(self.session.pk, self.a)
        self.assertIsNotNone(promoted)
        self.assertEqual(promoted.member, self.c)
        self.assertEqual(promoted.status, BookingStatus.BOOKED)
        self.assertIsNone(promoted.position)

    def test_cancelling_a_waitlisted_place_promotes_nobody(self):
        book(self.session.pk, self.a)
        book(self.session.pk, self.b)
        book(self.session.pk, self.c)

        _, promoted = cancel(self.session.pk, self.c)
        self.assertIsNone(promoted)

    def test_rebooking_after_cancelling_reuses_the_row(self):
        book(self.session.pk, self.a)
        cancel(self.session.pk, self.a)
        again = book(self.session.pk, self.a)

        self.assertEqual(again.status, BookingStatus.BOOKED)
        self.assertEqual(ClassBooking.objects.filter(member=self.a, session=self.session).count(), 1)

    def test_cancelling_without_a_place_is_refused(self):
        with self.assertRaises(BookingError):
            cancel(self.session.pk, self.a)

    def test_past_classes_cannot_be_booked(self):
        past = make_class(capacity=5, days_ahead=-1)
        with self.assertRaises(BookingError):
            book(past.pk, self.a)

    def test_uncapped_class_never_waitlists(self):
        uncapped = make_class(capacity=None)
        for i in range(5):
            self.assertEqual(book(uncapped.pk, make_user(f"u{i}")).status, BookingStatus.BOOKED)

    def test_one_booking_per_member_per_class_is_enforced_by_the_database(self):
        book(self.session.pk, self.a)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ClassBooking.objects.create(member=self.a, session=self.session)


class BookingApiTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.trainer = make_user("trainer", Role.TRAINER)
        self.profile = Instructor.objects.create(user=self.trainer, name="Coach")
        self.other_trainer = make_user("trainer2", Role.TRAINER)
        Instructor.objects.create(user=self.other_trainer, name="Other Coach")
        self.admin = make_user("admin", Role.ADMIN)
        self.member = make_user("member")
        self.session = make_class(capacity=1, instructor=self.profile)

    def test_member_books_and_cancels_over_the_api(self):
        self.client.force_authenticate(self.member)

        booked = self.client.post(f"/api/schedule/{self.session.pk}/book/")
        self.assertEqual(booked.status_code, 201)
        self.assertEqual(booked.data["status"], BookingStatus.BOOKED)

        cancelled = self.client.post(f"/api/schedule/{self.session.pk}/cancel/")
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.data["booking"]["status"], BookingStatus.CANCELLED)

    def test_double_booking_returns_a_readable_message(self):
        self.client.force_authenticate(self.member)
        self.client.post(f"/api/schedule/{self.session.pk}/book/")
        resp = self.client.post(f"/api/schedule/{self.session.pk}/book/")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("already booked", resp.data["detail"])

    def test_schedule_list_reports_seats_and_my_status(self):
        self.client.force_authenticate(self.member)
        self.client.post(f"/api/schedule/{self.session.pk}/book/")

        row = self.client.get("/api/schedule/").data["results"][0]
        self.assertEqual(row["booked_count"], 1)
        self.assertEqual(row["spots_left"], 0)
        self.assertEqual(row["my_status"], BookingStatus.BOOKED)

    def test_my_status_is_null_for_someone_elses_booking(self):
        self.client.force_authenticate(self.member)
        self.client.post(f"/api/schedule/{self.session.pk}/book/")

        self.client.force_authenticate(make_user("bystander"))
        row = self.client.get("/api/schedule/").data["results"][0]
        self.assertIsNone(row["my_status"])
        self.assertEqual(row["booked_count"], 1)

    def test_my_bookings_lists_only_my_own(self):
        other = make_user("other")
        self.client.force_authenticate(other)
        self.client.post(f"/api/schedule/{self.session.pk}/book/")

        self.client.force_authenticate(self.member)
        resp = self.client.get("/api/schedule/my-bookings/")
        self.assertEqual(resp.data["count"], 0)

    def test_roster_is_visible_to_the_classes_own_trainer(self):
        self.client.force_authenticate(self.member)
        self.client.post(f"/api/schedule/{self.session.pk}/book/")

        self.client.force_authenticate(self.trainer)
        resp = self.client.get(f"/api/schedule/{self.session.pk}/roster/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)

    def test_roster_is_hidden_from_another_trainer_and_from_members(self):
        for user in (self.other_trainer, self.member):
            self.client.force_authenticate(user)
            resp = self.client.get(f"/api/schedule/{self.session.pk}/roster/")
            self.assertEqual(resp.status_code, 403)

    def test_admin_can_read_any_roster(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get(f"/api/schedule/{self.session.pk}/roster/")
        self.assertEqual(resp.status_code, 200)

    def test_trainer_marks_attendance(self):
        self.client.force_authenticate(self.member)
        self.client.post(f"/api/schedule/{self.session.pk}/book/")

        self.client.force_authenticate(self.trainer)
        resp = self.client.post(
            f"/api/schedule/{self.session.pk}/attendance/", {"member_ids": [self.member.pk]}
        )
        self.assertEqual(resp.data["marked_attended"], 1)
        self.assertEqual(
            ClassBooking.objects.get(member=self.member).status, BookingStatus.ATTENDED
        )


class AttendanceEncodingTests(TenantAPIMixin, APITestCase):
    """`member_ids` has to survive whichever way the body was encoded.

    A form-encoded body arrives as a QueryDict, and reading it with `.get()`
    returned the last value as a string. Fed to an `__in` lookup that iterates
    into its characters, so a two-digit id matched nobody and the endpoint
    answered 200 with nothing marked. Ids under ten happened to work, which is
    the only reason it stayed hidden.
    """

    def setUp(self):
        self.trainer = make_user("enc_trainer", Role.TRAINER)
        self.instructor = Instructor.objects.create(name="Enc Coach", user=self.trainer)
        self.session = ClassSession.objects.create(
            title="Spin",
            instructor=self.instructor,
            date=timezone.localdate() + timedelta(days=1),
            start_time=time(9),
            end_time=time(10),
            capacity=10,
        )

    def _member_with_a_two_digit_id(self):
        """Burn ids until the next member is >= 10, reproducing the real case."""
        member = make_user("enc_member")
        while member.pk < 10:
            member = make_user(f"enc_filler_{member.pk}")
        return member

    def _book_and_mark(self, member, **post_kwargs):
        self.client.force_authenticate(member)
        self.client.post(f"/api/schedule/{self.session.pk}/book/")
        self.client.force_authenticate(self.trainer)
        return self.client.post(
            f"/api/schedule/{self.session.pk}/attendance/",
            {"member_ids": [member.pk]},
            **post_kwargs,
        )

    def test_a_json_body_marks_the_member(self):
        member = self._member_with_a_two_digit_id()
        resp = self._book_and_mark(member, format="json")

        self.assertEqual(resp.data["marked_attended"], 1)
        self.assertEqual(
            ClassBooking.objects.get(member=member).status, BookingStatus.ATTENDED
        )

    def test_a_form_encoded_body_marks_the_member_too(self):
        member = self._member_with_a_two_digit_id()
        self.assertGreaterEqual(member.pk, 10, "the id has to be multi-digit to bite")
        resp = self._book_and_mark(member)

        self.assertEqual(resp.data["marked_attended"], 1)
        self.assertEqual(
            ClassBooking.objects.get(member=member).status, BookingStatus.ATTENDED
        )

    def test_several_members_are_marked_at_once(self):
        members = [self._member_with_a_two_digit_id()]
        members.append(make_user("enc_second"))
        for member in members:
            self.client.force_authenticate(member)
            self.client.post(f"/api/schedule/{self.session.pk}/book/")

        self.client.force_authenticate(self.trainer)
        resp = self.client.post(
            f"/api/schedule/{self.session.pk}/attendance/",
            {"member_ids": [m.pk for m in members]},
            format="json",
        )
        self.assertEqual(resp.data["marked_attended"], 2)

    def test_an_empty_list_marks_nobody_without_erroring(self):
        self.client.force_authenticate(self.trainer)
        resp = self.client.post(
            f"/api/schedule/{self.session.pk}/attendance/", {"member_ids": []}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["marked_attended"], 0)

    def test_a_missing_key_marks_nobody_without_erroring(self):
        self.client.force_authenticate(self.trainer)
        resp = self.client.post(f"/api/schedule/{self.session.pk}/attendance/", {}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["marked_attended"], 0)
