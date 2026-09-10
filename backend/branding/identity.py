"""Who this gym is, for the parts of the system that print it.

One helper rather than `getattr(settings, ...)` scattered around, so that when a
gym fills in the branding page their name appears on invoices and in email as
well as in the portal. The environment stays the fallback: an install that has
never opened the branding page still renders as something sensible instead of
blank.
"""

from django.conf import settings


def _row():
    # Imported lazily: this module is called from invoicing and messaging, and a
    # module-level query would run at import time.
    from .models import Branding

    return Branding.current()


def gym_name():
    row = _row()
    return (row.name if row else "") or getattr(settings, "GYM_NAME", "IRONCORE")


def gstin():
    row = _row()
    return (row.gstin if row else "") or getattr(settings, "GYM_GSTIN", "")


def state():
    row = _row()
    return (row.state if row else "") or getattr(settings, "GYM_STATE", "")


def address():
    row = _row()
    return (row.address if row else "") or ""


def contact_line():
    """Phone and email on one line, for an invoice footer. Empty when neither
    is filled in, so nothing prints a stray separator."""
    row = _row()
    if row is None:
        return ""
    parts = [p for p in (row.phone, row.email, row.website) if p]
    return "  |  ".join(parts)
