"""Turnstiles and terminals, on the paths where something goes wrong.

`tests.py` covers the decisions -- who is let in, who is turned away, a repeat
punch, an unknown card. What it does not cover is what happens when the
attendance write behind the decision fails.

That case has a deliberate answer and it is worth pinning: the gate still
opens. A member who has paid is entitled to be in the building, and a
bookkeeping problem on our side is not a reason to leave them standing outside
in front of a queue. The failure is recorded against the punch instead, so it
can be sorted out afterwards rather than at the door.
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from accounts.models import MembershipStatus, MemberProfile, Role
from attendance.models import CheckInOut
from attendance.services import AttendanceError
from billing.models import Plan
from billing.services import record_payment

from . import access, services
from .models import Device, DeviceEvent, DeviceKind, EventOutcome, generate_key

User = get_user_model()


def make_member(username, biometric_id=None, paid=True):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=Role.MEMBER
    )
    MemberProfile.objects.update_or_create(
        user=user, defaults={"biometric_id": biometric_id}
    )
    if paid:
        plan = Plan.objects.filter(name="Monthly").first() or Plan.objects.create(
            name="Monthly", price=Decimal("1000"), duration_days=30
        )
        record_payment(member=user, plan=plan, amount=Decimal("1000"), method="cash")
    return User.objects.get(pk=user.pk)


def make_device(name="Front door", kind=DeviceKind.TURNSTILE):
    raw, hashed = generate_key()
    device = Device.objects.create(
        name=name, serial=f"SN-{name}", api_key_hash=hashed, kind=kind
    )
    return device, raw


class GateOpensDespiteBookkeepingFailureTests(TenantAPIMixin, APITestCase):
    """An attendance write that fails must not become a locked door."""

    def setUp(self):
        self.device, self.key = make_device()
        self.member = make_member("gate_member", biometric_id="B-100")

    @patch("devices.access.toggle_visit", side_effect=AttendanceError("Already checked in."))
    def test_the_gate_still_opens_when_the_visit_cannot_be_written(self, toggle):
        allow, reason, event = access.request_access(self.device, "B-100")

        self.assertTrue(allow, "a paid-up member was left outside over a bookkeeping error")
        self.assertEqual(reason, access.Decision.ALLOWED)

    @patch("devices.access.toggle_visit", side_effect=AttendanceError("Already checked in."))
    def test_the_failure_is_recorded_against_the_punch(self, toggle):
        _, _, event = access.request_access(self.device, "B-100")
        event.refresh_from_db()

        self.assertEqual(event.outcome, EventOutcome.FAILED)
        self.assertEqual(event.detail, "Already checked in.")
        # No visit attached, because none was written.
        self.assertIsNone(event.check_in_id)

    @patch("devices.access.toggle_visit", side_effect=AttendanceError("Already checked in."))
    def test_a_member_who_is_not_entitled_is_still_refused(self, toggle):
        # The rescue is only for people who are allowed in. Someone expired is
        # refused before the attendance write is ever attempted.
        lapsed = make_member("gate_lapsed", biometric_id="B-101", paid=False)
        MemberProfile.objects.filter(user=lapsed).update(
            membership_status=MembershipStatus.EXPIRED
        )

        allow, _, event = access.request_access(self.device, "B-101")
        self.assertFalse(allow)
        event.refresh_from_db()
        self.assertEqual(event.outcome, EventOutcome.DENIED)
        toggle.assert_not_called()

    def test_a_working_punch_still_records_the_visit(self):
        # The control: without the failure the visit is attached as normal, so
        # the tests above are pinning the error path rather than the happy one.
        allow, _, event = access.request_access(self.device, "B-100")
        event.refresh_from_db()

        self.assertTrue(allow)
        self.assertEqual(event.outcome, EventOutcome.CHECKED_IN)
        self.assertIsNotNone(event.check_in_id)
        self.assertTrue(
            CheckInOut.objects.filter(user=self.member, check_out_time__isnull=True).exists()
        )


class IngestFailureTests(TenantAPIMixin, APITestCase):
    """The recording-only path, which has the same rescue for a different reason."""

    def setUp(self):
        self.device, self.key = make_device("Terminal", kind=DeviceKind.TERMINAL)
        self.member = make_member("ingest_member", biometric_id="B-200")

    @patch("devices.services.toggle_visit", side_effect=AttendanceError("Already checked in."))
    def test_a_failed_toggle_is_logged_not_lost(self, toggle):
        event, _ = services.record_punch(self.device, "B-200", timezone.now())

        self.assertEqual(event.outcome, EventOutcome.FAILED)
        self.assertEqual(event.detail, "Already checked in.")
        self.assertEqual(event.member, self.member)
        # The punch itself survives, which is what makes reprocessing possible.
        self.assertTrue(DeviceEvent.objects.filter(pk=event.pk).exists())

    @patch("devices.services.toggle_visit", side_effect=AttendanceError("Already checked in."))
    def test_the_endpoint_reports_the_punch_rather_than_erroring(self, toggle):
        resp = self.client.post(
            "/api/devices/events/ingest/",
            {"punches": [{"biometric_id": "B-200", "event_time": timezone.now().isoformat()}]},
            format="json",
            HTTP_X_DEVICE_KEY=self.key,
        )
        # A terminal that gets a 500 will retry the same buffer forever.
        self.assertEqual(resp.status_code, 200)

    def test_an_unknown_id_is_recorded_as_unmatched_not_dropped(self):
        event, _ = services.record_punch(self.device, "B-NOBODY", timezone.now())

        self.assertEqual(event.outcome, EventOutcome.UNMATCHED)
        self.assertIsNone(event.member_id)
        # Kept so the id can be enrolled and the punch reprocessed.
        self.assertTrue(DeviceEvent.objects.filter(pk=event.pk).exists())

    def test_a_punch_reprocessed_after_enrolment_is_resolved(self):
        event, _ = services.record_punch(self.device, "B-LATE", timezone.now())
        self.assertEqual(event.outcome, EventOutcome.UNMATCHED)

        MemberProfile.objects.filter(user=self.member).update(biometric_id="B-LATE")
        again = services.reprocess(event)

        self.assertEqual(again.member, self.member)
        self.assertNotEqual(again.outcome, EventOutcome.UNMATCHED)


class ReprocessEndpointTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="dev_admin", email="a@example.com", password="pass12345", role=Role.ADMIN
        )
        self.device, self.key = make_device("Terminal2", kind=DeviceKind.TERMINAL)
        self.client.force_authenticate(self.admin)

    def test_reprocessing_an_event_that_does_not_exist_is_a_404(self):
        resp = self.client.post("/api/devices/events/999999/reprocess/")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("No such event", resp.data["detail"])

    def test_a_member_cannot_reprocess(self):
        member = make_member("dev_member", biometric_id="B-300")
        event, _ = services.record_punch(self.device, "B-300", timezone.now())

        self.client.force_authenticate(member)
        resp = self.client.post(f"/api/devices/events/{event.pk}/reprocess/")
        self.assertEqual(resp.status_code, 403)

    def test_events_can_be_filtered_by_device(self):
        other, _ = make_device("Terminal3", kind=DeviceKind.TERMINAL)
        make_member("filt_member", biometric_id="B-400")
        services.record_punch(self.device, "B-400", timezone.now())
        services.record_punch(other, "B-400", timezone.now() + timedelta(minutes=5))

        resp = self.client.get(f"/api/devices/events/?device={other.pk}")
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["device"], other.pk)

    def test_events_can_be_filtered_by_outcome(self):
        make_member("out_member", biometric_id="B-500")
        services.record_punch(self.device, "B-500", timezone.now())
        services.record_punch(self.device, "B-NOBODY", timezone.now())

        resp = self.client.get(f"/api/devices/events/?outcome={EventOutcome.UNMATCHED}")
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["outcome"], EventOutcome.UNMATCHED)
