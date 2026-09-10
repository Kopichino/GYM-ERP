"""The public leads endpoint: the one unauthenticated write path in the system.

Its key lives in a contact form on a public marketing site, so it is readable
by anyone who views source. These tests are written on that assumption -- what
is asserted is not that the key stays secret, but that holding it is worth very
little:

* it creates one enquiry in one gym's pipeline and can do nothing else;
* it cannot read anything, including what it just wrote;
* it cannot reach another gym;
* revoking it works immediately.

The spam checks are asserted to be *silent*. A bot told which rule caught it
has been handed the way around it, so a dropped submission answers 201 exactly
like an accepted one.
"""

from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient, APITestCase

from accounts.models import Role
from crm.models import Enquiry, EnquirySource
from tenancy import context
from tenancy.leads import LeadRateThrottle
from tenancy.models import (
    LeadApiKey,
    LeadFailure,
    Membership,
    Organisation,
    Tenant,
    generate_lead_key,
)

User = get_user_model()


def make_gym(slug, name):
    org = Organisation.objects.create(name=name, slug=slug)
    tenant = Tenant.objects.create(organisation=org, name=name, slug=f"{slug}-main")
    return org, tenant


def issue_key(tenant, label="Website", origins=""):
    raw, hashed = generate_lead_key()
    with context.scope(tenant):
        key = LeadApiKey.objects.create(
            label=label, key_hash=hashed, allowed_origins=origins
        )
    return raw, key


class LeadEndpointTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.org_a, self.gym_a = make_gym("alpha", "Alpha Fitness")
        self.org_b, self.gym_b = make_gym("beta", "Beta Gym")
        self.raw_a, self.key_a = issue_key(self.gym_a)
        self.raw_b, self.key_b = issue_key(self.gym_b)

    def tearDown(self):
        cache.clear()

    def post(self, payload, key=None, origin=None):
        extra = {}
        if key:
            extra["HTTP_X_LEAD_KEY"] = key
        if origin:
            extra["HTTP_ORIGIN"] = origin
        return self.client.post(
            "/api/t/alpha-main/tenancy/leads/", payload, format="json", **extra
        )

    def enquiries(self, tenant):
        with context.scope(tenant):
            return list(Enquiry.objects.all())

    def test_a_valid_lead_lands_in_that_gyms_pipeline(self):
        resp = self.post({"name": "Asha", "phone": "9820011111"}, key=self.raw_a)
        self.assertEqual(resp.status_code, 201)

        rows = self.enquiries(self.gym_a)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].name, "Asha")
        self.assertEqual(rows[0].source, EnquirySource.WEBSITE)

    def test_it_is_due_for_a_call_today(self):
        """A website lead is at its warmest on arrival."""
        from django.utils import timezone

        self.post({"name": "Asha", "phone": "9820011111"}, key=self.raw_a)
        self.assertEqual(self.enquiries(self.gym_a)[0].follow_up_on, timezone.localdate())

    def test_it_never_lands_in_another_gyms_pipeline(self):
        self.post({"name": "Asha", "phone": "9820011111"}, key=self.raw_a)
        self.assertEqual(self.enquiries(self.gym_b), [])

    def test_one_gyms_key_writes_only_to_that_gym(self):
        """Even posting at another gym's URL: the key decides, not the path."""
        resp = self.client.post(
            "/api/t/alpha-main/tenancy/leads/",
            {"name": "Wrong Gym", "phone": "1"},
            format="json",
            HTTP_X_LEAD_KEY=self.raw_b,
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(self.enquiries(self.gym_a), [])
        self.assertEqual(len(self.enquiries(self.gym_b)), 1)

    def test_an_email_alone_is_enough(self):
        resp = self.post({"name": "Asha", "email": "asha@example.com"}, key=self.raw_a)
        self.assertEqual(resp.status_code, 201)

    def test_no_way_to_contact_them_is_refused(self):
        """A lead nobody can reach is not a lead."""
        resp = self.post({"name": "Asha"}, key=self.raw_a)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self.enquiries(self.gym_a), [])

    def test_no_name_is_refused(self):
        resp = self.post({"phone": "9820011111"}, key=self.raw_a)
        self.assertEqual(resp.status_code, 400)

    def test_the_response_does_not_leak_a_row_id(self):
        """A public caller has no use for it, and it would reveal how many
        enquiries a gym has."""
        resp = self.post({"name": "Asha", "phone": "1"}, key=self.raw_a)
        self.assertEqual(resp.data, {"received": True})


class LeadKeyAuthTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.org, self.gym = make_gym("alpha", "Alpha Fitness")
        self.raw, self.key = issue_key(self.gym)

    def tearDown(self):
        cache.clear()

    def post(self, key=None, origin=None):
        extra = {}
        if key:
            extra["HTTP_X_LEAD_KEY"] = key
        if origin:
            extra["HTTP_ORIGIN"] = origin
        return self.client.post(
            "/api/t/alpha-main/tenancy/leads/",
            {"name": "Asha", "phone": "1"},
            format="json",
            **extra,
        )

    def test_no_key_is_refused(self):
        self.assertEqual(self.post().status_code, 401)

    def test_an_unknown_key_is_refused(self):
        self.assertEqual(self.post(key="lead_nonsense").status_code, 401)

    def test_a_revoked_key_stops_working_immediately(self):
        LeadApiKey.unscoped.filter(pk=self.key.pk).update(is_active=False)
        self.assertEqual(self.post(key=self.raw).status_code, 401)

    def test_a_suspended_gym_stops_accepting_enquiries(self):
        Tenant.objects.filter(pk=self.gym.pk).update(is_active=False)
        self.assertEqual(self.post(key=self.raw).status_code, 401)

    def test_the_key_is_stored_hashed_not_in_the_clear(self):
        """A database dump must not hand someone every gym's key."""
        self.key.refresh_from_db()
        self.assertNotEqual(self.key.key_hash, self.raw)
        self.assertNotIn(self.raw, self.key.key_hash)

    def test_an_origin_restricted_key_refuses_another_site(self):
        LeadApiKey.unscoped.filter(pk=self.key.pk).update(
            allowed_origins="https://www.alpha.example"
        )
        self.assertEqual(self.post(key=self.raw, origin="https://evil.example").status_code, 401)

    def test_and_accepts_its_own(self):
        LeadApiKey.unscoped.filter(pk=self.key.pk).update(
            allowed_origins="https://www.alpha.example"
        )
        self.assertEqual(
            self.post(key=self.raw, origin="https://www.alpha.example").status_code, 201
        )

    def test_with_no_origins_configured_a_server_side_post_still_works(self):
        """Those carry no Origin header at all, and are the commonest case."""
        self.assertEqual(self.post(key=self.raw).status_code, 201)

    def test_the_key_cannot_read_anything(self):
        """The whole safety argument: it writes one row and that is all."""
        for path in ("crm/enquiries/", "auth/admin/members/", "billing/"):
            resp = self.client.get(
                f"/api/t/alpha-main/{path}", HTTP_X_LEAD_KEY=self.raw
            )
            self.assertIn(resp.status_code, (401, 403, 404), path)


class SpamTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.org, self.gym = make_gym("alpha", "Alpha Fitness")
        self.raw, self.key = issue_key(self.gym)

    def tearDown(self):
        cache.clear()

    def post(self, payload):
        return self.client.post(
            "/api/t/alpha-main/tenancy/leads/", payload, format="json",
            HTTP_X_LEAD_KEY=self.raw,
        )

    def count(self):
        with context.scope(self.gym):
            return Enquiry.objects.count()

    def test_a_filled_honeypot_is_dropped_silently(self):
        """201, exactly like an accepted one -- telling a bot which rule caught
        it is a free lesson in getting past it."""
        resp = self.post({
            "name": "Bot", "phone": "1", "company_website": "http://spam.example",
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(self.count(), 0)

    def test_link_spam_is_dropped(self):
        resp = self.post({
            "name": "Bot", "phone": "1",
            "message": "http://a.example http://b.example http://c.example",
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(self.count(), 0)

    def test_a_genuine_message_with_one_link_is_kept(self):
        resp = self.post({
            "name": "Asha", "phone": "1",
            "message": "Saw your timetable at http://alpha.example - do you do 6am classes?",
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(self.count(), 1)

    def test_an_absurd_name_is_dropped(self):
        resp = self.post({"name": "x" * 200, "phone": "1"})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(self.count(), 0)


class ThrottleTests(APITestCase):
    """Per key, so one gym's flood cannot spend another gym's allowance.

    The rate is lowered by patching the throttle class rather than by
    `override_settings`. DRF reads `DEFAULT_THROTTLE_RATES` into
    `SimpleRateThrottle.THROTTLE_RATES` once, at import, so a settings override
    applied later never reaches it -- the flood test passed thirty requests
    against the real 30/hour limit and quietly proved nothing.

    Patching the class skips the settings wiring, so
    `test_the_rate_comes_from_settings` asserts that half separately.
    """

    def setUp(self):
        cache.clear()
        patcher = patch.object(LeadRateThrottle, "THROTTLE_RATES", {"leads": "3/hour"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.org_a, self.gym_a = make_gym("alpha", "Alpha Fitness")
        self.org_b, self.gym_b = make_gym("beta", "Beta Gym")
        self.raw_a, _ = issue_key(self.gym_a)
        self.raw_b, _ = issue_key(self.gym_b)

    def tearDown(self):
        cache.clear()

    def post(self, key):
        return self.client.post(
            "/api/t/alpha-main/tenancy/leads/",
            {"name": "Asha", "phone": "1"}, format="json",
            HTTP_X_LEAD_KEY=key,
        )

    def test_the_rate_comes_from_settings(self):
        """The half the patch above skips: that "leads" is the name DRF looks up."""
        with patch.object(
            LeadRateThrottle,
            "THROTTLE_RATES",
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
        ):
            self.assertEqual(LeadRateThrottle().rate, "30/hour")

    def test_a_flood_on_one_key_is_eventually_refused(self):
        codes = [self.post(self.raw_a).status_code for _ in range(6)]
        self.assertEqual(codes, [201, 201, 201, 429, 429, 429])

    def test_and_the_other_gym_is_unaffected(self):
        """The cross-tenant coupling an IP-based limit would have created."""
        for _ in range(6):
            self.post(self.raw_a)
        self.assertEqual(self.post(self.raw_b).status_code, 201)


class LeadKeyManagementTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.org_a, self.gym_a = make_gym("alpha", "Alpha Fitness")
        self.org_b, self.gym_b = make_gym("beta", "Beta Gym")
        self.owner_a = User.objects.create_user(
            username="alpha_owner", email="a@example.com",
            password="pass12345", role=Role.ADMIN,
        )
        self.owner_b = User.objects.create_user(
            username="beta_owner", email="b@example.com",
            password="pass12345", role=Role.ADMIN,
        )
        Membership.objects.create(user=self.owner_a, tenant=self.gym_a, role=Role.ADMIN)
        Membership.objects.create(user=self.owner_b, tenant=self.gym_b, role=Role.ADMIN)

    def tearDown(self):
        cache.clear()

    def test_the_plaintext_is_returned_once_and_never_again(self):
        self.client.force_authenticate(self.owner_a)
        created = self.client.post(
            "/api/t/alpha-main/tenancy/lead-keys/", {"label": "Marketing site"}
        )
        self.assertEqual(created.status_code, 201)
        self.assertTrue(created.data["plaintext"].startswith("lead_"))

        listed = self.client.get("/api/t/alpha-main/tenancy/lead-keys/")
        self.assertNotIn("plaintext", str(listed.data))

    def test_an_owner_sees_only_their_own_keys(self):
        self.client.force_authenticate(self.owner_a)
        self.client.post("/api/t/alpha-main/tenancy/lead-keys/", {"label": "Alpha site"})
        self.client.force_authenticate(self.owner_b)
        listed = self.client.get("/api/t/beta-main/tenancy/lead-keys/")
        self.assertEqual(listed.data["results"], [])

    def test_a_member_cannot_issue_a_key(self):
        member = User.objects.create_user(
            username="alpha_member", email="am@example.com",
            password="pass12345", role=Role.MEMBER,
        )
        Membership.objects.create(user=member, tenant=self.gym_a, role=Role.MEMBER)
        self.client.force_authenticate(member)
        resp = self.client.post(
            "/api/t/alpha-main/tenancy/lead-keys/", {"label": "Sneaky"}
        )
        self.assertEqual(resp.status_code, 403)

    def test_a_gym_may_hold_several_so_one_can_be_replaced_safely(self):
        self.client.force_authenticate(self.owner_a)
        for label in ("Old site", "New site"):
            self.client.post("/api/t/alpha-main/tenancy/lead-keys/", {"label": label})
        listed = self.client.get("/api/t/alpha-main/tenancy/lead-keys/")
        self.assertEqual(len(listed.data["results"]), 2)

    def test_a_new_key_is_active_however_the_request_was_encoded(self):
        """DRF reads a missing BooleanField as False for form input, because an
        unchecked checkbox sends nothing -- so a form-encoded create was
        handing back a key that was born revoked. The admin screen posts JSON
        and never saw it; anyone integrating from a form would have."""
        self.client.force_authenticate(self.owner_a)
        for label, kwargs in (
            ("Form encoded", {}),
            ("JSON encoded", {"format": "json"}),
        ):
            created = self.client.post(
                "/api/t/alpha-main/tenancy/lead-keys/", {"label": label}, **kwargs
            )
            self.assertEqual(created.status_code, 201, label)
            self.assertTrue(created.data["is_active"], label)

    def test_another_gyms_key_is_out_of_reach_even_with_its_real_id(self):
        """The other direction of the isolation check.

        An empty list proves the scoping filters; it does not prove a guessed
        id is refused, and the id here is not guessed but correct. Every verb
        the router exposes is tried, because a viewset that scopes `list` and
        forgets `get_object` reads as isolated right up until someone types a
        number into the URL.
        """
        _, key_b = issue_key(self.gym_b, label="Beta site")
        self.client.force_authenticate(self.owner_a)

        url = f"/api/t/alpha-main/tenancy/lead-keys/{key_b.pk}/"
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.patch(url, {"is_active": False}).status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)

        # And it is still there and still working.
        key_b.refresh_from_db()
        self.assertTrue(key_b.is_active)

    def test_revoking_leaves_the_row_and_its_usage_trail(self):
        """The path the admin screen uses. A delete would take the history of
        what the key sent with it, which is the record an owner needs *after*
        deciding it was compromised."""
        self.client.force_authenticate(self.owner_a)
        created = self.client.post(
            "/api/t/alpha-main/tenancy/lead-keys/", {"label": "Marketing site"}
        )
        raw = created.data["plaintext"]
        key_id = created.data["id"]

        # A separate client, because `force_authenticate` short-circuits
        # authentication entirely: the lead key would never be looked at, and
        # the post would be refused for having no key rather than accepted.
        # The gym's website is an anonymous caller, so the test has to be one.
        website = APIClient()
        posted = website.post(
            "/api/t/alpha-main/tenancy/leads/",
            {"name": "Asha", "phone": "1"}, format="json", HTTP_X_LEAD_KEY=raw,
        )
        self.assertEqual(posted.status_code, 201)

        revoked = self.client.patch(
            f"/api/t/alpha-main/tenancy/lead-keys/{key_id}/", {"is_active": False}
        )
        self.assertEqual(revoked.status_code, 200)
        self.assertFalse(revoked.data["is_active"])
        self.assertEqual(revoked.data["leads_created"], 1)

        self.assertEqual(
            website.post(
                "/api/t/alpha-main/tenancy/leads/",
                {"name": "Later", "phone": "1"}, format="json", HTTP_X_LEAD_KEY=raw,
            ).status_code,
            401,
        )

    def test_a_key_cannot_be_issued_into_another_gym_by_asking(self):
        """`tenant` is stamped from the request's scope, so naming one in the
        body is ignored rather than obeyed."""
        self.client.force_authenticate(self.owner_a)
        created = self.client.post(
            "/api/t/alpha-main/tenancy/lead-keys/",
            {"label": "Sneaky", "tenant": self.gym_b.pk},
        )
        self.assertEqual(created.status_code, 201)

        key = LeadApiKey.unscoped.get(pk=created.data["id"])
        self.assertEqual(key.tenant_id, self.gym_a.pk)


class CorsTests(APITestCase):
    """The form runs in a browser, so CORS is part of whether it works at all.

    Everything else here can be checked with curl, which browsers' same-origin
    rules never touch -- which is exactly why this needed its own tests. The
    endpoint passed every functional check while being unusable from the one
    place it is meant to be used from.
    """

    def setUp(self):
        cache.clear()
        self.org, self.gym = make_gym("alpha", "Alpha Fitness")

    def tearDown(self):
        cache.clear()

    def preflight(self, path, headers="content-type,x-lead-key"):
        return self.client.options(
            path,
            HTTP_ORIGIN="https://www.alpha-marketing.example",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS=headers,
        )

    def test_the_leads_endpoint_answers_a_stranger_origin(self):
        """A gym's marketing site is not the domain they verified for the
        portal, and is often not on this platform at all."""
        resp = self.preflight("/api/t/alpha-main/tenancy/leads/")
        self.assertEqual(
            resp.headers.get("access-control-allow-origin"),
            "https://www.alpha-marketing.example",
        )

    def test_the_lead_key_header_is_allowed_through_the_preflight(self):
        """A header the preflight omits is one the browser refuses to send, so
        the request would never reach the view."""
        resp = self.preflight("/api/t/alpha-main/tenancy/leads/")
        allowed = resp.headers.get("access-control-allow-headers", "").lower()
        self.assertIn("x-lead-key", allowed)

    def test_nothing_else_is_opened_up(self):
        """The blast radius of the line above: one path, not the API."""
        for path in (
            "/api/t/alpha-main/crm/enquiries/",
            "/api/t/alpha-main/tenancy/lead-keys/",
            "/api/auth/login/",
        ):
            resp = self.preflight(path)
            self.assertIsNone(resp.headers.get("access-control-allow-origin"), path)


class FailureReportingTests(APITestCase):
    """A form that breaks on someone else's website breaks silently here.

    The visitor gets an apology and the gym gets nothing, so the normal way a
    broken form is discovered is by noticing weeks later that enquiries dried
    up. These record the refusals this system can actually attribute to a key,
    which is what lets the admin screen say so on the day.
    """

    def setUp(self):
        cache.clear()
        self.org, self.gym = make_gym("alpha", "Alpha Fitness")
        self.raw, self.key = issue_key(self.gym)

    def tearDown(self):
        cache.clear()

    def post(self, payload=None, key=None, origin=None):
        extra = {"HTTP_X_LEAD_KEY": key or self.raw}
        if origin:
            extra["HTTP_ORIGIN"] = origin
        return self.client.post(
            "/api/t/alpha-main/tenancy/leads/",
            payload if payload is not None else {"name": "Asha", "phone": "1"},
            format="json",
            **extra,
        )

    def reread(self):
        self.key.refresh_from_db()
        return self.key

    def test_a_revoked_key_still_being_called_is_recorded(self):
        """The owner did the revoking, but this says their site was never
        updated -- so every enquiry since has been going nowhere."""
        LeadApiKey.unscoped.filter(pk=self.key.pk).update(is_active=False)
        self.post()

        row = self.reread()
        self.assertEqual(row.last_failure_reason, LeadFailure.REVOKED)
        self.assertEqual(row.failures_since_success, 1)
        self.assertIsNotNone(row.last_failure_at)

    def test_a_blocked_origin_is_recorded(self):
        LeadApiKey.unscoped.filter(pk=self.key.pk).update(
            allowed_origins="https://www.alpha.example"
        )
        self.post(origin="https://elsewhere.example")
        self.assertEqual(self.reread().last_failure_reason, LeadFailure.ORIGIN)

    def test_a_form_sending_no_contact_details_is_recorded(self):
        """One of these is a visitor leaving a box empty. A run of them is a
        form whose fields were renamed when it was pasted in."""
        self.assertEqual(self.post({"name": "Asha"}).status_code, 400)
        self.assertEqual(self.reread().last_failure_reason, LeadFailure.PAYLOAD)

    def test_hitting_the_rate_limit_is_recorded(self):
        with patch.object(LeadRateThrottle, "THROTTLE_RATES", {"leads": "2/hour"}):
            codes = [self.post().status_code for _ in range(4)]
        self.assertIn(429, codes)
        self.assertEqual(self.reread().last_failure_reason, LeadFailure.RATE)

    def test_an_accepted_lead_clears_the_alarm(self):
        """So a fixed form stops warning by itself. A warning that has to be
        dismissed gets dismissed by habit, and then the next one is too."""
        self.assertEqual(self.post({"name": "Asha"}).status_code, 400)
        self.assertEqual(self.reread().failures_since_success, 1)

        self.assertEqual(self.post().status_code, 201)
        row = self.reread()
        self.assertEqual(row.failures_since_success, 0)
        # The reason is kept as history; the counter is what the screen reads.
        self.assertEqual(row.last_failure_reason, LeadFailure.PAYLOAD)

    def test_a_burst_of_the_same_fault_counts_once(self):
        """Thirty visitors meeting one broken form in a minute is one problem.

        Also the reason the refusals that happen *before* the rate limit cannot
        be turned into a write amplifier by anyone holding a scraped key.
        """
        LeadApiKey.unscoped.filter(pk=self.key.pk).update(is_active=False)
        for _ in range(5):
            self.post()
        self.assertEqual(self.reread().failures_since_success, 1)

    def test_but_a_different_fault_is_recorded_at_once(self):
        """A key that starts failing for a new reason has changed state, and
        the screen should say the current thing rather than the stale one."""
        self.assertEqual(self.post({"name": "Asha"}).status_code, 400)
        LeadApiKey.unscoped.filter(pk=self.key.pk).update(is_active=False)
        self.post()

        row = self.reread()
        self.assertEqual(row.last_failure_reason, LeadFailure.REVOKED)
        self.assertEqual(row.failures_since_success, 2)

    def test_an_unknown_key_records_nothing(self):
        """There is no gym to attribute it to, and no screen to show it on."""
        self.post(key="lead_nobodyskey")
        self.assertEqual(self.reread().failures_since_success, 0)

    def test_spam_is_not_a_failure(self):
        """It was dropped on purpose. Warning a gym that their form is broken
        every time a bot finds it would train them to ignore the warning."""
        resp = self.post({
            "name": "Bot", "phone": "1", "company_website": "http://spam.example",
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(self.reread().failures_since_success, 0)

    def test_the_owner_can_see_all_of_this(self):
        """It is worth nothing if it does not reach the screen."""
        owner = User.objects.create_user(
            username="alpha_owner", email="a@example.com",
            password="pass12345", role=Role.ADMIN,
        )
        Membership.objects.create(user=owner, tenant=self.gym, role=Role.ADMIN)
        self.post({"name": "Asha"})

        self.client.force_authenticate(owner)
        listed = self.client.get("/api/t/alpha-main/tenancy/lead-keys/")
        row = listed.data["results"][0]
        self.assertEqual(row["last_failure_reason"], LeadFailure.PAYLOAD)
        self.assertEqual(row["failures_since_success"], 1)
        self.assertIsNotNone(row["last_failure_at"])
