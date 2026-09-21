"""A trainer opening one member: only a member assigned to them, at this gym.

The trainer's member page read its member id from the URL and rendered the
workout logger, body stats and diet planner whether or not that id was one of
the trainer's members -- nothing on the page could say "not found", because the
only member data it had was the first page of the roster list. Each endpoint
behind it refused writes, but only after the trainer had been offered them.

This lookup is what the page now asks first: the trainer's own member, or a 404
that says nothing about whether the id exists anywhere else.
"""

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from accounts.models import MemberProfile, Role
from core.testing import TenantAPIMixin, founding_tenant
from tenancy.models import Membership

User = get_user_model()


class TrainerAndMembers(TenantAPIMixin, APITestCase):
    """Two trainers, a member assigned to each, and one assigned to nobody."""

    def setUp(self):
        self.trainer = self._person("coach", Role.TRAINER)
        self.other_trainer = self._person("other_coach", Role.TRAINER)
        self.mine = self._person("mine", first_name="Asha", last_name="Rao")
        self.unassigned = self._person("unassigned")
        self.theirs = self._person("theirs")
        self._assign(self.mine, self.trainer)
        self._assign(self.theirs, self.other_trainer)

    def _person(self, username, role=Role.MEMBER, **fields):
        user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password="pass12345", role=role, **fields
        )
        MemberProfile.objects.get_or_create(user=user)
        self.member_for(user, role)
        return user

    def _assign(self, member, trainer):
        member.profile.trainer = trainer
        member.profile.save(update_fields=["trainer"])


class TrainerMemberDetailTests(TrainerAndMembers):
    def detail(self, member_id, user=None):
        self.client.force_authenticate(user or self.trainer)
        return self.client.get(f"/api/auth/trainer/members/{member_id}/")

    def test_a_trainer_opens_a_member_assigned_to_them(self):
        resp = self.detail(self.mine.pk)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            (resp.data["id"], resp.data["username"], resp.data["first_name"], resp.data["last_name"]),
            (self.mine.pk, "mine", "Asha", "Rao"),
        )
        # The trainer's view of a member, not the admin's: no billing on it.
        self.assertNotIn("payments", resp.data)

    def test_an_id_that_does_not_exist_is_a_404(self):
        self.assertEqual(self.detail(999_999).status_code, 404)

    def test_a_member_not_assigned_to_anyone_is_a_404(self):
        self.assertEqual(self.detail(self.unassigned.pk).status_code, 404)

    def test_another_trainers_member_is_a_404(self):
        self.assertEqual(self.detail(self.theirs.pk).status_code, 404)

    def test_a_member_whose_standing_here_has_ended_is_a_404(self):
        Membership.objects.filter(user=self.mine, tenant=self.tenant).update(is_active=False)
        self.assertEqual(self.detail(self.mine.pk).status_code, 404)

    def test_a_member_assigned_to_them_at_another_gym_is_a_404(self):
        _, elsewhere = founding_tenant("elsewhere")
        outsider = User.objects.create_user(
            username="outsider", email="outsider@example.com", password="pass12345"
        )
        MemberProfile.objects.get_or_create(user=outsider)
        Membership.objects.create(user=outsider, tenant=elsewhere, role=Role.MEMBER)
        self._assign(outsider, self.trainer)
        self.assertEqual(self.detail(outsider.pk).status_code, 404)

    def test_only_a_trainer_uses_it(self):
        admin = self._person("owner", Role.ADMIN)
        for user in (self.mine, admin):
            with self.subTest(user=user.username):
                self.assertEqual(self.detail(self.mine.pk, user=user).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f"/api/auth/trainer/members/{self.mine.pk}/").status_code, 401)

    def test_the_roster_list_still_lists_only_their_members(self):
        self.client.force_authenticate(self.trainer)
        resp = self.client.get("/api/auth/trainer/members/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([row["id"] for row in resp.data["results"]], [self.mine.pk])


class EndpointsBehindTheMemberPageTests(TrainerAndMembers):
    """The page's lookup is only the front door. Every endpoint the member page
    reads from or writes to decides for itself, so calling one directly with a
    member id that is not the trainer's gets nothing -- and the same calls work
    for the trainer's own member, so these are not refusing everybody."""

    def setUp(self):
        super().setUp()
        from datetime import date

        from workouts.models import Exercise, WorkoutSession

        self.today = date.today().isoformat()
        self.exercise = Exercise.objects.create(name="Back Squat")
        self.sessions = {
            member.username: WorkoutSession.objects.create(user=member)
            for member in (self.mine, self.unassigned, self.theirs)
        }
        self.client.force_authenticate(self.trainer)

    def calls(self, member):
        """Each endpoint behind the page, as the page calls it for `member`."""
        session = self.sessions[member.username]
        return {
            "workout sessions": lambda: self.client.get(f"/api/workouts/sessions/?member={member.pk}"),
            "progress chart": lambda: self.client.get(
                f"/api/workouts/sessions/progress/?exercise={self.exercise.pk}&member={member.pk}"
            ),
            "start a session": lambda: self.client.post(
                "/api/workouts/sessions/", {"notes": "", "user": member.pk}, format="json"
            ),
            "log a set": lambda: self.client.post(
                "/api/workouts/logs/",
                {"session": session.pk, "exercise": self.exercise.pk, "set_number": 1, "reps": 5, "weight": "60"},
                format="json",
            ),
            "body stats summary": lambda: self.client.get(f"/api/bodystats/summary/?member={member.pk}"),
            "record a weigh-in": lambda: self.client.post(
                "/api/bodystats/measurements/",
                {"user": member.pk, "recorded_on": self.today, "weight_kg": "80.0"},
                format="json",
            ),
            "diet plans": lambda: self.client.get(f"/api/nutrition/plans/?member={member.pk}"),
        }

    def test_a_member_who_is_not_theirs_gets_nothing_from_any_of_them(self):
        from bodystats.models import BodyMeasurement
        from workouts.models import WorkoutLog, WorkoutSession

        for member in (self.unassigned, self.theirs):
            for label, call in self.calls(member).items():
                with self.subTest(member=member.username, call=label):
                    resp = call()
                    if label == "workout sessions":
                        # A filtered list: allowed, but empty.
                        self.assertEqual(resp.status_code, 200, resp.content)
                        self.assertEqual(resp.data["results"], [])
                    else:
                        self.assertEqual(resp.status_code, 403, resp.content)
            self.assertEqual(WorkoutSession.objects.filter(user=member).count(), 1)
            self.assertFalse(WorkoutLog.objects.filter(session__user=member).exists())
            self.assertFalse(BodyMeasurement.objects.filter(user=member).exists())

    def test_the_same_calls_work_for_their_own_member(self):
        expected = {
            "workout sessions": 200,
            "progress chart": 200,
            "start a session": 201,
            "log a set": 201,
            "body stats summary": 200,
            "record a weigh-in": 201,
            "diet plans": 200,
        }
        for label, call in self.calls(self.mine).items():
            with self.subTest(call=label):
                resp = call()
                self.assertEqual(resp.status_code, expected[label], resp.content)
