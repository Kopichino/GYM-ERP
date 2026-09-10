"""Helpers for tests that need two requests to actually collide.

Most of this project's invariants are held by a database constraint rather than
an application check, and a constraint is only worth what it does under load.
A sequential test that calls the same function twice proves the second call is
refused; it does not prove that two callers arriving at the same instant are.
These helpers make the second kind of test writable.

Not a test module itself -- `tests_concurrency.py` in each app uses it.
"""

import contextvars
import threading
import unittest

from django.db import connection, connections

from tenancy import context

# SQLite serialises every writer and ignores `select_for_update()` outright
# (`has_select_for_update` is False), so a race is not reproducible on it: the
# lock-based invariants would appear to hold for the wrong reason, and the
# index-based ones would trip "database is locked" instead of the constraint.
# The tests below therefore run on a backend that takes row locks -- Postgres,
# which is what production uses -- and skip loudly everywhere else, so nobody
# reads a green SQLite run as evidence these paths are safe.
NEEDS_ROW_LOCKS = (
    "needs a backend with real row-level locking (Postgres). SQLite serialises "
    "writers and ignores select_for_update, so a race cannot be reproduced on it. "
    "Run with DATABASE_URL=postgres://... to exercise this."
)

requires_row_locks = unittest.skipUnless(
    connection.features.has_select_for_update, NEEDS_ROW_LOCKS
)


def run_concurrently(action, count=2, timeout=30):
    """Run `action(i)` in `count` threads released at the same moment.

    Returns a list of `(outcome, value)` in thread order, where outcome is
    "ok" and value is the return, or "error" and value is the exception. Both
    are returned rather than raised: the whole point of these tests is that
    exactly one caller wins and the others are refused, so the refusals are
    the result, not a failure.

    A barrier holds every thread until the last one is ready, which is what
    turns "two calls" into "two simultaneous calls". Each thread closes its own
    connection afterwards -- Django hands out one per thread, and leaving them
    open makes the test-database teardown hang.
    """
    barrier = threading.Barrier(count, timeout=timeout)
    results = [None] * count

    # A new thread starts with a *fresh* ContextVar context -- it does not
    # inherit the caller's. So the tenant scope the test opened is invisible in
    # the workers, and every scoped query inside them raises.
    #
    # One copy per thread, not one shared copy: a Context cannot be entered
    # twice at once, and `Context.run` from several threads on the same object
    # raises "cannot enter context: ... is already entered" -- which surfaced as
    # a RuntimeError where the test expected the service's own refusal.
    contexts = [contextvars.copy_context() for _ in range(count)]

    def worker(index):
        try:
            barrier.wait()
            results[index] = ("ok", contexts[index].run(action, index))
        except BaseException as exc:  # noqa: BLE001 -- the refusal is the result
            results[index] = ("error", exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=timeout)

    stuck = [i for i, thread in enumerate(threads) if thread.is_alive()]
    if stuck:
        raise AssertionError(f"threads {stuck} did not finish within {timeout}s")
    return results


def winners(results):
    """The values from the calls that succeeded."""
    return [value for outcome, value in results if outcome == "ok"]


def losers(results):
    """The exceptions from the calls that were refused."""
    return [value for outcome, value in results if outcome == "error"]


def founding_tenant(slug="testgym"):
    """An organisation with one branch, for tests that need somewhere to belong.

    Most tests predate multi-tenancy and do not care which gym they are in --
    but a per-organisation uniqueness rule cannot fire on rows whose
    organisation is null, because NULLs are distinct in a unique index. Tests
    asserting those rules therefore have to put their rows somewhere.
    """
    from tenancy.models import Organisation, Tenant

    org, _ = Organisation.objects.get_or_create(
        slug=slug, defaults={"name": slug.title()}
    )
    tenant, _ = Tenant.objects.get_or_create(
        slug=f"{slug}-main", defaults={"organisation": org, "name": slug.title()}
    )
    return org, tenant


class TenantAPIMixin:
    """Gives a test case a gym, and points its client at that gym's URLs.

    Every API test predates multi-tenancy and calls `/api/...` directly, which
    now resolves no tenant at all -- so permissions refuse it and scoped
    managers raise. Rather than rewrite several hundred call sites, this
    rewrites the path on the way out of the client.

    `member_for(user, role)` opens the Membership that makes the user somebody
    at this gym. Without one they are a signed-in stranger, which is exactly
    what a cross-tenant caller is -- so tests that forget it fail the same way
    an attacker would, which is the right kind of failure.
    """

    tenant_slug = "testgym"

    #: Set by `_pre_setup`. Left None so the properties below can tell
    #: "the mixin has not run" from "the tenant is legitimately absent".
    _tenant = None
    _organisation = None

    #: `_pre_setup` is private Django API. It has been stable for a decade and
    #: several third-party test packages hook it, but it sits outside the
    #: backwards-compatibility policy -- so the risk worth guarding is not that
    #: it changes behaviour, it is that a future upgrade stops calling it. If
    #: that happens the client is never patched either, and every request goes
    #: out unprefixed and comes back 403: a wave of confusing failures pointing
    #: nowhere near the cause. This turns that into one sentence, said once per
    #: test, naming the thing that broke.
    NOT_INITIALISED = (
        "TenantAPIMixin did not initialise -- Django's _pre_setup contract may "
        "have changed. Without it no tenant exists and the test client sends "
        "unprefixed URLs, which the API refuses with 403."
    )

    @property
    def tenant(self):
        if self._tenant is None:
            raise RuntimeError(self.NOT_INITIALISED)
        return self._tenant

    @property
    def organisation(self):
        if self._organisation is None:
            raise RuntimeError(self.NOT_INITIALISED)
        return self._organisation

    #: Open a Membership for every user the test made, using the role they were
    #: created with. These tests predate multi-tenancy and assume one gym that
    #: everybody belongs to, so this reproduces exactly that -- without it,
    #: every user would be a signed-in stranger. Cross-tenant tests turn it off
    #: and enrol deliberately, so isolation is still tested honestly.
    enrol_everyone = True

    @classmethod
    def setUpClass(cls):
        """Open the tenant scope around `setUpTestData`, not just around tests.

        `setUpTestData` runs inside `setUpClass`, well before `_pre_setup`, and
        it is where most classes build their fixtures -- so with the scope only
        opened per test, every one of those fixture writes hit a scoped manager
        with no tenant and raised.

        Wrapping rather than overriding `setUpTestData` directly, because
        subclasses define their own and would shadow the mixin's. The wrapper
        creates the tenant, enters the scope, then calls whatever the subclass
        wrote. Both are unwound in `tearDownClass`.
        """
        original = cls.setUpTestData

        def wrapped(inner_cls):
            inner_cls._organisation, inner_cls._class_tenant = founding_tenant(
                inner_cls.tenant_slug
            )
            inner_cls._class_scope_token = context.set(inner_cls._class_tenant)
            original.__func__(inner_cls)

        cls.setUpTestData = classmethod(wrapped)
        try:
            super().setUpClass()
        finally:
            cls.setUpTestData = original

    @classmethod
    def tearDownClass(cls):
        token = getattr(cls, "_class_scope_token", None)
        if token is not None:
            context.reset(token)
            cls._class_scope_token = None
        super().tearDownClass()

    def _pre_setup(self):
        """Hooked here rather than in `setUp` on purpose.

        Test classes in this codebase routinely override `setUp` without
        calling `super()`, which silently skipped the mixin -- and the symptom
        was a KeyError on a response body, pointing nowhere near the cause. The
        request had gone out unprefixed, resolved no tenant, and been refused.

        `_pre_setup` always runs and is effectively never overridden, so the
        mixin cannot be switched off by accident. It also runs after
        `setUpTestData`, which is what lets the enrolment below see the users a
        class made.
        """
        super()._pre_setup()
        self._organisation, self._tenant = founding_tenant(self.tenant_slug)
        # Hold the scope open for the whole test. The middleware does this per
        # request, but a test also touches the ORM directly -- in setUpTestData,
        # in assertions -- and those calls are not inside a request. Without
        # this every one of them raises TenantScopeError.
        self._scope_token = context.set(self._tenant)
        if self.enrol_everyone:
            self.enrol_existing_users()
        self._point_client_at_tenant()

    def _post_teardown(self):
        # Released before the database is torn down, and defensively: a test
        # that failed inside setUp may never have opened one.
        token = getattr(self, "_scope_token", None)
        if token is not None:
            context.reset(token)
            self._scope_token = None
        super()._post_teardown()

    def enrol_existing_users(self):
        """One INSERT for the whole class's users, not one per user.

        This runs before every test in the suite, so a get_or_create per user
        was a query per user per test. `ignore_conflicts` leans on the
        (user, tenant, role) unique constraint to skip anybody already enrolled,
        which is also what makes it safe to call repeatedly.
        """
        from django.contrib.auth import get_user_model
        from tenancy.models import Membership

        Membership.objects.bulk_create(
            [
                Membership(user=user, tenant=self._tenant, role=user.role)
                for user in get_user_model().objects.all()
            ],
            ignore_conflicts=True,
        )

    def _point_client_at_tenant(self):
        """Rewrite /api/... to /api/t/<slug>/... on the way out.

        Hooked at `request()` rather than `generic()`: DRF's APIClient builds
        the environ through its own factory, so `generic` is not always on the
        path. By `request()` everything has converged on one dict with
        PATH_INFO in it, which is the only place guaranteed to be seen.
        """
        prefix = f"/api/t/{self._tenant.slug}"
        client = self.client
        original = client.request
        # Only DRF's APIClient has this; a plain django TestCase uses
        # django.test.Client, which does not. Those classes authenticate some
        # other way (or not at all), so there is simply nothing to hook.
        original_auth = getattr(client, "force_authenticate", None)
        if original_auth is None:
            return

        def force_authenticate(user=None, token=None):
            # `_pre_setup` runs before `setUp`, so classes that build their
            # users there were invisible to the first enrolment pass and would
            # arrive at the API as signed-in strangers. Enrolling the acting
            # user here catches them at the one moment it matters.
            if user is not None and self.enrol_everyone:
                self.member_for(user, user.role)
            return original_auth(user, token)

        client.force_authenticate = force_authenticate

        def request(**environ):
            path = environ.get("PATH_INFO", "")
            if path.startswith("/api/") and not path.startswith("/api/t/"):
                environ["PATH_INFO"] = prefix + path[len("/api"):]
            return original(**environ)

        client.request = request

    def member_for(self, user, role):
        """Open a Membership so `user` is somebody at this gym."""
        from tenancy.models import Membership

        row, _ = Membership.objects.get_or_create(
            user=user, tenant=self._tenant, role=role
        )
        return row
