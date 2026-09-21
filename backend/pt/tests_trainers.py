"""The trainers a member can book, read off who trains at this gym."""

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from accounts.models import MemberProfile, Role
from core.testing import TenantAPIMixin

User = get_user_model()


def make(username, role):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    MemberProfile.objects.get_or_create(user=user)
    return user


class BookableTrainerListTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.here = make("coach_here", Role.TRAINER)
        self.here.first_name, self.here.last_name = "Ravi", "Kumar"
        self.here.save()
        # A trainer role on the user row, but never enrolled at this gym.
        self.elsewhere = make("coach_elsewhere", Role.TRAINER)
        self.member = make("member_here", Role.MEMBER)
        # Authenticating enrols an account at this test's gym.
        self.client.force_authenticate(self.here)
        self.client.force_authenticate(self.member)

    def test_lists_trainers_who_work_here_by_name(self):
        resp = self.client.get("/api/pt/trainers/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn({"id": self.here.id, "name": "Ravi Kumar"}, resp.data["results"])

    def test_a_trainer_from_another_gym_is_not_bookable_here(self):
        resp = self.client.get("/api/pt/trainers/")
        self.assertNotIn(self.elsewhere.id, [t["id"] for t in resp.data["results"]])
