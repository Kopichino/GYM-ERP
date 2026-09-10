"""Turning a lead into a member.

Conversion is the one place the CRM writes outside its own tables, so it lives
here rather than in a view: creating the account, stamping the enquiry, and
closing the referral loop have to happen together or not at all.
"""

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils.text import slugify

from accounts.models import MemberProfile, Role, User

from .models import EnquiryStatus


class ConversionError(Exception):
    """A conversion the front desk needs told about, not a bug."""


def suggest_username(name):
    """A readable handle from the person's name, e.g. "Ravi Menon" ->
    "ravi.menon", with a numeric suffix only when it is actually taken."""
    base = slugify(name).replace("-", ".") or "member"
    candidate = base
    suffix = 2
    while User.objects.filter(username__iexact=candidate).exists():
        candidate = f"{base}{suffix}"
        suffix += 1
    return candidate


def convert(enquiry, *, username=None, email=None, password=None, converted_by=None):
    """Creates the member account this lead becomes.

    The account is created without a usable password unless one is given, the
    same as any other account an admin opens at the desk -- the member sets
    their own later.
    """
    if enquiry.converted_user_id:
        raise ConversionError(f"{enquiry.name} has already been converted.")

    username = (username or suggest_username(enquiry.name)).strip()
    if User.objects.filter(username__iexact=username).exists():
        raise ConversionError(f"The username '{username}' is taken.")

    email = (email if email is not None else enquiry.email) or ""
    parts = enquiry.name.strip().split(None, 1)

    if password:
        # Signup and admin account creation both run the configured validators;
        # converting a lead is a third way to set a first password, and without
        # this it was the one route that would accept "123456".
        try:
            password_validation.validate_password(password)
        except DjangoValidationError as exc:
            raise ConversionError(" ".join(exc.messages)) from exc

    with transaction.atomic():
        user = User(
            username=username,
            email=email,
            first_name=parts[0] if parts else "",
            last_name=parts[1] if len(parts) > 1 else "",
            role=Role.MEMBER,
        )
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        MemberProfile.objects.create(user=user, phone=enquiry.phone)

        enquiry.converted_user = user
        enquiry.status = EnquiryStatus.JOINED
        enquiry.save(update_fields=["converted_user", "status", "updated_at"])

        # If this lead came in as a referral, the referrer's side has to learn
        # about it too -- otherwise their reward never becomes due.
        referral = getattr(enquiry, "referral", None)
        if referral is not None and referral.referred_user_id is None:
            referral.referred_user = user
            referral.save(update_fields=["referred_user"])

    return user
