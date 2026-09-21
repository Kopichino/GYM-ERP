"""Trainer commission was removed from the product.

The rules, entries and payouts already recorded are kept as history, untouched.
These two functions stay only because the payment flow still calls them when a
payment is recorded or voided; they deliberately do nothing, so taking a payment
earns nobody a commission and voiding one rewrites no past entry.
"""


def accrue_for_payment(payment):
    """Formerly raised a commission entry for a payment. Now does nothing."""
    return None


def void_for_payment(payment):
    """Formerly voided a payment's commission entry. Now leaves history alone."""
    return None
