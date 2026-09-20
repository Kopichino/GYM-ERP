from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from decimal import Decimal

from accounts.models import MemberProfile, MembershipStatus, Role
from attendance.models import CheckInMethod, CheckInOut
from billing.models import PaymentMethod, Plan
from billing.services import record_payment

from . import access
from .models import (
    Device,
    DeviceEvent,
    DeviceKind,
    EventOutcome,
    generate_key,
    hash_key,
)

User = get_user_model()


def make_user(username, role=Role.MEMBER, biometric_id=None):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    MemberProfile.objects.update_or_create(
        user=user, defaults={"biometric_id": biometric_id}
    )
    return user


def make_device(name="Front door"):
    raw, hashed = generate_key()
    device = Device.objects.create(name=name, serial=f"SN-{name}", api_key_hash=hashed)
    return device, raw


class DeviceAuthTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.device, self.key = make_device()
        self.member = make_user("member", biometric_id="B-001")
        self.punch = {
            "punches": [
                {"biometric_id": "B-001", "event_time": timezone.now().isoformat()}
            ]
        }

    def test_ingest_requires_a_device_key(self):
        # No credentials at all is 401, not 403 -- the terminal is
        # unauthenticated rather than forbidden.
        resp = self.client.post("/api/devices/events/ingest/", self.punch, format="json")
        self.assertEqual(resp.status_code, 401)

    def test_ingest_rejects_an_unknown_key(self):
        resp = self.client.post(
            "/api/devices/events/ingest/", self.punch, format="json", HTTP_X_DEVICE_KEY="nonsense"
        )
        self.assertEqual(resp.status_code, 401)

    def test_ingest_rejects_a_deactivated_device(self):
        self.device.is_active = False
        self.device.save()
        resp = self.client.post(
            "/api/devices/events/ingest/", self.punch, format="json", HTTP_X_DEVICE_KEY=self.key
        )
        self.assertEqual(resp.status_code, 401)

    def test_a_members_jwt_cannot_push_punches(self):
        """A device key is not a login, and a login is not a device key."""
        self.client.force_authenticate(self.member)
        resp = self.client.post("/api/devices/events/ingest/", self.punch, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_valid_key_is_accepted_and_updates_last_seen(self):
        resp = self.client.post(
            "/api/devices/events/ingest/", self.punch, format="json", HTTP_X_DEVICE_KEY=self.key
        )
        self.assertEqual(resp.status_code, 200)
        self.device.refresh_from_db()
        self.assertIsNotNone(self.device.last_seen_at)

    def test_the_plaintext_key_is_never_stored(self):
        self.assertNotEqual(self.device.api_key_hash, self.key)
        self.assertEqual(self.device.api_key_hash, hash_key(self.key))


class PunchResolutionTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.device, self.key = make_device()
        self.member = make_user("member", biometric_id="B-001")

    def _push(self, biometric_id="B-001", when=None):
        return self.client.post(
            "/api/devices/events/ingest/",
            {
                "punches": [
                    {
                        "biometric_id": biometric_id,
                        "event_time": (when or timezone.now()).isoformat(),
                    }
                ]
            },
            format="json",
            HTTP_X_DEVICE_KEY=self.key,
        )

    def test_first_punch_checks_the_member_in(self):
        resp = self._push()
        self.assertEqual(resp.data["results"][0]["outcome"], EventOutcome.CHECKED_IN)

        record = CheckInOut.objects.get(user=self.member)
        self.assertIsNone(record.check_out_time)
        self.assertEqual(record.method, CheckInMethod.BIOMETRIC)

    def test_second_punch_checks_the_member_out(self):
        self._push(when=timezone.now() - timedelta(hours=2))
        resp = self._push()

        self.assertEqual(resp.data["results"][0]["outcome"], EventOutcome.CHECKED_OUT)
        self.assertIsNotNone(CheckInOut.objects.get(user=self.member).check_out_time)

    def test_repeat_punch_within_the_window_is_ignored(self):
        now = timezone.now()
        self._push(when=now - timedelta(seconds=5))
        resp = self._push(when=now)

        self.assertEqual(resp.data["results"][0]["outcome"], EventOutcome.DUPLICATE)
        # Still exactly one open visit -- the swipe did not close it.
        self.assertEqual(
            CheckInOut.objects.filter(user=self.member, check_out_time__isnull=True).count(), 1
        )

    def test_identical_punch_is_not_stored_twice(self):
        when = timezone.now()
        self._push(when=when)
        resp = self._push(when=when)

        self.assertFalse(resp.data["results"][0]["accepted"])
        self.assertEqual(DeviceEvent.objects.count(), 1)

    def test_unmatched_punch_is_kept_not_discarded(self):
        resp = self._push(biometric_id="B-999")
        self.assertEqual(resp.data["results"][0]["outcome"], EventOutcome.UNMATCHED)

        event = DeviceEvent.objects.get(biometric_id="B-999")
        self.assertIsNone(event.member)
        self.assertIn("No member enrolled", event.detail)

    def test_unmatched_punch_can_be_reprocessed_after_enrolment(self):
        self._push(biometric_id="B-999")
        event = DeviceEvent.objects.get(biometric_id="B-999")

        # Admin corrects the enrolment, then replays the punch.
        self.member.profile.biometric_id = "B-999"
        self.member.profile.save()

        admin = make_user("admin", Role.ADMIN)
        self.client.force_authenticate(admin)
        resp = self.client.post(f"/api/devices/events/{event.pk}/reprocess/")

        self.assertEqual(resp.data["outcome"], EventOutcome.CHECKED_IN)
        self.assertTrue(CheckInOut.objects.filter(user=self.member).exists())

    def test_a_batch_is_processed_in_order(self):
        now = timezone.now()
        resp = self.client.post(
            "/api/devices/events/ingest/",
            {
                "punches": [
                    {"biometric_id": "B-001", "event_time": (now - timedelta(hours=3)).isoformat()},
                    {"biometric_id": "B-001", "event_time": (now - timedelta(hours=1)).isoformat()},
                ]
            },
            format="json",
            HTTP_X_DEVICE_KEY=self.key,
        )
        outcomes = [r["outcome"] for r in resp.data["results"]]
        self.assertEqual(outcomes, [EventOutcome.CHECKED_IN, EventOutcome.CHECKED_OUT])


class OneOpenCheckInInvariantTests(TenantAPIMixin, APITestCase):
    """Biometric is a second write path into attendance, so the rule it could
    most easily break gets its own guard."""

    def setUp(self):
        self.device, self.key = make_device()
        self.member = make_user("member", biometric_id="B-001")

    def test_device_punch_cannot_open_a_second_visit(self):
        # Member taps in on the app first.
        self.client.force_authenticate(self.member)
        self.client.post("/api/attendance/check_in/")
        self.client.force_authenticate(None)

        # Then presents a finger at the door, well outside the dedupe window.
        self.client.post(
            "/api/devices/events/ingest/",
            {
                "punches": [
                    {
                        "biometric_id": "B-001",
                        "event_time": (timezone.now() + timedelta(minutes=5)).isoformat(),
                    }
                ]
            },
            format="json",
            HTTP_X_DEVICE_KEY=self.key,
        )

        self.assertEqual(
            CheckInOut.objects.filter(user=self.member, check_out_time__isnull=True).count(),
            0,
            "the punch should have closed the open visit, not opened another",
        )
        self.assertEqual(CheckInOut.objects.filter(user=self.member).count(), 1)


class DeviceAdminApiTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = make_user("admin", Role.ADMIN)
        self.member = make_user("member")
        # The admin account endpoints reach only people enrolled at this gym, and
        # the member is never the one authenticating -- so enrol them explicitly.
        self.member_for(self.member, Role.MEMBER)

    def test_registering_a_device_returns_the_key_once(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post("/api/devices/", {"name": "Door", "serial": "SN-1"})

        self.assertEqual(resp.status_code, 201)
        self.assertIn("api_key", resp.data)
        # Never returned again on read.
        listed = self.client.get("/api/devices/").data["results"][0]
        self.assertNotIn("api_key", listed)

    def test_device_management_is_admin_only(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get("/api/devices/").status_code, 403)
        self.assertEqual(self.client.get("/api/devices/events/").status_code, 403)

    def test_rotating_a_key_invalidates_the_old_one(self):
        device, old_key = make_device("Side door")
        self.client.force_authenticate(self.admin)
        new_key = self.client.post(f"/api/devices/{device.pk}/rotate_key/").data["api_key"]
        self.client.force_authenticate(None)

        self.assertNotEqual(old_key, new_key)
        punch = {"punches": [{"biometric_id": "X", "event_time": timezone.now().isoformat()}]}
        stale = self.client.post(
            "/api/devices/events/ingest/", punch, format="json", HTTP_X_DEVICE_KEY=old_key
        )
        self.assertEqual(stale.status_code, 401)

    def test_admin_enrols_a_biometric_id_on_a_member(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.patch(
            f"/api/auth/admin/users/{self.member.pk}/", {"biometric_id": "B-777"}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        self.member.profile.refresh_from_db()
        self.assertEqual(self.member.profile.biometric_id, "B-777")

    def test_unmatched_queue_is_filterable(self):
        device, key = make_device("Gate")
        self.client.post(
            "/api/devices/events/ingest/",
            {"punches": [{"biometric_id": "ghost", "event_time": timezone.now().isoformat()}]},
            format="json",
            HTTP_X_DEVICE_KEY=key,
        )
        self.client.force_authenticate(self.admin)
        resp = self.client.get("/api/devices/events/?outcome=unmatched")
        self.assertEqual(resp.data["count"], 1)


class AccessControlTests(TenantAPIMixin, APITestCase):
    """A turnstile asking whether to open.

    The answer is read from the same derived membership status the rest of the
    app uses, so a member who pays at the desk is through on their next swipe
    with nothing to synchronise.
    """

    def setUp(self):
        self.raw_key, hashed = generate_key()
        self.gate = Device.objects.create(
            name="Turnstile",
            serial="GATE-01",
            api_key_hash=hashed,
            kind=DeviceKind.TURNSTILE,
        )
        self.plan = Plan.objects.create(
            name="Monthly", price=Decimal("1500"), duration_days=30
        )
        self.member = make_user("gatemember", biometric_id="FP-2001")

    def enrol(self, user, biometric_id):
        MemberProfile.objects.update_or_create(
            user=user, defaults={"biometric_id": biometric_id}
        )
        return user

    def pay(self, member, days_ago=0):
        return record_payment(
            member=member,
            plan=self.plan,
            amount=self.plan.price,
            method=PaymentMethod.CASH,
            paid_date=timezone.localdate() - timedelta(days=days_ago),
        )

    def ask(self, identifier="FP-2001", device=None):
        return access.request_access(device or self.gate, identifier)

    def test_a_paid_up_member_is_let_in_and_checked_in(self):
        self.pay(self.member)
        allow, reason, event = self.ask()

        self.assertTrue(allow)
        self.assertEqual(reason, access.Decision.ALLOWED)
        self.assertEqual(event.outcome, EventOutcome.CHECKED_IN)
        self.assertTrue(
            CheckInOut.objects.filter(user=self.member, check_out_time__isnull=True).exists()
        )

    def test_a_second_swipe_checks_them_out_rather_than_opening_a_second_visit(self):
        self.pay(self.member)
        self.ask()
        allow, _, event = access.request_access(
            self.gate, "FP-2001", at=timezone.now() + timedelta(minutes=90)
        )

        self.assertTrue(allow)
        self.assertEqual(event.outcome, EventOutcome.CHECKED_OUT)
        self.assertEqual(CheckInOut.objects.filter(user=self.member).count(), 1)

    def test_an_expired_membership_is_refused_and_no_visit_is_opened(self):
        self.pay(self.member, days_ago=60)
        allow, reason, event = self.ask()

        self.assertFalse(allow)
        self.assertEqual(reason, access.Decision.EXPIRED)
        self.assertEqual(event.outcome, EventOutcome.DENIED)
        self.assertFalse(CheckInOut.objects.filter(user=self.member).exists())

    def test_paying_at_the_desk_opens_the_gate_on_the_next_swipe(self):
        """Nothing is synchronised -- the decision reads the ledger each time."""
        self.pay(self.member, days_ago=60)
        self.assertFalse(self.ask()[0])

        self.pay(self.member)
        allow, reason, _ = access.request_access(
            self.gate, "FP-2001", at=timezone.now() + timedelta(seconds=30)
        )
        self.assertTrue(allow)
        self.assertEqual(reason, access.Decision.ALLOWED)

    def test_a_paused_membership_is_refused(self):
        self.pay(self.member)
        MemberProfile.objects.filter(user=self.member).update(
            membership_status=MembershipStatus.PAUSED
        )
        allow, reason, _ = self.ask()
        self.assertFalse(allow)
        self.assertEqual(reason, access.Decision.PAUSED)

    def test_a_member_who_never_paid_is_refused(self):
        allow, reason, _ = self.ask()
        self.assertFalse(allow)
        self.assertEqual(reason, access.Decision.NO_PLAN)

    def test_an_unknown_card_is_refused_and_still_logged(self):
        allow, reason, event = self.ask("FP-9999")
        self.assertFalse(allow)
        self.assertEqual(reason, access.Decision.UNKNOWN)
        self.assertEqual(event.outcome, EventOutcome.UNMATCHED)
        self.assertIsNone(event.member)

    def test_a_closed_account_is_refused(self):
        self.pay(self.member)
        User.objects.filter(pk=self.member.pk).update(is_active=False)
        allow, reason, _ = self.ask()
        self.assertFalse(allow)
        self.assertEqual(reason, access.Decision.DISABLED)

    def test_grace_days_let_a_just_lapsed_member_through(self):
        self.pay(self.member, days_ago=31)  # expired yesterday
        self.assertFalse(self.ask()[0])

        Device.objects.filter(pk=self.gate.pk).update(grace_days=3)
        self.gate.refresh_from_db()
        allow, reason, _ = access.request_access(
            self.gate, "FP-2001", at=timezone.now() + timedelta(seconds=30)
        )
        self.assertTrue(allow)

    def test_staff_are_always_let_in(self):
        """A trainer whose own membership lapsed still has sessions to take."""
        coach = User.objects.create_user(
            username="gatecoach", email="gc@example.com", password="pass12345", role=Role.TRAINER
        )
        # Staff-ness is now held by a Membership at *this* gym, not by
        # `User.role`. The device carries the tenant, so both halves have to be
        # present for the turnstile to recognise them.
        Device.objects.filter(pk=self.gate.pk).update(tenant=self.tenant)
        self.gate.refresh_from_db()
        self.member_for(coach, Role.TRAINER)

        self.enrol(coach, "FP-3001")
        allow, reason, _ = self.ask("FP-3001")
        self.assertTrue(allow)
        self.assertEqual(reason, access.Decision.ALLOWED)

    def test_an_admin_of_another_gym_is_not_staff_here(self):
        """The security hole this replaced.

        `judge` used to wave through anyone whose `User.role` was admin or
        trainer. On a platform running many gyms that opened every turnstile to
        an admin of any gym; staff now has to mean staff *at this door*.
        """
        outsider = User.objects.create_user(
            username="othergymadmin", email="oga@example.com",
            password="pass12345", role=Role.ADMIN,
        )
        Device.objects.filter(pk=self.gate.pk).update(tenant=self.tenant)
        self.gate.refresh_from_db()
        # Deliberately no Membership at this gym.
        self.enrol(outsider, "FP-3002")
        allow, _, _ = self.ask("FP-3002")
        self.assertFalse(allow)

    def test_a_plain_terminal_never_turns_anyone_away(self):
        """Registered before access control existed, and unchanged by it."""
        _, hashed = generate_key()
        terminal = Device.objects.create(
            name="Reception", serial="TERM-01", api_key_hash=hashed
        )
        self.assertEqual(terminal.kind, DeviceKind.TERMINAL)

        self.pay(self.member, days_ago=60)  # expired
        allow, _, event = self.ask(device=terminal)
        self.assertTrue(allow)
        self.assertEqual(event.outcome, EventOutcome.CHECKED_IN)

    def test_a_retried_swipe_repeats_the_original_answer(self):
        self.pay(self.member, days_ago=60)
        at = timezone.now()
        first = access.request_access(self.gate, "FP-2001", at=at)
        second = access.request_access(self.gate, "FP-2001", at=at)

        self.assertEqual(first[0], second[0])
        self.assertEqual(DeviceEvent.objects.filter(biometric_id="FP-2001").count(), 1)


class AccessApiTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.raw_key, hashed = generate_key()
        self.gate = Device.objects.create(
            name="Turnstile", serial="GATE-API", api_key_hash=hashed, kind=DeviceKind.TURNSTILE
        )
        self.plan = Plan.objects.create(
            name="Monthly", price=Decimal("1500"), duration_days=30
        )
        self.member = make_user("apigate", biometric_id="FP-4001")

    def post(self, payload, key=None):
        return self.client.post(
            "/api/devices/access/",
            payload,
            HTTP_X_DEVICE_KEY=key if key is not None else self.raw_key,
        )

    def test_the_gate_gets_an_answer_it_can_act_on(self):
        record_payment(
            member=self.member,
            plan=self.plan,
            amount=self.plan.price,
            method=PaymentMethod.CASH,
        )
        resp = self.post({"identifier": "FP-4001"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["allow"])
        self.assertEqual(resp.data["message"], "")
        self.assertEqual(resp.data["reason"], "allowed")

    def test_a_refusal_comes_with_wording_for_the_gates_screen(self):
        resp = self.post({"identifier": "FP-4001"})
        self.assertFalse(resp.data["allow"])
        self.assertIn("front desk", resp.data["message"])

    def test_a_gate_without_a_key_is_refused_outright(self):
        resp = self.post({"identifier": "FP-4001"}, key="")
        self.assertEqual(resp.status_code, 401)

    def test_a_wrong_key_is_refused(self):
        resp = self.post({"identifier": "FP-4001"}, key="not-the-key")
        self.assertEqual(resp.status_code, 401)

    def test_denials_show_up_in_the_admin_event_feed(self):
        self.post({"identifier": "FP-4001"})
        admin = User.objects.create_user(
            username="gateadmin", email="ga@example.com", password="pass12345", role=Role.ADMIN
        )
        self.client.force_authenticate(admin)
        resp = self.client.get("/api/devices/events/?outcome=denied")
        self.assertEqual(resp.data["count"], 1)
        row = resp.data["results"][0]
        # The feed carries wording the desk can act on, not just a code.
        self.assertIn("no membership on file", row["detail"].lower())
        self.assertEqual(row["member_name"], "apigate")
