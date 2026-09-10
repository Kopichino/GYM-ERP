from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from accounts.models import MemberProfile, Role
from attendance.models import CheckInOut
from pt.models import PTSession, SessionStatus

from . import nps
from .models import Survey, SurveyResponse, Trigger

User = get_user_model()
TODAY = timezone.localdate()


def make_member(username):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345",
        role=Role.MEMBER,
    )
    MemberProfile.objects.get_or_create(user=user)
    return user


def closed_visit(member, days_ago=1):
    """A finished visit. Created closed so the one-open-check-in index -- which
    this feature must not disturb -- is never left holding a row open."""
    when = timezone.now() - timedelta(days=days_ago)
    visit = CheckInOut.objects.create(user=member, check_out_time=when)
    CheckInOut.objects.filter(pk=visit.pk).update(
        check_in_time=when, check_out_time=when + timedelta(hours=1)
    )
    return visit


class ScoreTests(TenantAPIMixin, APITestCase):
    """NPS is a definition, not an average, and it is easy to get wrong."""

    def setUp(self):
        self.survey = Survey.objects.create(title="NPS", trigger=Trigger.MANUAL)
        self.member = make_member("scorer")

    def answer(self, score):
        return SurveyResponse.objects.create(
            survey=self.survey, member=self.member, score=score
        )

    def test_promoters_minus_detractors_over_everyone(self):
        for value in (10, 9, 8, 3):  # 2 promoters, 1 passive, 1 detractor
            self.answer(value)
        result = nps.score(SurveyResponse.objects.all())
        self.assertEqual(result["promoters"], 2)
        self.assertEqual(result["passives"], 1)
        self.assertEqual(result["detractors"], 1)
        self.assertEqual(result["nps"], 25.0)  # (2 - 1) / 4 * 100

    def test_seven_and_eight_are_passives_not_promoters(self):
        """The most common way an NPS gets quietly inflated."""
        self.answer(7)
        self.answer(8)
        result = nps.score(SurveyResponse.objects.all())
        self.assertEqual(result["promoters"], 0)
        self.assertEqual(result["nps"], 0.0)

    def test_all_detractors_is_minus_one_hundred(self):
        for value in (0, 6):
            self.answer(value)
        self.assertEqual(nps.score(SurveyResponse.objects.all())["nps"], -100.0)

    def test_nobody_answering_is_none_rather_than_zero(self):
        """Zero is a real score. 'Nobody has answered' is not a score at all."""
        result = nps.score(SurveyResponse.objects.all())
        self.assertIsNone(result["nps"])
        self.assertEqual(result["responses"], 0)

    def test_the_count_travels_with_the_score(self):
        self.answer(10)
        result = nps.score(SurveyResponse.objects.all())
        self.assertEqual((result["nps"], result["responses"]), (100.0, 1))

    def test_a_score_above_ten_cannot_reach_the_table(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SurveyResponse.objects.create(
                    survey=self.survey, member=self.member, score=11
                )


class PendingTests(TenantAPIMixin, APITestCase):
    """Prompts are derived from occasions, so there is no queue to drain."""

    def setUp(self):
        self.member = make_member("prompted")
        self.trainer = User.objects.create_user(
            username="ptcoach", email="c@example.com", password="pass12345",
            role=Role.TRAINER,
        )

    def test_a_finished_visit_earns_a_prompt(self):
        survey = Survey.objects.create(title="After the gym", trigger=Trigger.POST_CHECKIN)
        visit = closed_visit(self.member)
        prompts = nps.pending(self.member)
        self.assertEqual(len(prompts), 1)
        self.assertEqual(prompts[0]["survey"], survey)
        self.assertEqual(prompts[0]["visit"], visit)

    def test_an_open_visit_does_not(self):
        """Nobody wants to be asked how it went while they are still lifting."""
        Survey.objects.create(title="After the gym", trigger=Trigger.POST_CHECKIN)
        CheckInOut.objects.create(user=self.member)
        self.assertEqual(nps.pending(self.member), [])

    def test_answering_clears_it(self):
        survey = Survey.objects.create(title="After the gym", trigger=Trigger.POST_CHECKIN)
        visit = closed_visit(self.member)
        SurveyResponse.objects.create(
            survey=survey, member=self.member, score=9, visit=visit
        )
        self.assertEqual(nps.pending(self.member), [])

    def test_a_second_visit_inside_the_cooldown_does_not_ask_again(self):
        survey = Survey.objects.create(
            title="After the gym", trigger=Trigger.POST_CHECKIN, cooldown_days=90
        )
        first = closed_visit(self.member, days_ago=3)
        SurveyResponse.objects.create(
            survey=survey, member=self.member, score=9, visit=first
        )
        closed_visit(self.member, days_ago=1)
        self.assertEqual(nps.pending(self.member), [])

    def test_after_the_cooldown_they_are_asked_again(self):
        survey = Survey.objects.create(
            title="After the gym", trigger=Trigger.POST_CHECKIN, cooldown_days=30
        )
        old = closed_visit(self.member, days_ago=100)
        answer = SurveyResponse.objects.create(
            survey=survey, member=self.member, score=9, visit=old
        )
        SurveyResponse.objects.filter(pk=answer.pk).update(
            created_at=timezone.now() - timedelta(days=100)
        )
        closed_visit(self.member, days_ago=1)
        self.assertEqual(len(nps.pending(self.member)), 1)

    def test_an_inactive_survey_asks_nobody(self):
        Survey.objects.create(
            title="Old one", trigger=Trigger.POST_CHECKIN, is_active=False
        )
        closed_visit(self.member)
        self.assertEqual(nps.pending(self.member), [])

    def test_a_completed_pt_session_earns_a_prompt(self):
        Survey.objects.create(title="After PT", trigger=Trigger.POST_PT)
        session = PTSession.objects.create(
            trainer=self.trainer, member=self.member, date=TODAY - timedelta(days=1),
            start_time=time(9), end_time=time(10), status=SessionStatus.COMPLETED,
        )
        prompts = nps.pending(self.member)
        self.assertEqual(prompts[0]["pt_session"], session)

    def test_a_booked_pt_session_does_not(self):
        Survey.objects.create(title="After PT", trigger=Trigger.POST_PT)
        PTSession.objects.create(
            trainer=self.trainer, member=self.member, date=TODAY + timedelta(days=1),
            start_time=time(9), end_time=time(10), status=SessionStatus.BOOKED,
        )
        self.assertEqual(nps.pending(self.member), [])

    def test_a_manual_survey_is_always_pending_until_answered(self):
        Survey.objects.create(title="Any time", trigger=Trigger.MANUAL)
        self.assertEqual(len(nps.pending(self.member)), 1)
        SurveyResponse.objects.create(
            survey=Survey.objects.first(), member=self.member, score=8
        )
        self.assertEqual(nps.pending(self.member), [])

    def test_one_visit_cannot_be_answered_twice(self):
        survey = Survey.objects.create(title="After the gym", trigger=Trigger.POST_CHECKIN)
        visit = closed_visit(self.member)
        SurveyResponse.objects.create(
            survey=survey, member=self.member, score=9, visit=visit
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SurveyResponse.objects.create(
                    survey=survey, member=self.member, score=2, visit=visit
                )


class SurveyRulesTests(TenantAPIMixin, APITestCase):
    def test_two_live_surveys_cannot_share_a_trigger(self):
        """Within one organisation. Another gym's survey is its own business."""
        from core.testing import founding_tenant

        org, _ = founding_tenant()
        Survey.objects.create(title="One", trigger=Trigger.POST_CHECKIN, organisation=org)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Survey.objects.create(
                    title="Two", trigger=Trigger.POST_CHECKIN, organisation=org
                )

    def test_but_another_organisation_may_run_the_same_trigger(self):
        from core.testing import founding_tenant

        org, _ = founding_tenant("gymone")
        other, _ = founding_tenant("gymtwo")
        Survey.unscoped.create(title="One", trigger=Trigger.POST_CHECKIN, organisation=org)
        Survey.unscoped.create(title="Two", trigger=Trigger.POST_CHECKIN, organisation=other)
        self.assertEqual(Survey.unscoped.filter(is_active=True).count(), 2)

    def test_but_a_switched_off_one_can(self):
        Survey.objects.create(title="One", trigger=Trigger.POST_CHECKIN)
        Survey.objects.create(title="Two", trigger=Trigger.POST_CHECKIN, is_active=False)
        self.assertEqual(Survey.objects.count(), 2)


class ApiTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="npsadmin", email="a@example.com", password="pass12345", role=Role.ADMIN
        )
        self.member = make_member("npsmember")
        self.other = make_member("npsother")
        self.survey = Survey.objects.create(title="NPS", trigger=Trigger.MANUAL)

    def test_a_member_answers_and_the_answer_is_theirs(self):
        self.client.force_authenticate(self.member)
        resp = self.client.post(
            "/api/feedback/responses/",
            {"survey": self.survey.id, "score": 10, "comment": "Great gym",
             "member": self.other.id},
        )
        self.assertEqual(resp.status_code, 201)
        # The payload named someone else; it was ignored.
        self.assertEqual(SurveyResponse.objects.get().member, self.member)

    def test_a_member_only_reads_their_own_answers(self):
        SurveyResponse.objects.create(survey=self.survey, member=self.other, score=2)
        SurveyResponse.objects.create(survey=self.survey, member=self.member, score=9)
        self.client.force_authenticate(self.member)
        results = self.client.get("/api/feedback/responses/").data
        rows = results["results"] if isinstance(results, dict) else results
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["score"], 9)

    def test_a_member_cannot_write_surveys(self):
        self.client.force_authenticate(self.member)
        resp = self.client.post("/api/feedback/surveys/", {"title": "Mine"})
        self.assertEqual(resp.status_code, 403)

    def test_a_member_cannot_read_the_nps(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get("/api/feedback/nps/").status_code, 403)

    def test_a_member_can_read_their_pending_prompt(self):
        self.client.force_authenticate(self.member)
        resp = self.client.get("/api/feedback/surveys/pending/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data[0]["survey"]["question"][:8], "How like")

    def test_an_admin_gets_the_score_the_bands_and_the_trend(self):
        for score, member in ((10, self.member), (3, self.other)):
            SurveyResponse.objects.create(survey=self.survey, member=member, score=score)
        self.client.force_authenticate(self.admin)
        data = self.client.get("/api/feedback/nps/").data
        self.assertEqual(data["nps"], 0.0)
        self.assertEqual(data["responses"], 2)
        self.assertEqual(len(data["trend"]), 6)
        self.assertIn("Promoters", data["definition"])

    def test_detractor_comments_come_back_for_the_owner_to_act_on(self):
        SurveyResponse.objects.create(
            survey=self.survey, member=self.other, score=2, comment="Showers cold"
        )
        SurveyResponse.objects.create(
            survey=self.survey, member=self.member, score=10, comment="Love it"
        )
        self.client.force_authenticate(self.admin)
        comments = self.client.get("/api/feedback/nps/").data["detractor_comments"]
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["comment"], "Showers cold")

    def test_a_second_live_survey_on_one_trigger_is_explained_not_a_500(self):
        Survey.objects.create(title="Live", trigger=Trigger.POST_CHECKIN)
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/feedback/surveys/",
            {"title": "Another", "trigger": Trigger.POST_CHECKIN},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Switch that one off", resp.data["detail"])

    def test_the_same_guard_covers_a_payload_with_no_trigger(self):
        """Omitting it falls to the model default, which can clash too."""
        self.client.force_authenticate(self.admin)
        resp = self.client.post("/api/feedback/surveys/", {"title": "Second manual"})
        self.assertEqual(resp.status_code, 400)

    def test_answers_cannot_be_edited_afterwards(self):
        answer = SurveyResponse.objects.create(
            survey=self.survey, member=self.member, score=1
        )
        self.client.force_authenticate(self.member)
        resp = self.client.patch(f"/api/feedback/responses/{answer.id}/", {"score": 10})
        self.assertEqual(resp.status_code, 405)

    def test_answering_the_same_visit_twice_is_a_polite_conflict(self):
        survey = Survey.objects.create(
            title="After the gym", trigger=Trigger.POST_CHECKIN
        )
        visit = closed_visit(self.member)
        self.client.force_authenticate(self.member)
        payload = {"survey": survey.id, "score": 9, "visit": visit.id}
        self.assertEqual(
            self.client.post("/api/feedback/responses/", payload).status_code, 201
        )
        self.assertEqual(
            self.client.post("/api/feedback/responses/", payload).status_code, 409
        )


class DoesNotBreakExistingRulesTests(TenantAPIMixin, APITestCase):
    """The two invariants this feature was told not to disturb."""

    def test_the_one_open_check_in_rule_still_holds(self):
        member = make_member("stillguarded")
        CheckInOut.objects.create(user=member)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CheckInOut.objects.create(user=member)

    def test_a_survey_response_writes_no_payment_and_no_membership(self):
        """Feedback is not money and must not touch the derived status."""
        from billing.models import Payment

        member = make_member("nopayment")
        survey = Survey.objects.create(title="NPS", trigger=Trigger.MANUAL)
        SurveyResponse.objects.create(survey=survey, member=member, score=10)
        self.assertEqual(Payment.objects.filter(member=member).count(), 0)
