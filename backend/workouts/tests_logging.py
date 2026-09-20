"""Logging a set: into the caller's own sessions only, and never a 500.

Every set logged from the Workouts page failed with a 500. The ownership check
in `WorkoutLogViewSet.perform_create` referred to `request` rather than
`self.request`, so it raised NameError before it could decide anything -- and
nothing exercised the endpoint, so no test noticed. These pin the happy path end
to end, and each refusal the check exists to make.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from accounts.models import MemberProfile, Role
from core.testing import TenantAPIMixin, founding_tenant
from tenancy import context
from tenancy.models import Membership

from .models import Exercise, WorkoutLog, WorkoutSession

User = get_user_model()


class WorkoutSetLoggingTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.exercise = Exercise.objects.create(name="Barbell Back Squat")
        self.member = self._person("lifter")
        self.other = self._person("other_member")
        self.trainer = self._person("coach", Role.TRAINER)
        self.admin = self._person("owner", Role.ADMIN)
        self.member.profile.trainer = self.trainer
        self.member.profile.save(update_fields=["trainer"])
        self.session = WorkoutSession.objects.create(user=self.member)
        self.others_session = WorkoutSession.objects.create(user=self.other)

    def _person(self, username, role=Role.MEMBER):
        user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password="pass12345", role=role
        )
        MemberProfile.objects.get_or_create(user=user)
        self.member_for(user, role)
        return user

    def log(self, session_id, *, set_number=1, reps=8, weight="60.00", exercise_id=None):
        return self.client.post(
            "/api/workouts/logs/",
            {
                "session": session_id,
                "exercise": exercise_id or self.exercise.pk,
                "set_number": set_number,
                "reps": reps,
                "weight": weight,
                "weight_unit": "kg",
            },
            format="json",
        )

    # -- the regression itself

    def test_a_member_logs_a_set_to_their_own_session(self):
        self.client.force_authenticate(self.member)
        resp = self.log(self.session.pk)

        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["exercise_name"], "Barbell Back Squat")
        entry = WorkoutLog.objects.get(pk=resp.data["id"])
        self.assertEqual(
            (entry.session_id, entry.exercise_id, entry.set_number, entry.reps, entry.weight, entry.weight_unit),
            (self.session.pk, self.exercise.pk, 1, 8, Decimal("60.00"), "kg"),
        )

    def test_consecutive_sets_are_each_kept_and_shown_on_the_session(self):
        self.client.force_authenticate(self.member)
        for number, reps in enumerate((10, 8, 6), start=1):
            self.assertEqual(self.log(self.session.pk, set_number=number, reps=reps).status_code, 201)

        self.assertEqual(
            list(
                WorkoutLog.objects.filter(session=self.session)
                .order_by("set_number")
                .values_list("set_number", "reps")
            ),
            [(1, 10), (2, 8), (3, 6)],
        )
        # The Workouts page reads the sets back off the session list.
        listing = self.client.get("/api/workouts/sessions/").data
        rows = listing["results"] if isinstance(listing, dict) else listing
        mine = next(row for row in rows if row["id"] == self.session.pk)
        self.assertEqual([log["reps"] for log in mine["logs"]], [10, 8, 6])

    # -- bad references fail as validation, not as a crash

    def test_a_session_that_does_not_exist_is_a_400(self):
        self.client.force_authenticate(self.member)
        resp = self.log(999_999)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("session", resp.data)
        self.assertFalse(WorkoutLog.objects.exists())

    def test_an_exercise_that_does_not_exist_is_a_400(self):
        self.client.force_authenticate(self.member)
        resp = self.log(self.session.pk, exercise_id=999_999)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("exercise", resp.data)
        self.assertFalse(WorkoutLog.objects.exists())

    def test_negative_reps_are_a_400(self):
        self.client.force_authenticate(self.member)
        resp = self.log(self.session.pk, reps=-1)
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(WorkoutLog.objects.exists())

    # -- who may log where

    def test_signing_in_is_required(self):
        self.assertEqual(self.log(self.session.pk).status_code, 401)
        self.assertFalse(WorkoutLog.objects.exists())

    def test_a_member_cannot_log_into_another_members_session(self):
        self.client.force_authenticate(self.member)
        resp = self.log(self.others_session.pk)
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(WorkoutLog.objects.filter(session=self.others_session).exists())

    def test_a_trainer_logs_for_a_member_assigned_to_them(self):
        self.client.force_authenticate(self.trainer)
        self.assertEqual(self.log(self.session.pk).status_code, 201)

    def test_a_trainer_cannot_log_for_a_member_they_do_not_train(self):
        self.client.force_authenticate(self.trainer)
        self.assertEqual(self.log(self.others_session.pk).status_code, 403)
        self.assertFalse(WorkoutLog.objects.filter(session=self.others_session).exists())

    def test_an_admin_logs_for_any_member_of_the_gym(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.log(self.others_session.pk).status_code, 201)

    def test_a_session_at_another_gym_cannot_be_logged_to_from_here(self):
        """An admin here is the dangerous case: every local check says yes."""
        _, elsewhere = founding_tenant("elsewhere")
        outsider = User.objects.create_user(
            username="outsider", email="outsider@example.com", password="pass12345"
        )
        Membership.objects.create(user=outsider, tenant=elsewhere, role=Role.MEMBER)
        with context.scope(elsewhere):
            foreign = WorkoutSession.objects.create(user=outsider)

        self.client.force_authenticate(self.admin)
        resp = self.log(foreign.pk)
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(WorkoutLog.unscoped.filter(session=foreign).exists())

    # -- editing a set that was already logged

    def test_a_logged_set_cannot_be_moved_into_another_members_session(self):
        entry = WorkoutLog.objects.create(
            session=self.session, exercise=self.exercise, set_number=1, reps=5
        )
        self.client.force_authenticate(self.member)
        resp = self.client.patch(
            f"/api/workouts/logs/{entry.pk}/", {"session": self.others_session.pk}, format="json"
        )
        self.assertEqual(resp.status_code, 403)
        entry.refresh_from_db()
        self.assertEqual(entry.session_id, self.session.pk)
        self.assertFalse(WorkoutLog.objects.filter(session=self.others_session).exists())

    def test_a_logged_set_can_still_be_corrected(self):
        entry = WorkoutLog.objects.create(
            session=self.session, exercise=self.exercise, set_number=1, reps=5
        )
        self.client.force_authenticate(self.member)
        resp = self.client.patch(f"/api/workouts/logs/{entry.pk}/", {"reps": 6}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        entry.refresh_from_db()
        self.assertEqual(entry.reps, 6)
