"""The NPS summary reads its date window the way every report does.

It parsed `from` and `to` with `date.fromisoformat`, so a malformed date was a
500, and a `to` before `from` quietly answered with an empty summary. Leaving
either out still means no bound on that side.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import MemberProfile, Role
from core.testing import TenantAPIMixin

User = get_user_model()

TODAY = timezone.localdate()
END_BEFORE_START = "The end date is before the start date."


class NpsWindowTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="owner", email="owner@example.com", password="pass12345", role=Role.ADMIN
        )
        MemberProfile.objects.get_or_create(user=self.admin)
        self.member_for(self.admin, Role.ADMIN)
        self.client.force_authenticate(self.admin)

    def nps(self, **params):
        return self.client.get("/api/feedback/nps/", params)

    def test_no_window_a_valid_window_and_a_single_day_all_work(self):
        cases = [
            {},
            {"from": (TODAY - timedelta(days=30)).isoformat(), "to": TODAY.isoformat()},
            {"from": TODAY.isoformat(), "to": TODAY.isoformat()},
            {"from": (TODAY - timedelta(days=7)).isoformat()},
            {"to": TODAY.isoformat()},
        ]
        for params in cases:
            with self.subTest(params=params):
                self.assertEqual(self.nps(**params).status_code, 200)

    def test_a_malformed_date_is_a_400_on_that_parameter_not_a_500(self):
        for params, field in (({"from": "2026-13-45"}, "from"), ({"to": "yesterday"}, "to")):
            with self.subTest(params=params):
                resp = self.nps(**params)
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertIn(field, resp.data)

    def test_a_to_date_before_the_from_date_is_refused(self):
        resp = self.nps(**{"from": TODAY.isoformat(), "to": (TODAY - timedelta(days=1)).isoformat()})
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual([str(m) for m in resp.data["to"]], [END_BEFORE_START])

    def test_only_an_admin_reads_it(self):
        member = User.objects.create_user(username="member", email="member@example.com", password="pass12345")
        self.member_for(member, Role.MEMBER)
        self.client.force_authenticate(member)
        self.assertEqual(self.nps().status_code, 403)
