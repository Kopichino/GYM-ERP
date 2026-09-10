"""Gapless invoice numbering, under genuine concurrency.

`InvoiceCounter.next_for` takes a row lock so numbers are handed out one caller
at a time. That lock is the entire mechanism -- there is no unique index that
can express "no holes" -- which makes this the invariant most dependent on the
database actually being Postgres, and the one least worth trusting a green
SQLite run about.

Two properties are checked, and they are different:

* uniqueness -- no two invoices share a number;
* gaplessness -- the numbers issued form 1..n with nothing missing. A statutory
  sequence with a hole in it is a filing problem, and a burnt number cannot be
  recovered after the fact.

The sequential half of this lives in `tests.py::GaplessNumberingTests`.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from accounts.models import MemberProfile, Role
from billing.models import Payment, Plan
from billing.services import record_payment
from core.testing import (
    losers,
    requires_row_locks,
    run_concurrently,
    winners,
)

from .models import Invoice, InvoiceCounter, financial_year_for
from .services import issue_invoice

User = get_user_model()


def make_user(username, role=Role.MEMBER):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    if role == Role.MEMBER:
        MemberProfile.objects.get_or_create(user=user)
    return user


class _ScopedTransactionTestCase(TransactionTestCase):
    """A tenant in scope for the whole test.

    These drive services directly rather than through the API, so nothing has
    resolved a tenant for them -- and the scoped managers refuse to run without
    one. Threads do NOT inherit a ContextVar context, so `run_concurrently`
    copies it across explicitly; see core.testing.

    `setUp`, not `_pre_setup`: on TransactionTestCase that hook is a
    *classmethod*, so overriding it as an instance method breaks its contract
    and every class errors before a test runs. The subclasses below therefore
    have to call super().setUp() -- without it the scope never opens and every
    worker thread raises.
    """

    def setUp(self):
        super().setUp()
        from core.testing import founding_tenant
        from tenancy import context

        _, self.tenant = founding_tenant("racegym")
        self._tenancy_token = context.set(self.tenant)

    def tearDown(self):
        from tenancy import context

        token = getattr(self, "_tenancy_token", None)
        if token is not None:
            context.reset(token)
            self._tenancy_token = None
        super().tearDown()


@requires_row_locks
class ConcurrentNumberingTests(_ScopedTransactionTestCase):
    # No reset_sequences: the tenancy backfill migration inserts an
    # Organisation at id 1, and resetting the sequence would hand that id out a
    # second time. Nothing here depends on primary key values anyway -- the
    # gapless assertions read `InvoiceCounter.last_number`, which is a column
    # default of zero, not a database sequence.

    def setUp(self):
        super().setUp()
        # The counter is keyed on (tenant, financial year), so a payment with no
        # branch would draw from its own null-keyed sequence and the gapless
        # assertions below would be measuring nothing.
        # The base class already created a tenant and put it in scope; making a
        # second one here left the payments stamped with the scoped tenant while
        # the assertions filtered on a different one.
        self.plan = Plan.objects.create(
            name="Monthly", price=Decimal("1180"), duration_days=30
        )

    def _payments(self, count, prefix):
        made = [
            record_payment(
                member=make_user(f"{prefix}_{i}"),
                plan=self.plan,
                amount=Decimal("1180"),
                method="cash",
            )
            for i in range(count)
        ]
        Payment.objects.filter(pk__in=[p.pk for p in made]).update(tenant=self.tenant)
        for payment in made:
            payment.refresh_from_db()
        return made

    def _sequence(self, day):
        fy = financial_year_for(day)
        return sorted(
            Invoice.objects.filter(financial_year=fy).values_list("sequence", flat=True)
        )

    def test_simultaneous_checkouts_get_different_numbers(self):
        payments = self._payments(6, "conc_num")
        results = run_concurrently(lambda i: issue_invoice(payments[i]), count=6)

        self.assertEqual(len(winners(results)), 6, losers(results))
        numbers = {invoice.number for invoice in winners(results)}
        self.assertEqual(len(numbers), 6)

    def test_the_sequence_is_gapless_after_a_burst(self):
        payments = self._payments(8, "conc_gap")
        run_concurrently(lambda i: issue_invoice(payments[i]), count=8)

        self.assertEqual(self._sequence(payments[0].paid_date), list(range(1, 9)))

    def test_the_counter_matches_the_invoices_issued(self):
        payments = self._payments(5, "conc_count")
        run_concurrently(lambda i: issue_invoice(payments[i]), count=5)

        counter = InvoiceCounter.objects.get(
            financial_year=financial_year_for(payments[0].paid_date)
        )
        self.assertEqual(counter.last_number, Invoice.objects.count())

    def test_concurrent_retries_of_one_payment_issue_one_invoice(self):
        """The retried-webhook case, raced rather than repeated.

        Both callers pass the idempotency check at the top of `issue_invoice`
        before either writes. The payment one-to-one settles it, and the loser
        must hand back the winner's invoice -- without leaving a hole where its
        own number would have been.
        """
        payment = self._payments(1, "conc_retry")[0]
        results = run_concurrently(lambda _: issue_invoice(payment), count=4)

        self.assertEqual(len(losers(results)), 0, losers(results))
        issued = {invoice.pk for invoice in winners(results)}
        self.assertEqual(len(issued), 1)
        self.assertEqual(Invoice.objects.filter(payment=payment).count(), 1)
        self.assertEqual(self._sequence(payment.paid_date), [1])

    def test_a_mixed_burst_of_new_and_retried_payments_stays_gapless(self):
        fresh = self._payments(4, "conc_mixed")
        repeated = fresh[0]
        work = list(fresh) + [repeated, repeated]

        run_concurrently(lambda i: issue_invoice(work[i]), count=len(work))

        self.assertEqual(Invoice.objects.count(), 4)
        self.assertEqual(self._sequence(fresh[0].paid_date), [1, 2, 3, 4])
