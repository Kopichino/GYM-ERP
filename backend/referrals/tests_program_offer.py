"""Editing the referral offer: it saves, it stays saved, and it stays one offer.

What the audit saw -- 11 saved, 15 back after a reload -- was the page, not the
database. The save went through, but the form's fields started from a hard-coded
15 and an empty message on every load rather than from the offer running, and
because the page could only create, every save added another programme row.

The page now edits the running offer in place. These pin that path, and the two
ways a programme save could still break the one-running-offer rule and escape as
a 500: switching an old offer back on, and two new offers racing each other.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from rest_framework.test import APITestCase

from accounts.models import MemberProfile, Role
from billing.models import PaymentMethod, Plan
from billing.services import record_payment
from core.testing import (
    TenantAPIMixin,
    founding_tenant,
    losers,
    requires_row_locks,
    run_concurrently,
    winners,
)
from tenancy import context

from .models import Referral, ReferralProgram
from .serializers import ReferralProgramSerializer
from .services import grant_reward

User = get_user_model()


class ReferralOfferEditingTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = self._person("owner", Role.ADMIN)
        self.member = self._person("member")
        self.offer = ReferralProgram.objects.create(reward_days=15, blurb="Bring a friend.")

    def _person(self, username, role=Role.MEMBER):
        user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password="pass12345", role=role
        )
        MemberProfile.objects.get_or_create(user=user)
        self.member_for(user, role)
        return user

    def edit(self, program, user=None, **fields):
        self.client.force_authenticate(user or self.admin)
        return self.client.patch(f"/api/referrals/programs/{program.pk}/", fields, format="json")

    def running(self):
        self.client.force_authenticate(self.admin)
        rows = self.client.get("/api/referrals/programs/").data["results"]
        return [(row["id"], row["reward_days"], row["blurb"]) for row in rows if row["is_active"]]

    # -- saving and reading back

    def test_the_first_offer_is_created_and_runs(self):
        self.offer.delete()
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/referrals/programs/", {"reward_days": 20, "blurb": "Twenty days"}, format="json"
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(self.running(), [(resp.data["id"], 20, "Twenty days")])

    def test_editing_the_running_offer_saves_in_place(self):
        resp = self.edit(self.offer, reward_days=11, blurb="Eleven days on us.")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(ReferralProgram.objects.count(), 1)
        self.assertEqual(self.running(), [(self.offer.pk, 11, "Eleven days on us.")])

    def test_the_saved_offer_is_what_everyone_reads_afterwards(self):
        self.edit(self.offer, reward_days=11, blurb="Eleven days on us.")
        self.assertEqual(ReferralProgram.current().reward_days, 11)
        self.client.force_authenticate(self.member)
        mine = self.client.get("/api/referrals/mine/").data
        self.assertEqual((mine["reward_days"], mine["blurb"], mine["program_active"]), (11, "Eleven days on us.", True))

    def test_saving_twice_still_leaves_one_offer(self):
        self.edit(self.offer, reward_days=11)
        self.edit(self.offer, reward_days=12)
        self.assertEqual(ReferralProgram.objects.count(), 1)
        self.assertEqual(ReferralProgram.current().reward_days, 12)

    def test_switching_an_old_offer_back_on_retires_the_running_one(self):
        """Was an IntegrityError on the one-running-offer index: a 500."""
        old = ReferralProgram.objects.create(reward_days=7, blurb="Old offer", is_active=False)
        resp = self.edit(old, is_active=True)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self.running(), [(old.pk, 7, "Old offer")])
        self.offer.refresh_from_db()
        self.assertFalse(self.offer.is_active)

    def test_switching_the_offer_off_leaves_none_running(self):
        self.assertEqual(self.edit(self.offer, is_active=False).status_code, 200)
        self.assertEqual(self.running(), [])
        self.assertIsNone(ReferralProgram.current())

    def test_creating_a_new_programme_still_retires_the_previous_one(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post("/api/referrals/programs/", {"reward_days": 30}, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(self.running(), [(resp.data["id"], 30, "")])
        self.assertEqual(ReferralProgram.objects.count(), 2)

    def test_bad_values_are_refused_and_nothing_changes(self):
        for value in ("abc", -1):
            with self.subTest(reward_days=value):
                self.assertEqual(self.edit(self.offer, reward_days=value).status_code, 400)
        self.assertEqual(self.running(), [(self.offer.pk, 15, "Bring a friend.")])

    def test_an_offer_of_no_free_days_is_refused(self):
        """Nothing to give is not an offer: granting a reward treats 0 days as no
        programme running, and members would be told they get 0 free days."""
        resp = self.edit(self.offer, reward_days=0)
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("reward_days", resp.data)
        self.client.force_authenticate(self.admin)
        resp = self.client.post("/api/referrals/programs/", {"reward_days": 0}, format="json")
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("reward_days", resp.data)
        self.assertEqual(self.running(), [(self.offer.pk, 15, "Bring a friend.")])
        self.assertEqual(ReferralProgram.objects.count(), 1)

    # -- history

    def test_past_referrals_and_rewards_are_untouched(self):
        plan = Plan.objects.create(name="Monthly", price=Decimal("1500"), duration_days=30)
        referrer, joiner = self._person("giver"), self._person("taker")
        for person in (referrer, joiner):
            record_payment(member=person, plan=plan, amount=plan.price, method=PaymentMethod.CASH)
        referral = Referral.objects.create(referrer=referrer, name="Taker", referred_user=joiner)
        reward = grant_reward(referral, granted_by=self.admin)

        self.edit(self.offer, reward_days=11)
        self.client.post("/api/referrals/programs/", {"reward_days": 30}, format="json")

        reward.refresh_from_db()
        referral.refresh_from_db()
        self.assertEqual(reward.days_granted, 15)
        self.assertEqual((referral.referrer, referral.referred_user), (referrer, joiner))
        self.assertEqual(Referral.objects.count(), 1)

    # -- who and where

    def test_only_an_admin_here_can_change_the_offer(self):
        trainer = self._person("coach", Role.TRAINER)
        for user in (self.member, trainer):
            with self.subTest(user=user.username):
                self.assertEqual(self.edit(self.offer, user=user, reward_days=90).status_code, 403)
        self.client.force_authenticate(None)
        resp = self.client.patch(
            f"/api/referrals/programs/{self.offer.pk}/", {"reward_days": 90}, format="json"
        )
        self.assertEqual(resp.status_code, 401)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.reward_days, 15)

    def test_another_brands_offer_is_neither_listed_nor_editable(self):
        _, elsewhere = founding_tenant("elsewhere")
        with context.scope(elsewhere):
            foreign = ReferralProgram.objects.create(reward_days=99, blurb="Theirs")
        self.assertNotIn(foreign.pk, [row[0] for row in self.running()])
        self.assertEqual(self.edit(foreign, reward_days=1).status_code, 404)
        self.assertEqual(ReferralProgram.unscoped.get(pk=foreign.pk).reward_days, 99)


@requires_row_locks
class SimultaneousNewOffersTests(TransactionTestCase):
    """Two admins starting a new offer at the same instant. Both retire nothing
    (neither sees the other's row yet), and the one-running-offer index would
    stop the second with an IntegrityError -- unless the saves queue."""

    def setUp(self):
        super().setUp()
        _, self.tenant = founding_tenant("offergym")
        self._scope_token = context.set(self.tenant)

    def tearDown(self):
        context.reset(self._scope_token)
        super().tearDown()

    def test_two_new_offers_at_once_leave_exactly_one_running(self):
        from .services import save_programme

        def start(index):
            form = ReferralProgramSerializer(data={"reward_days": 10 + index, "blurb": ""})
            form.is_valid(raise_exception=True)
            return save_programme(form).pk

        results = run_concurrently(start, count=2)

        self.assertEqual(len(winners(results)), 2, losers(results))
        self.assertEqual(ReferralProgram.objects.filter(is_active=True).count(), 1)


@requires_row_locks
class EditingDuringANewOfferTests(TransactionTestCase):
    """One admin edits the running offer while another starts a new one.

    The edit loads the running offer before the new one retires it. Saving that
    stale copy would write is_active back to True -- a second running offer,
    which the one-running-offer index refuses with an IntegrityError: a 500.
    """

    def setUp(self):
        super().setUp()
        from tenancy.models import Membership

        _, self.tenant = founding_tenant("editgym")
        self._scope_token = context.set(self.tenant)
        self.admin = User.objects.create_user(
            username="owner", email="owner@example.com", password="pass12345", role=Role.ADMIN
        )
        Membership.objects.create(user=self.admin, tenant=self.tenant, role=Role.ADMIN)
        self.offer = ReferralProgram.objects.create(reward_days=15, blurb="Bring a friend.")

    def tearDown(self):
        context.reset(self._scope_token)
        super().tearDown()

    def test_an_edit_that_loaded_the_offer_before_it_was_replaced_is_not_a_500(self):
        import threading
        from unittest import mock

        from django.db import connections
        from rest_framework.test import APIClient

        from .views import ReferralProgramViewSet

        def admin_client():
            client = APIClient()
            client.force_authenticate(self.admin)
            return client

        base = f"/api/t/{self.tenant.slug}/referrals/programs/"
        loaded, release = threading.Event(), threading.Event()
        original = ReferralProgramViewSet.perform_update

        def held(view, serializer):
            # The running offer is already loaded; wait here until the new one is saved.
            loaded.set()
            release.wait(timeout=15)
            return original(view, serializer)

        outcome = []

        def edit():
            try:
                outcome.append(admin_client().patch(f"{base}{self.offer.pk}/", {"reward_days": 11}, format="json"))
            except BaseException as exc:  # noqa: BLE001 -- a 500 raised by the client is the result
                outcome.append(exc)
            finally:
                connections.close_all()

        with mock.patch.object(ReferralProgramViewSet, "perform_update", held):
            thread = threading.Thread(target=edit)
            thread.start()
            self.assertTrue(loaded.wait(timeout=15), "the edit never loaded the offer")
            new = admin_client().post(base, {"reward_days": 30, "blurb": "Thirty"}, format="json")
            release.set()
            thread.join(timeout=30)

        self.assertEqual(new.status_code, 201, new.content)
        [resp] = outcome
        self.assertNotIsInstance(resp, BaseException, resp)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            list(ReferralProgram.objects.filter(is_active=True).values_list("pk", flat=True)),
            [new.data["id"]],
        )
        self.offer.refresh_from_db()
        self.assertEqual((self.offer.is_active, self.offer.reward_days), (False, 11))
