"""Parse an uploaded CSV/XLSX and turn its rows into members, payments or
trainers. Import runs in two passes: `preview` (parse + validate, write
nothing) and `commit` (apply inside one transaction), so an admin always sees
what will happen before anything touches the database."""

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import openpyxl
from django.db import transaction

from accounts.models import MembershipStatus, MemberProfile, Role, User
from billing.models import PaymentMethod, PaymentStatus, Plan
from billing.services import record_payment

from .mapping import BILLING, MEMBER, REQUIRED, TRAINER, detect_columns
from tenancy.people import members_here, people_here

MAX_ROWS = 5000

DATE_FORMATS = [
    "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y",
    "%d/%m/%y", "%m/%d/%y", "%Y/%m/%d", "%d %b %Y", "%d %B %Y",
    "%b %d, %Y", "%B %d, %Y", "%d.%m.%Y",
]

STATUS_ALIASES = {
    "active": MembershipStatus.ACTIVE, "current": MembershipStatus.ACTIVE,
    "live": MembershipStatus.ACTIVE, "yes": MembershipStatus.ACTIVE,
    "y": MembershipStatus.ACTIVE, "1": MembershipStatus.ACTIVE,
    "true": MembershipStatus.ACTIVE, "enabled": MembershipStatus.ACTIVE,
    "paused": MembershipStatus.PAUSED, "hold": MembershipStatus.PAUSED,
    "onhold": MembershipStatus.PAUSED, "frozen": MembershipStatus.PAUSED,
    "freeze": MembershipStatus.PAUSED, "suspended": MembershipStatus.PAUSED,
    "expired": MembershipStatus.EXPIRED, "inactive": MembershipStatus.EXPIRED,
    "lapsed": MembershipStatus.EXPIRED, "cancelled": MembershipStatus.EXPIRED,
    "canceled": MembershipStatus.EXPIRED, "no": MembershipStatus.EXPIRED,
    "n": MembershipStatus.EXPIRED, "0": MembershipStatus.EXPIRED,
    "false": MembershipStatus.EXPIRED, "ended": MembershipStatus.EXPIRED,
}

METHOD_ALIASES = {
    "cash": PaymentMethod.CASH, "upi": PaymentMethod.UPI, "gpay": PaymentMethod.UPI,
    "googlepay": PaymentMethod.UPI, "phonepe": PaymentMethod.UPI, "paytm": PaymentMethod.UPI,
    "card": PaymentMethod.CARD, "credit": PaymentMethod.CARD, "creditcard": PaymentMethod.CARD,
    "debit": PaymentMethod.CARD, "debitcard": PaymentMethod.CARD, "visa": PaymentMethod.CARD,
    "mastercard": PaymentMethod.CARD, "banktransfer": PaymentMethod.BANK_TRANSFER,
    "bank": PaymentMethod.BANK_TRANSFER, "transfer": PaymentMethod.BANK_TRANSFER,
    "neft": PaymentMethod.BANK_TRANSFER, "imps": PaymentMethod.BANK_TRANSFER,
    "rtgs": PaymentMethod.BANK_TRANSFER, "cheque": PaymentMethod.BANK_TRANSFER,
    "check": PaymentMethod.BANK_TRANSFER, "netbanking": PaymentMethod.BANK_TRANSFER,
}

PAYMENT_STATUS_ALIASES = {
    "completed": PaymentStatus.COMPLETED, "complete": PaymentStatus.COMPLETED,
    "paid": PaymentStatus.COMPLETED, "success": PaymentStatus.COMPLETED,
    "successful": PaymentStatus.COMPLETED, "settled": PaymentStatus.COMPLETED,
    "pending": PaymentStatus.PENDING, "due": PaymentStatus.PENDING,
    "unpaid": PaymentStatus.PENDING, "outstanding": PaymentStatus.PENDING,
    "failed": PaymentStatus.FAILED, "declined": PaymentStatus.FAILED,
    "refunded": PaymentStatus.REFUNDED, "refund": PaymentStatus.REFUNDED,
}


class ImportError_(Exception):
    """Raised for problems with the file as a whole (not a single row)."""


#: An import names people by email, and `User` spans every gym on the
#: platform. Matching across that boundary let a gym adopt somebody else's
#: account -- renaming it, enrolling it here, and handing this gym's admin
#: its set-password and reset-MFA buttons. A row like that is refused.
FOREIGN_EMAIL = "That email belongs to an account at another gym."


def _key(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").strip().lower())


def parse_file(uploaded):
    """-> (headers, rows) where rows are dicts keyed by the original header."""
    name = (uploaded.name or "").lower()
    raw = uploaded.read()
    if not raw:
        raise ImportError_("The uploaded file is empty.")

    if name.endswith((".xlsx", ".xlsm", ".xltx")):
        headers, rows = _parse_xlsx(raw)
    elif name.endswith((".csv", ".txt", ".tsv")):
        headers, rows = _parse_csv(raw)
    else:
        raise ImportError_("Unsupported file type. Upload a .csv or .xlsx file.")

    if not headers:
        raise ImportError_("Could not find a header row in the file.")
    if not rows:
        raise ImportError_("The file has a header row but no data rows.")
    if len(rows) > MAX_ROWS:
        raise ImportError_(f"File has {len(rows)} rows; the limit is {MAX_ROWS} per import.")
    return headers, rows


def _parse_xlsx(raw):
    workbook = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    sheet = workbook.active
    rows_iter = sheet.iter_rows(values_only=True)
    headers = []
    for row in rows_iter:
        if any(str(c or "").strip() for c in row):
            headers = [str(c).strip() if c is not None else "" for c in row]
            break
    rows = []
    for row in rows_iter:
        if not any(str(c or "").strip() for c in row):
            continue
        rows.append({h: row[i] if i < len(row) else None for i, h in enumerate(headers) if h})
    return [h for h in headers if h], rows


def _parse_csv(raw):
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ImportError_("Could not decode the file; save it as UTF-8 CSV and retry.")

    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = [h.strip() for h in (reader.fieldnames or []) if h and h.strip()]
    rows = [r for r in reader if any(str(v or "").strip() for v in r.values())]
    return headers, rows


def to_text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def to_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = to_text(value)
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def to_decimal(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    # Strip currency symbols/thousand separators: "₹1,200.00" -> 1200.00
    cleaned = re.sub(r"[^0-9.\-]", "", to_text(value).replace(",", ""))
    if not cleaned or cleaned in ("-", "."):
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _enrol(user, role):
    """Give an imported account standing at the gym doing the import.

    Access is read off Membership. Without this, an imported member who later
    sets a password would log in to find nothing there at all.
    """
    from tenancy import context
    from tenancy.models import Membership

    Membership.objects.get_or_create(user=user, tenant=context.require(), role=role)


def _unique_username(base):
    base = re.sub(r"[^a-zA-Z0-9._-]", "", base) or "member"
    base = base[:140]
    candidate = base
    suffix = 1
    while User.objects.filter(username__iexact=candidate).exists():
        suffix += 1
        candidate = f"{base}{suffix}"
    return candidate


def _row_values(row, mapping, fields):
    return {field: row.get(header) for field, header in mapping.items() if field in fields}


def build_rows(rows, mapping, kind):
    """Validate every row, returning per-row dicts with `action` and `errors`.
    Never writes; `commit_rows` consumes exactly this output."""
    missing = [f for f in REQUIRED[kind] if f not in mapping]
    if missing:
        raise ImportError_(
            "Could not find a column for: "
            + ", ".join(f.replace("_", " ") for f in missing)
            + ". Map it manually below, or add it to the file."
        )

    builder = {MEMBER: _build_member, BILLING: _build_billing, TRAINER: _build_trainer}[kind]
    seen_emails = set()
    results = []
    for index, row in enumerate(rows):
        parsed = builder(row, mapping, seen_emails)
        parsed["row_number"] = index + 2  # +2: 1-indexed, and row 1 is the header
        results.append(parsed)
    return results


def _resolve_person_name(values):
    first = to_text(values.get("first_name"))
    last = to_text(values.get("last_name"))
    if not first and not last:
        return "", ""
    # Some exports put the whole name in one column; split on first space.
    if first and not last and " " in first:
        first, _, last = first.partition(" ")
    return first.strip(), last.strip()


def _build_member(row, mapping, seen_emails):
    values = _row_values(row, mapping, set(mapping))
    first, last = _resolve_person_name(values)
    email = to_text(values.get("email")).lower()
    errors = []

    if not first and not last:
        errors.append("No name in this row.")
    if email and "@" not in email:
        errors.append(f"'{email}' is not a valid email.")
        email = ""
    if email and email in seen_emails:
        errors.append("Duplicate email within this file.")
    if email:
        seen_emails.add(email)

    existing = members_here().filter(email__iexact=email).first() if email else None
    if email and existing is None and User.objects.filter(email__iexact=email).exists():
        errors.append(FOREIGN_EMAIL)
    status_raw = _key(values.get("membership_status"))

    return {
        "action": "update" if existing else "create",
        "errors": errors,
        "existing_id": existing.id if existing else None,
        "data": {
            "first_name": first,
            "last_name": last,
            "email": email,
            "username": to_text(values.get("username")),
            "phone": to_text(values.get("phone")),
            "date_of_birth": to_date(values.get("date_of_birth")),
            "join_date": to_date(values.get("join_date")),
            "membership_status": STATUS_ALIASES.get(status_raw, "") if status_raw else "",
            "emergency_contact_name": to_text(values.get("emergency_contact_name")),
            "emergency_contact_phone": to_text(values.get("emergency_contact_phone")),
        },
    }


def _build_billing(row, mapping, _seen):
    values = _row_values(row, mapping, set(mapping))
    errors = []

    email = to_text(values.get("email")).lower()
    username = to_text(values.get("username"))
    member_name = to_text(values.get("member_name"))

    member = None
    if email:
        member = members_here().filter(email__iexact=email).first()
    if not member and username:
        member = members_here().filter(username__iexact=username).first()
    if not member and member_name:
        parts = member_name.split()
        qs = members_here()
        if len(parts) >= 2:
            member = qs.filter(first_name__iexact=parts[0], last_name__iexact=parts[-1]).first()
        else:
            member = qs.filter(first_name__iexact=member_name).first()
    if not member:
        errors.append("No matching member -- import members first, or add an email column.")

    amount = to_decimal(values.get("amount"))
    if amount is None:
        errors.append("Missing or unreadable amount.")

    plan_name = to_text(values.get("plan"))
    plan = Plan.objects.filter(name__iexact=plan_name).first() if plan_name else None
    if plan_name and not plan:
        errors.append(f"Plan '{plan_name}' will be created.")

    method_raw = _key(values.get("method"))
    status_raw = _key(values.get("status"))

    return {
        "action": "create",
        "errors": [e for e in errors if not e.endswith("will be created.")],
        "warnings": [e for e in errors if e.endswith("will be created.")],
        "existing_id": member.id if member else None,
        "data": {
            "member_id": member.id if member else None,
            "member_label": member.username if member else (email or member_name),
            "plan_name": plan_name,
            "plan_id": plan.id if plan else None,
            "amount": str(amount) if amount is not None else "",
            "method": METHOD_ALIASES.get(method_raw, PaymentMethod.OTHER),
            "status": PAYMENT_STATUS_ALIASES.get(status_raw, PaymentStatus.COMPLETED),
            "paid_date": to_date(values.get("paid_date")),
            "period_start": to_date(values.get("period_start")),
            "period_end": to_date(values.get("period_end")),
            "external_reference": to_text(values.get("external_reference")),
            "notes": to_text(values.get("notes")),
        },
    }


def _build_trainer(row, mapping, seen_emails):
    values = _row_values(row, mapping, set(mapping))
    name = to_text(values.get("name"))
    first, last = _resolve_person_name(values)
    if not name:
        name = f"{first} {last}".strip()
    email = to_text(values.get("email")).lower()
    errors = []

    if not name:
        errors.append("No trainer name in this row.")
    if email and "@" not in email:
        errors.append(f"'{email}' is not a valid email.")
        email = ""
    if email and email in seen_emails:
        errors.append("Duplicate email within this file.")
    if email:
        seen_emails.add(email)

    if not to_text(values.get("email")):
        # A trainer only exists as an account now, and an account needs an
        # email -- so this row is refused and reported rather than committed to
        # nothing.
        errors.append("A trainer needs an email address to get an account.")

    existing = people_here().filter(email__iexact=email).first() if email else None
    if email and existing is None and User.objects.filter(email__iexact=email).exists():
        errors.append(FOREIGN_EMAIL)

    return {
        "action": "update" if existing else "create",
        "errors": errors,
        "existing_id": existing.id if existing else None,
        "data": {
            "name": name,
            "email": email,
            "username": to_text(values.get("username")),
            "phone": to_text(values.get("phone")),
            "specialty": to_text(values.get("specialty")),
            "bio": to_text(values.get("bio")),
        },
    }


@transaction.atomic
def commit_rows(built_rows, kind, *, actor):
    """Applies the previewed rows. Rows carrying errors are skipped, not
    aborted -- one bad row in a 900-row export shouldn't sink the import."""
    committer = {MEMBER: _commit_member, BILLING: _commit_billing, TRAINER: _commit_trainer}[kind]
    created = updated = skipped = 0
    problems = []

    for row in built_rows:
        if row.get("errors"):
            skipped += 1
            problems.append({"row_number": row["row_number"], "errors": row["errors"]})
            continue
        try:
            was_created = committer(row["data"], actor)
        except Exception as exc:  # a single malformed row must not kill the batch
            skipped += 1
            problems.append({"row_number": row["row_number"], "errors": [str(exc)]})
            continue
        created += was_created
        updated += not was_created

    return {"created": created, "updated": updated, "skipped": skipped, "problems": problems}


def _commit_member(data, _actor):
    user = members_here().filter(email__iexact=data["email"]).first() if data["email"] else None
    is_new = user is None
    if is_new and data["email"] and User.objects.filter(email__iexact=data["email"]).exists():
        raise ImportError_(FOREIGN_EMAIL)

    if is_new:
        username = data["username"] or data["email"].split("@")[0] or f"{data['first_name']}{data['last_name']}"
        user = User(username=_unique_username(username), role=Role.MEMBER)
        # Imported accounts have no password until the member resets it --
        # set_unusable_password keeps them from being logged into meanwhile.
        user.set_unusable_password()

    user.first_name = data["first_name"] or user.first_name
    user.last_name = data["last_name"] or user.last_name
    if data["email"]:
        user.email = data["email"]
    elif is_new:
        # email is unique+required on User; synthesise a placeholder so a
        # phone-only export still imports.
        user.email = f"{user.username}@imported.local"
    user.save()
    _enrol(user, Role.MEMBER)

    profile, _ = MemberProfile.objects.get_or_create(user=user)
    for field in ("phone", "emergency_contact_name", "emergency_contact_phone"):
        if data[field]:
            setattr(profile, field, data[field])
    if data["date_of_birth"]:
        profile.date_of_birth = data["date_of_birth"]
    if data["membership_status"]:
        profile.membership_status = data["membership_status"]
    profile.save()

    if data["join_date"]:
        # join_date is auto_now_add, so it needs a direct UPDATE to preserve
        # the real joining date from the old system.
        MemberProfile.objects.filter(pk=profile.pk).update(join_date=data["join_date"])
    return is_new


def _commit_billing(data, actor):
    member = User.objects.get(pk=data["member_id"])
    plan = None
    if data["plan_id"]:
        plan = Plan.objects.filter(pk=data["plan_id"]).first()
    if plan is None:
        name = data["plan_name"] or "Imported"
        duration = 30
        if data["period_start"] and data["period_end"]:
            duration = max((data["period_end"] - data["period_start"]).days, 1)
        plan, _ = Plan.objects.get_or_create(
            name=name,
            defaults={
                "price": Decimal(data["amount"] or 0),
                "duration_days": duration,
                "description": "Created automatically during data import.",
            },
        )

    payment = record_payment(
        member=member,
        plan=plan,
        amount=Decimal(data["amount"]),
        method=data["method"],
        paid_date=data["paid_date"],
        notes=data["notes"],
        recorded_by=actor,
        status=data["status"],
        external_reference=data["external_reference"],
    )
    # record_payment derives the period by stacking on existing history; when
    # the source file states the real period, that wins.
    if data["period_start"] or data["period_end"]:
        payment.period_start = data["period_start"] or payment.period_start
        payment.period_end = data["period_end"] or payment.period_end
        payment.save(update_fields=["period_start", "period_end"])
    return True


def _commit_trainer(data, _actor):
    # A trainer is an account at this gym. There is no separate profile to fall
    # back on any more, so `_build_trainer` refuses rows without an email rather
    # than letting them reach here and become nothing.
    user = people_here().filter(email__iexact=data["email"]).first()
    is_new = user is None
    if is_new and User.objects.filter(email__iexact=data["email"]).exists():
        raise ImportError_(FOREIGN_EMAIL)
    if is_new:
        username = data["username"] or data["email"].split("@")[0] or data["name"]
        user = User(
            username=_unique_username(username),
            email=data["email"],
            role=Role.TRAINER,
        )
        parts = data["name"].split()
        user.first_name = parts[0] if parts else ""
        user.last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
        user.set_unusable_password()
        user.save()
    elif user.role == Role.MEMBER:
        user.role = Role.TRAINER
        user.save(update_fields=["role", "is_staff"])

    MemberProfile.objects.get_or_create(user=user)
    _enrol(user, Role.TRAINER)
    return is_new
