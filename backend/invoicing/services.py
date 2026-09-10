"""Turning a payment into a GST invoice.

The amount a member paid is treated as tax-inclusive, which is how gym pricing
is quoted in practice -- a 1500 membership is 1500 at the counter, not 1500 plus
tax. The taxable value and tax are therefore back-calculated out of the total
rather than added on top.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import IntegrityError, transaction

from .models import Invoice, InvoiceCounter

TWO_DP = Decimal("0.01")


def _q(value):
    return Decimal(value).quantize(TWO_DP, rounding=ROUND_HALF_UP)


def split_tax(total, rate, interstate):
    """Back out tax from a tax-inclusive total.

    Intra-state supply splits into CGST + SGST at half the rate each;
    inter-state is a single IGST at the full rate.
    """
    total = Decimal(total)
    rate = Decimal(rate)
    taxable = _q(total / (1 + rate / 100))
    tax = _q(total - taxable)

    if interstate:
        return taxable, Decimal("0.00"), Decimal("0.00"), tax
    half = _q(tax / 2)
    # Give any rounding remainder to CGST so the parts always sum to the whole.
    return taxable, tax - half, half, Decimal("0.00")


def issue_invoice(payment, place_of_supply="", buyer_gstin="", tax_rate=None):
    """Creates the invoice for a payment, or returns the existing one.

    Idempotent on purpose: re-running checkout or a retried webhook must not
    burn a second statutory number for the same sale.
    """
    existing = Invoice.objects.filter(payment=payment).first()
    if existing:
        return existing

    rate = Decimal(tax_rate if tax_rate is not None else getattr(settings, "GST_RATE", 18))
    # The branding row wins where a gym has filled it in; settings are the
    # fallback so an unconfigured install still issues a valid invoice.
    from branding.identity import gstin as gym_gstin, state as gym_state

    seller_state = gym_state()
    place = place_of_supply or seller_state
    interstate = bool(seller_state and place and place.strip().lower() != seller_state.strip().lower())

    taxable, cgst, sgst, igst = split_tax(payment.amount, rate, interstate)

    # Allocating the number and writing the invoice have to be one unit. Left
    # apart, a number handed out by a committed counter bump whose insert then
    # failed is gone for good -- and a statutory sequence with a hole in it is
    # exactly what the counter exists to prevent.
    # The invoice belongs to the branch that took the money.
    tenant = payment.tenant
    # A branch may set its own prefix; "INV" keeps pre-tenancy numbers looking
    # exactly as they did, so nothing already issued appears to change format.
    prefix = (getattr(tenant, "invoice_prefix", "") or "INV").strip() or "INV"

    try:
        with transaction.atomic():
            fy, sequence = InvoiceCounter.next_for(tenant, payment.paid_date)
            return Invoice.objects.create(
                payment=payment,
                tenant=tenant,
                number=f"{prefix}/{fy}/{sequence:05d}",
                financial_year=fy,
                sequence=sequence,
                issued_on=payment.paid_date,
                seller_gstin=gym_gstin(),
                buyer_gstin=buyer_gstin,
                place_of_supply=place,
                taxable_value=taxable,
                cgst=cgst,
                sgst=sgst,
                igst=igst,
                total=_q(payment.amount),
                tax_rate=rate,
            )
    except IntegrityError:
        # Two retries of the same webhook raced past the check at the top and
        # both got here; the payment one-to-one settled it. Our rollback put
        # the number back, so the winner's invoice is simply the answer.
        existing = Invoice.objects.filter(payment=payment).first()
        if existing:
            return existing
        raise
