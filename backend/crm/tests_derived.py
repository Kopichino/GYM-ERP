"""The at-risk list at the endpoint, checked against dates set in the test.

Nobody is stored as "quiet" or "cooling" -- the bands are derived on read from
the gap between today and each member's last check-in, against thresholds an
admin can change. So the tests seed visits a known number of days back, work
out from the policy which band that has to fall in, and assert the endpoint
agrees. Asserting 200 would pass just as well with everyone in the wrong band,
and this list is a call sheet somebody works through by hand.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from accounts.models import MembershipStatus, MemberProfile, Role
from attendance.models import CheckInOut

from .models import RetentionPolicy

User = get_user_model()


def make_user(username, role=Role.MEMBER, trainer=None, joined_days_ago=365):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    if role == Role.MEMBER:
        MemberProfile.objects.get_or_create(user=user)
        MemberProfile.objects.filter(user=user).update(
            trainer=trainer, join_date=timezone.localdate() - timedelta(days=joined_days_ago)
        )
    return User.objects.get(pk=user.pk)


class AtRiskEndpointTests(TenantAPIMixin, APITestCase):
    """Bands, ordering and scoping, all against known gaps."""

    QUIET_DAYS = 14
    COOLING_DAYS = 7
    GRACE_DAYS = 5

    def setUp(self):
        self.admin = make_user("risk_admin", Role.ADMIN)
        self.trainer = make_user("risk_trainer", Role.TRAINER)
        self.policy = RetentionPolicy.objects.create(
            quiet_days=self.QUIET_DAYS,
            cooling_days=self.COOLING_DAYS,
            grace_days=self.GRACE_DAYS,
        )
        self.today = timezone.localdate()
        self.client.force_authenticate(self.admin)

    def _visited(self, username, days_ago, **kwargs):
        member = make_user(username, **kwargs)
        visit = CheckInOut.objects.create(user=member)
        stamp = timezone.now() - timedelta(days=days_ago)
        CheckInOut.objects.filter(pk=visit.pk).update(
            check_in_time=stamp, check_out_time=stamp
        )
        return member

    def _rows(self):
        resp = self.client.get("/api/crm/at-risk/")
        self.assertEqual(resp.status_code, 200)
        return resp.data

    def _row_for(self, member):
        return next(
            (r for r in self._rows()["results"] if r["id"] == member.id), None
        )

    def _expected_band(self, days_ago):
        """The band the policy says a gap of this many days falls in."""
        if days_ago >= self.QUIET_DAYS:
            return "quiet"
        if days_ago >= self.COOLING_DAYS:
            return "cooling"
        return None

    def test_a_gap_past_the_quiet_threshold_reads_quiet(self):
        member = self._visited("risk_quiet", days_ago=20)
        row = self._row_for(member)

        self.assertEqual(self._expected_band(20), "quiet")
        self.assertEqual(row["band"], "quiet")
        self.assertEqual(row["days_since_visit"], 20)

    def test_a_gap_between_the_thresholds_reads_cooling(self):
        member = self._visited("risk_cooling", days_ago=9)
        row = self._row_for(member)

        self.assertEqual(self._expected_band(9), "cooling")
        self.assertEqual(row["band"], "cooling")
        self.assertEqual(row["days_since_visit"], 9)

    def test_the_boundary_day_counts_as_quiet_not_cooling(self):
        # Exactly on the threshold. Off by one here moves people between two
        # different scripts on the phone.
        member = self._visited("risk_boundary", days_ago=self.QUIET_DAYS)
        self.assertEqual(self._row_for(member)["band"], "quiet")

    def test_someone_inside_the_cooling_window_is_not_listed(self):
        member = self._visited("risk_recent", days_ago=self.COOLING_DAYS - 1)
        self.assertIsNone(self._expected_band(self.COOLING_DAYS - 1))
        self.assertIsNone(self._row_for(member))

    def test_a_brand_new_member_is_left_alone(self):
        # Inside the grace period they have not gone quiet, they have just not
        # been in yet, and chasing them on day two is worse than saying nothing.
        member = make_user("risk_new", joined_days_ago=self.GRACE_DAYS - 1)
        self.assertIsNone(self._row_for(member))

    def test_a_member_who_never_came_is_measured_from_joining(self):
        member = make_user("risk_never", joined_days_ago=30)
        row = self._row_for(member)

        self.assertTrue(row["never_visited"])
        self.assertIsNone(row["last_visit"])
        self.assertEqual(row["days_since_visit"], 30)
        self.assertEqual(row["band"], "quiet")

    def test_a_paused_member_is_not_chased(self):
        member = self._visited("risk_paused", days_ago=40)
        MemberProfile.objects.filter(user=member).update(
            membership_status=MembershipStatus.PAUSED
        )
        self.assertIsNone(self._row_for(member))

    def test_the_counts_match_the_rows_returned(self):
        self._visited("risk_c1", days_ago=8)
        self._visited("risk_c2", days_ago=10)
        self._visited("risk_q1", days_ago=30)

        data = self._rows()
        # Counted from the rows rather than trusted from the summary fields.
        quiet = sum(1 for r in data["results"] if r["band"] == "quiet")
        cooling = sum(1 for r in data["results"] if r["band"] == "cooling")
        self.assertEqual(data["quiet_count"], quiet)
        self.assertEqual(data["cooling_count"], cooling)
        self.assertEqual((quiet, cooling), (1, 2))

    def test_the_list_is_worst_first(self):
        self._visited("risk_a", days_ago=8)
        self._visited("risk_b", days_ago=40)
        self._visited("risk_c", days_ago=20)

        gaps = [r["days_since_visit"] for r in self._rows()["results"]]
        self.assertEqual(gaps, sorted(gaps, reverse=True))
        self.assertEqual(gaps, [40, 20, 8])

    def test_the_thresholds_in_the_response_are_the_policy_in_force(self):
        data = self._rows()
        self.assertEqual(data["quiet_days"], self.QUIET_DAYS)
        self.assertEqual(data["cooling_days"], self.COOLING_DAYS)
        self.assertEqual(data["grace_days"], self.GRACE_DAYS)

    def test_changing_the_policy_rebands_without_touching_a_member(self):
        # The bands are derived, so a new policy has to move people on the next
        # read -- nothing is stored against the member to migrate.
        member = self._visited("risk_reband", days_ago=10)
        self.assertEqual(self._row_for(member)["band"], "cooling")

        RetentionPolicy.objects.filter(pk=self.policy.pk).update(is_active=False)
        RetentionPolicy.objects.create(quiet_days=9, cooling_days=4, grace_days=5)

        self.assertEqual(self._row_for(member)["band"], "quiet")

    def test_a_trainer_sees_only_their_own_roster(self):
        mine = self._visited("risk_mine", days_ago=30, trainer=self.trainer)
        theirs = self._visited("risk_theirs", days_ago=30)

        self.client.force_authenticate(self.trainer)
        ids = {r["id"] for r in self._rows()["results"]}
        self.assertIn(mine.id, ids)
        self.assertNotIn(theirs.id, ids)

    def test_an_admin_sees_both_rosters(self):
        mine = self._visited("risk_admin_mine", days_ago=30, trainer=self.trainer)
        theirs = self._visited("risk_admin_theirs", days_ago=30)

        ids = {r["id"] for r in self._rows()["results"]}
        self.assertIn(mine.id, ids)
        self.assertIn(theirs.id, ids)
