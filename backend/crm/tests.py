from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from accounts.models import MemberProfile, MembershipStatus, Role
from attendance.models import CheckInOut
from billing.models import PaymentMethod, Plan
from billing.services import record_payment
from referrals.models import Referral

from . import retention
from .models import Enquiry, EnquirySource, EnquiryStatus, RetentionPolicy

User = get_user_model()
TODAY = timezone.localdate()


def make_user(username, role):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    MemberProfile.objects.get_or_create(user=user)
    return user


class EnquiryAccessTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = make_user("admin", Role.ADMIN)
        self.trainer = make_user("trainer", Role.TRAINER)
        self.member = make_user("member", Role.MEMBER)

    def test_enquiries_are_admin_only(self):
        """Prospects aren't gym members -- nobody but an admin sees them."""
        for user in (self.member, self.trainer):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get("/api/crm/enquiries/").status_code, 403)
            self.assertEqual(self.client.get("/api/crm/enquiries/due/").status_code, 403)

    def test_anonymous_is_rejected(self):
        self.assertIn(self.client.get("/api/crm/enquiries/").status_code, (401, 403))

    def test_admin_creates_an_enquiry(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/crm/enquiries/",
            {"name": "Rohit Shetty", "phone": "+91 98200 12345", "follow_up_on": str(TODAY)},
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["status"], EnquiryStatus.OPEN)
        self.assertEqual(Enquiry.objects.get().created_by, self.admin)

    def test_a_nonsense_phone_is_rejected(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/crm/enquiries/",
            {"name": "Rohit", "phone": "call me", "follow_up_on": str(TODAY)},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("phone", resp.data)


class EnquiryReminderTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = make_user("admin", Role.ADMIN)
        self.client.force_authenticate(self.admin)

        self.today = self._enquiry("Due today", TODAY)
        self.overdue = self._enquiry("Missed", TODAY - timedelta(days=3))
        self.future = self._enquiry("Next week", TODAY + timedelta(days=7))
        self.done = self._enquiry("Already called", TODAY, EnquiryStatus.CONTACTED)

    def _enquiry(self, name, follow_up_on, status=EnquiryStatus.OPEN):
        return Enquiry.objects.create(
            name=name, phone="9876500000", follow_up_on=follow_up_on, status=status
        )

    def test_due_returns_today_and_overdue_only(self):
        data = self.client.get("/api/crm/enquiries/due/").data
        names = {row["name"] for row in data["results"]}

        self.assertEqual(names, {"Due today", "Missed"})
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["overdue_count"], 1)

    def test_a_future_callback_is_not_due_yet(self):
        self.assertFalse(self.future.is_due)
        self.assertEqual(self.future.days_overdue, 0)

    def test_a_contacted_enquiry_stops_being_due(self):
        self.assertFalse(self.done.is_due)

    def test_days_overdue_counts_from_the_callback_date(self):
        self.assertEqual(self.overdue.days_overdue, 3)
        self.assertEqual(self.today.days_overdue, 0)

    def test_marking_called_closes_it_off_the_due_list(self):
        resp = self.client.post(f"/api/crm/enquiries/{self.today.pk}/mark_called/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], EnquiryStatus.CONTACTED)
        self.assertEqual(resp.data["last_contacted_on"], str(TODAY))

        self.assertEqual(self.client.get("/api/crm/enquiries/due/").data["count"], 1)

    def test_marking_called_with_a_new_date_reschedules_and_stays_open(self):
        next_week = TODAY + timedelta(days=7)
        resp = self.client.post(
            f"/api/crm/enquiries/{self.today.pk}/mark_called/",
            {"follow_up_on": str(next_week)},
        )
        self.assertEqual(resp.data["status"], EnquiryStatus.OPEN)
        self.assertEqual(resp.data["follow_up_on"], str(next_week))
        # Logged as called today even though it stays open for later.
        self.assertEqual(resp.data["last_contacted_on"], str(TODAY))
        self.assertFalse(resp.data["is_due"])

    def test_follow_up_is_a_date_with_no_time_component(self):
        """The field is deliberately a date -- a submitted time is discarded
        rather than silently shifting the callback across a timezone."""
        resp = self.client.post(
            "/api/crm/enquiries/",
            {"name": "Timed", "phone": "9876500001", "follow_up_on": "2027-03-04"},
        )
        self.assertEqual(resp.data["follow_up_on"], "2027-03-04")
        self.assertNotIn("T", resp.data["follow_up_on"])

    def test_list_is_ordered_by_soonest_callback(self):
        rows = self.client.get("/api/crm/enquiries/").data["results"]
        dates = [row["follow_up_on"] for row in rows]
        self.assertEqual(dates, sorted(dates))

    def test_status_filter(self):
        resp = self.client.get("/api/crm/enquiries/?status=contacted")
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["name"], "Already called")


class PipelineTests(TenantAPIMixin, APITestCase):
    """The lead pipeline: source, assignment, trail, and conversion."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="pipeadmin", email="pa@example.com", password="pass12345", role=Role.ADMIN
        )
        self.client.force_authenticate(self.admin)
        self.plan = Plan.objects.create(name="Monthly", price=Decimal("1500"), duration_days=30)

    def make(self, **kwargs):
        defaults = {
            "name": "Ravi Menon",
            "phone": "+91 90000 11111",
            "follow_up_on": timezone.localdate(),
        }
        defaults.update(kwargs)
        return Enquiry.objects.create(**defaults)

    def test_source_and_interest_round_trip(self):
        resp = self.client.post(
            "/api/crm/enquiries/",
            {
                "name": "Asha Rao",
                "phone": "+91 90000 22222",
                "follow_up_on": str(timezone.localdate()),
                "source": EnquirySource.INSTAGRAM,
                "interested_in": self.plan.id,
            },
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["source_name"], "Instagram")
        self.assertEqual(resp.data["interested_in_name"], "Monthly")

    def test_filtering_by_source(self):
        self.make(source=EnquirySource.GOOGLE)
        self.make(name="Other", source=EnquirySource.WALK_IN)
        resp = self.client.get("/api/crm/enquiries/?source=google")
        self.assertEqual(resp.data["count"], 1)

    def test_notes_append_to_a_trail_rather_than_overwriting(self):
        enquiry = self.make()
        self.client.post(f"/api/crm/enquiries/{enquiry.id}/note/", {"body": "Left a voicemail."})
        self.client.post(f"/api/crm/enquiries/{enquiry.id}/note/", {"body": "Called back, keen."})
        resp = self.client.get(f"/api/crm/enquiries/{enquiry.id}/")
        self.assertEqual(len(resp.data["trail"]), 2)
        # Newest first, and the author is stamped from the request.
        self.assertEqual(resp.data["trail"][0]["body"], "Called back, keen.")
        self.assertEqual(resp.data["trail"][0]["author_name"], "pipeadmin")

    def test_an_empty_note_is_refused(self):
        enquiry = self.make()
        resp = self.client.post(f"/api/crm/enquiries/{enquiry.id}/note/", {"body": "   "})
        self.assertEqual(resp.status_code, 400)

    def test_convert_creates_a_member_and_stamps_the_enquiry(self):
        enquiry = self.make(email="ravi@example.com")
        resp = self.client.post(f"/api/crm/enquiries/{enquiry.id}/convert/")
        self.assertEqual(resp.status_code, 201)

        member = User.objects.get(pk=resp.data["user_id"])
        self.assertEqual(member.username, "ravi.menon")
        self.assertEqual(member.role, Role.MEMBER)
        self.assertEqual(member.first_name, "Ravi")
        self.assertEqual(member.last_name, "Menon")
        self.assertEqual(member.email, "ravi@example.com")
        # The phone follows them onto the profile rather than being retyped.
        self.assertEqual(member.profile.phone, enquiry.phone)
        # And no usable password: they set their own.
        self.assertFalse(member.has_usable_password())

        enquiry.refresh_from_db()
        self.assertEqual(enquiry.converted_user, member)
        self.assertEqual(enquiry.status, EnquiryStatus.JOINED)
        self.assertTrue(enquiry.is_converted)

    def test_converting_twice_is_refused(self):
        enquiry = self.make()
        self.client.post(f"/api/crm/enquiries/{enquiry.id}/convert/")
        resp = self.client.post(f"/api/crm/enquiries/{enquiry.id}/convert/")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("already been converted", resp.data["detail"])

    def test_a_taken_username_is_refused_rather_than_guessed_around(self):
        User.objects.create_user(username="taken", email="t@example.com", password="pass12345")
        enquiry = self.make()
        resp = self.client.post(
            f"/api/crm/enquiries/{enquiry.id}/convert/", {"username": "taken"}
        )
        self.assertEqual(resp.status_code, 400)
        enquiry.refresh_from_db()
        self.assertIsNone(enquiry.converted_user)

    def test_suggested_username_avoids_a_collision(self):
        User.objects.create_user(
            username="ravi.menon", email="r@example.com", password="pass12345"
        )
        enquiry = self.make()
        resp = self.client.get(f"/api/crm/enquiries/{enquiry.id}/suggested_username/")
        self.assertEqual(resp.data["username"], "ravi.menon2")

    def test_converting_a_referred_lead_closes_the_referral_loop(self):
        referrer = User.objects.create_user(
            username="sponsor2", email="s2@example.com", password="pass12345"
        )
        MemberProfile.objects.get_or_create(user=referrer)
        enquiry = self.make(name="Friend Of Sponsor", source=EnquirySource.REFERRAL)
        referral = Referral.objects.create(
            referrer=referrer, name=enquiry.name, phone=enquiry.phone, enquiry=enquiry
        )

        resp = self.client.post(f"/api/crm/enquiries/{enquiry.id}/convert/")
        self.assertEqual(resp.status_code, 201)
        referral.refresh_from_db()
        self.assertEqual(referral.referred_user_id, resp.data["user_id"])

    def test_pipeline_counts_are_read_live(self):
        self.make(source=EnquirySource.INSTAGRAM)
        second = self.make(name="Two", source=EnquirySource.INSTAGRAM)
        self.make(name="Three", source=EnquirySource.WALK_IN, status=EnquiryStatus.LOST)
        self.client.post(f"/api/crm/enquiries/{second.id}/convert/")

        resp = self.client.get("/api/crm/enquiries/pipeline/")
        self.assertEqual(resp.data["total"], 3)
        self.assertEqual(resp.data["converted"], 1)
        self.assertEqual(resp.data["conversion_rate"], 33.3)

        instagram = next(r for r in resp.data["by_source"] if r["source"] == "instagram")
        self.assertEqual(instagram["total"], 2)
        self.assertEqual(instagram["joined"], 1)
        self.assertEqual(instagram["conversion_rate"], 50.0)

        lost = next(r for r in resp.data["by_status"] if r["status"] == "lost")
        self.assertEqual(lost["count"], 1)

    def test_pipeline_is_honest_when_there_are_no_leads(self):
        resp = self.client.get("/api/crm/enquiries/pipeline/")
        self.assertEqual(resp.data["total"], 0)
        self.assertEqual(resp.data["conversion_rate"], 0.0)

    def test_members_cannot_reach_the_pipeline(self):
        member = User.objects.create_user(
            username="nosy", email="n@example.com", password="pass12345"
        )
        self.client.force_authenticate(member)
        self.assertEqual(self.client.get("/api/crm/enquiries/pipeline/").status_code, 403)


class AtRiskTests(TenantAPIMixin, APITestCase):
    """Who is at risk is derived on every read -- there is no flag to clear."""

    def setUp(self):
        self.admin = make_user("riskadmin", Role.ADMIN)
        self.trainer = make_user("riskcoach", Role.TRAINER)
        self.other_trainer = make_user("othercoach", Role.TRAINER)
        self.plan = Plan.objects.create(
            name="Monthly", price=Decimal("1500"), duration_days=30
        )
        RetentionPolicy.objects.create(quiet_days=10, cooling_days=5, grace_days=7)

    def member(self, username, *, joined_days_ago=60, trainer=None, status=None):
        user = make_user(username, Role.MEMBER)
        profile = MemberProfile.objects.get(user=user)
        profile.trainer = trainer
        if status:
            profile.membership_status = status
        profile.save()
        # `join_date` is auto_now_add, so it has to be forced past the default.
        MemberProfile.objects.filter(pk=profile.pk).update(
            join_date=TODAY - timedelta(days=joined_days_ago)
        )
        return user

    def visit(self, user, days_ago):
        record = CheckInOut.objects.create(user=user, check_out_time=timezone.now())
        CheckInOut.objects.filter(pk=record.pk).update(
            check_in_time=timezone.now() - timedelta(days=days_ago)
        )
        return record

    def rows_for(self, user=None):
        from tenancy.resolution import access_for

        # at_risk scopes on what the caller is *at this gym* -- a trainer sees
        # their own roster, an admin the whole branch. This class never touches
        # the API, so nothing has enrolled these users yet; without a Membership
        # they hold no roles and every caller would look like a stranger.
        caller = None
        if user is not None:
            self.member_for(user, user.role)
            caller = access_for(user, self.tenant)
        return {row["username"]: row for row in retention.at_risk(for_access=caller)}

    def test_a_member_in_this_week_is_not_listed(self):
        member = self.member("regular")
        self.visit(member, 2)
        self.assertNotIn("regular", self.rows_for())

    def test_a_member_gone_a_week_is_cooling(self):
        member = self.member("cooling")
        self.visit(member, 6)
        self.assertEqual(self.rows_for()["cooling"]["band"], "cooling")

    def test_a_member_gone_a_fortnight_is_quiet(self):
        member = self.member("quiet")
        self.visit(member, 14)
        row = self.rows_for()["quiet"]
        self.assertEqual(row["band"], "quiet")
        self.assertEqual(row["days_since_visit"], 14)

    def test_checking_in_takes_them_off_the_list_with_nothing_to_clear(self):
        member = self.member("returner")
        self.visit(member, 20)
        self.assertIn("returner", self.rows_for())

        CheckInOut.objects.filter(user=member).update(check_out_time=timezone.now())
        CheckInOut.objects.create(user=member)
        self.assertNotIn("returner", self.rows_for())

    def test_a_brand_new_member_is_left_alone(self):
        """Someone who joined three days ago has not gone quiet."""
        self.member("newjoiner", joined_days_ago=3)
        self.assertNotIn("newjoiner", self.rows_for())

    def test_a_member_who_never_came_is_measured_from_joining(self):
        self.member("noshow", joined_days_ago=30)
        row = self.rows_for()["noshow"]
        self.assertTrue(row["never_visited"])
        self.assertEqual(row["days_since_visit"], 30)
        self.assertIsNone(row["last_visit"])

    def test_a_paused_member_is_not_chased(self):
        member = self.member("onhold", status=MembershipStatus.PAUSED)
        self.visit(member, 40)
        self.assertNotIn("onhold", self.rows_for())

    def test_the_list_is_worst_first(self):
        for name, days in [("gone30", 30), ("gone8", 8), ("gone15", 15)]:
            self.visit(self.member(name), days)
        order = [row["username"] for row in retention.at_risk()]
        self.assertEqual(order, ["gone30", "gone15", "gone8"])

    def test_expiry_is_shown_alongside_so_the_call_can_be_a_renewal(self):
        member = self.member("lapsing")
        self.visit(member, 20)
        record_payment(
            member=member,
            plan=self.plan,
            amount=self.plan.price,
            method=PaymentMethod.CASH,
            paid_date=TODAY - timedelta(days=28),
        )
        row = self.rows_for()["lapsing"]
        self.assertEqual(row["expires_on"], TODAY + timedelta(days=2))
        self.assertEqual(row["days_left"], 2)

    def test_a_trainer_sees_only_their_own_roster(self):
        mine = self.member("mine", trainer=self.trainer)
        theirs = self.member("theirs", trainer=self.other_trainer)
        self.visit(mine, 20)
        self.visit(theirs, 20)

        self.assertEqual(set(self.rows_for(self.trainer)), {"mine"})
        self.assertEqual(set(self.rows_for(self.admin)), {"mine", "theirs"})

    def test_thresholds_come_from_the_policy(self):
        member = self.member("borderline")
        self.visit(member, 6)
        self.assertEqual(self.rows_for()["borderline"]["band"], "cooling")

        RetentionPolicy.objects.update(quiet_days=6, cooling_days=3)
        self.assertEqual(self.rows_for()["borderline"]["band"], "quiet")

    def test_defaults_apply_when_no_policy_has_been_set(self):
        RetentionPolicy.objects.all().delete()
        self.assertEqual(retention.thresholds(), retention.DEFAULTS)


class AtRiskApiTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = make_user("arapiadmin", Role.ADMIN)
        self.trainer = make_user("arapicoach", Role.TRAINER)
        self.member = make_user("arapimember", Role.MEMBER)
        MemberProfile.objects.filter(user=self.member).update(
            join_date=TODAY - timedelta(days=60)
        )

    def test_members_cannot_read_the_at_risk_list(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get("/api/crm/at-risk/").status_code, 403)

    def test_a_trainer_can(self):
        self.client.force_authenticate(self.trainer)
        resp = self.client.get("/api/crm/at-risk/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("results", resp.data)
        self.assertIn("quiet_count", resp.data)

    def test_the_admin_sees_the_thresholds_in_use(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get("/api/crm/at-risk/")
        self.assertEqual(resp.data["quiet_days"], retention.DEFAULTS["quiet_days"])

    def test_only_an_admin_changes_the_policy(self):
        self.client.force_authenticate(self.trainer)
        self.assertEqual(
            self.client.post("/api/crm/retention/", {"quiet_days": 20}).status_code, 403
        )

    def test_saving_a_policy_retires_the_previous_one(self):
        self.client.force_authenticate(self.admin)
        self.client.post("/api/crm/retention/", {"quiet_days": 14, "cooling_days": 7})
        self.client.post("/api/crm/retention/", {"quiet_days": 21, "cooling_days": 9})
        self.assertEqual(RetentionPolicy.objects.filter(is_active=True).count(), 1)
        self.assertEqual(RetentionPolicy.current().quiet_days, 21)

    def test_a_cooling_threshold_past_the_quiet_one_is_refused_readably(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post("/api/crm/retention/", {"quiet_days": 5, "cooling_days": 9})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("cooling_days", resp.data)
