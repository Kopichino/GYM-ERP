"""A class has to end after it starts.

The class form accepted 19:00-18:00 and the API stored it. A class is one date
with a start and an end time -- there are no overnight classes -- so the end has
to be later than the start on that day. An equal start and end is refused too:
the same rule PT availability and PT bookings already hold ("has to end after
it starts").

Edits are checked against the stored row, so a PATCH that only moves one of the
two times cannot slip past. A PATCH that leaves both times alone is not refused
on their account, so an old row saved before this rule can still have its
capacity or description corrected.
"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from accounts.models import MemberProfile, Role
from core.testing import TenantAPIMixin, founding_tenant
from tenancy import context

from .models import ClassSession

User = get_user_model()

END_BEFORE_START = "A class has to end after it starts."


class ClassTimeValidationTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.trainer = self._person("coach", Role.TRAINER)
        self.admin = self._person("owner", Role.ADMIN)
        self.member = self._person("member")
        self.day = str(date.today() + timedelta(days=2))

    def _person(self, username, role=Role.MEMBER):
        user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password="pass12345", role=role
        )
        MemberProfile.objects.get_or_create(user=user)
        self.member_for(user, role)
        return user

    def payload(self, start, end, **extra):
        return {
            "title": "Spin",
            "date": self.day,
            "start_time": start,
            "end_time": end,
            "capacity": 10,
            "description": "",
            "trainer": None,
            **extra,
        }

    def create(self, user, start, end):
        self.client.force_authenticate(user)
        return self.client.post("/api/schedule/", self.payload(start, end), format="json")

    def assert_refused(self, resp):
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual([str(m) for m in resp.data["end_time"]], [END_BEFORE_START])

    def a_class(self, start="18:00", end="19:00", trainer=None):
        return ClassSession.objects.create(
            title="Yoga", trainer=trainer or self.trainer, date=self.day, start_time=start, end_time=end
        )

    # -- creating

    def test_a_class_that_ends_after_it_starts_is_created(self):
        for user in (self.trainer, self.admin):
            with self.subTest(user=user.username):
                self.assertEqual(self.create(user, "18:00", "19:00").status_code, 201)

    def test_a_class_one_minute_long_is_allowed(self):
        self.assertEqual(self.create(self.trainer, "18:00", "18:01").status_code, 201)

    def test_a_class_that_ends_before_it_starts_is_refused(self):
        for user in (self.trainer, self.admin):
            with self.subTest(user=user.username):
                self.assert_refused(self.create(user, "19:00", "18:00"))
        self.assertFalse(ClassSession.objects.exists())

    def test_a_class_that_ends_when_it_starts_is_refused(self):
        self.assert_refused(self.create(self.trainer, "18:00", "18:00"))
        self.assertFalse(ClassSession.objects.exists())

    def test_a_class_cannot_run_past_midnight(self):
        """One date per class: 23:00 to 01:00 would end before it starts."""
        self.assert_refused(self.create(self.admin, "23:00", "01:00"))

    # -- editing

    def test_moving_only_the_end_before_the_stored_start_is_refused(self):
        session = self.a_class()
        self.client.force_authenticate(self.trainer)
        resp = self.client.patch(f"/api/schedule/{session.pk}/", {"end_time": "17:30"}, format="json")
        self.assert_refused(resp)
        session.refresh_from_db()
        self.assertEqual(session.end_time.strftime("%H:%M"), "19:00")

    def test_moving_only_the_start_past_the_stored_end_is_refused(self):
        session = self.a_class()
        self.client.force_authenticate(self.admin)
        resp = self.client.patch(f"/api/schedule/{session.pk}/", {"start_time": "19:30"}, format="json")
        self.assert_refused(resp)
        session.refresh_from_db()
        self.assertEqual(session.start_time.strftime("%H:%M"), "18:00")

    def test_moving_both_times_to_a_valid_slot_is_saved(self):
        session = self.a_class()
        self.client.force_authenticate(self.trainer)
        resp = self.client.patch(
            f"/api/schedule/{session.pk}/", {"start_time": "07:00", "end_time": "08:00"}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        session.refresh_from_db()
        self.assertEqual(session.end_time.strftime("%H:%M"), "08:00")

    def test_an_old_backwards_class_can_still_have_other_details_corrected(self):
        legacy = self.a_class(start="19:00", end="18:00")
        self.client.force_authenticate(self.admin)
        resp = self.client.patch(f"/api/schedule/{legacy.pk}/", {"capacity": 12}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        resp = self.client.patch(f"/api/schedule/{legacy.pk}/", {"end_time": "20:00"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        legacy.refresh_from_db()
        self.assertEqual((legacy.capacity, legacy.end_time.strftime("%H:%M")), (12, "20:00"))

    def test_an_old_backwards_class_is_listed_without_error(self):
        self.a_class(start="19:00", end="18:00")
        self.client.force_authenticate(self.member)
        resp = self.client.get("/api/schedule/")
        self.assertEqual(resp.status_code, 200)

    # -- who and where

    # -- times that are not times at all

    def test_a_malformed_time_is_refused_as_a_bad_time_not_a_crash(self):
        self.client.force_authenticate(self.admin)
        for start, end, field in (("banana", "19:00", "start_time"), ("18:00", "half seven", "end_time")):
            with self.subTest(start=start, end=end):
                resp = self.client.post("/api/schedule/", self.payload(start, end), format="json")
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertIn(field, resp.data)

    def test_a_class_with_missing_or_blank_times_is_refused_naming_them(self):
        self.client.force_authenticate(self.admin)
        missing = self.payload("18:00", "19:00")
        missing.pop("start_time")
        missing.pop("end_time")
        blank = self.payload("", "")
        for payload in (missing, blank):
            with self.subTest(payload=sorted(payload)):
                resp = self.client.post("/api/schedule/", payload, format="json")
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertIn("start_time", resp.data)
                self.assertIn("end_time", resp.data)

    def test_a_member_cannot_create_a_class(self):
        self.assertEqual(self.create(self.member, "18:00", "19:00").status_code, 403)

    def test_a_trainer_cannot_retime_another_trainers_class(self):
        other = self._person("other_coach", Role.TRAINER)
        session = self.a_class(trainer=other)
        self.client.force_authenticate(self.trainer)
        resp = self.client.patch(
            f"/api/schedule/{session.pk}/", {"start_time": "07:00", "end_time": "08:00"}, format="json"
        )
        self.assertEqual(resp.status_code, 403)

    def test_another_gyms_class_cannot_be_retimed_from_here(self):
        _, elsewhere = founding_tenant("elsewhere")
        with context.scope(elsewhere):
            foreign = ClassSession.objects.create(
                title="Elsewhere", date=self.day, start_time="18:00", end_time="19:00"
            )
        self.client.force_authenticate(self.admin)
        resp = self.client.patch(f"/api/schedule/{foreign.pk}/", {"end_time": "17:00"}, format="json")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(ClassSession.unscoped.get(pk=foreign.pk).end_time.strftime("%H:%M"), "19:00")

    # -- the Django admin

    def test_the_django_admin_form_refuses_a_backwards_class(self):
        """The Django admin saves classes without going through the API
        serializer, so the model holds the rule too: the admin's own form
        refuses a backwards class, and still accepts a valid one."""
        from django.contrib import admin
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        request.user = self.admin
        self.admin.is_staff = self.admin.is_superuser = True
        form_class = admin.site._registry[ClassSession].get_form(request)

        def form(start, end):
            return form_class(
                data={
                    "tenant": self.tenant.pk,
                    "title": "Spin",
                    "date": self.day,
                    "start_time": start,
                    "end_time": end,
                    "capacity": 10,
                    "description": "",
                }
            )

        backwards = form("19:00", "18:00")
        self.assertFalse(backwards.is_valid())
        self.assertEqual(backwards.errors.get("end_time"), [END_BEFORE_START])
        valid = form("18:00", "19:00")
        self.assertTrue(valid.is_valid(), valid.errors)
