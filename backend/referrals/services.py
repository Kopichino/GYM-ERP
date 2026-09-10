"""The one place a referral is claimed or paid out.

The reward is applied by writing a zero-amount payment through
`billing.services.record_payment`, so a membership only ever gains time through
the single write path that also re-syncs the derived status. A referral bonus
that quietly edited `period_end` would be a second, silent way for a membership
to change -- exactly what the ledger exists to prevent.
"""

from decimal import Decimal

from django.db import IntegrityError, transaction

from billing.models import PaymentMethod, PaymentStatus
from billing.services import get_latest_completed_payment, record_payment

from .models import Referral, ReferralProgram, ReferralReward, ReferralStatus, make_code


class ReferralError(Exception):
    """Something a member or the front desk needs told, not a bug."""


def code_for(member):
    """The member's share code, minted on first use.

    Codes are only handed out when someone actually asks for one, so a gym that
    never runs a referral programme carries none.
    """
    profile = getattr(member, "profile", None)
    if profile is None:
        raise ReferralError("That account has no member profile.")
    if profile.referral_code:
        return profile.referral_code
    # A collision on a 6-character alphabet is unlikely but not impossible;
    # the unique index decides, and we simply try again.
    for _ in range(10):
        candidate = make_code()
        try:
            with transaction.atomic():
                profile.referral_code = candidate
                profile.save(update_fields=["referral_code"])
            return candidate
        except IntegrityError:
            continue
    raise ReferralError("Could not allocate a referral code. Try again.")


def resolve_code(code):
    """The member behind a code, or None. Case and spacing are forgiven --
    these get read out over the phone and typed back in by someone else."""
    if not code:
        return None
    from accounts.models import MemberProfile

    cleaned = code.strip().replace(" ", "").replace("-", "").upper()
    profile = MemberProfile.objects.filter(referral_code=cleaned).select_related("user").first()
    return profile.user if profile else None


def claim(code, new_user):
    """Links a fresh signup to whoever referred them.

    Returns the Referral, or None when the code is blank or unknown -- a bad
    code must never block a signup, since the person joining is not the one who
    got it wrong.
    """
    referrer = resolve_code(code)
    if referrer is None or referrer == new_user:
        return None
    # An existing pending referral for this person (raised by the referrer
    # before they signed up) is completed rather than duplicated.
    pending = (
        Referral.objects.filter(referrer=referrer, referred_user__isnull=True)
        .filter(name__iexact=new_user.get_full_name() or new_user.username)
        .first()
    )
    if pending:
        pending.referred_user = new_user
        pending.save(update_fields=["referred_user"])
        return pending
    return Referral.objects.create(
        referrer=referrer,
        name=new_user.get_full_name() or new_user.username,
        email=new_user.email,
        referred_user=new_user,
        notes="Signed up with the referral code.",
    )


def grant_reward(referral, granted_by=None, days=None, notes=""):
    """Pays the referrer their free days.

    Refuses rather than guessing: a referral that hasn't converted, or one
    already paid, is a mistake worth surfacing at the counter.
    """
    if hasattr(referral, "reward"):
        raise ReferralError("That referral has already been rewarded.")
    if referral.status != ReferralStatus.JOINED:
        raise ReferralError("That referral hasn't joined and paid yet.")

    program = ReferralProgram.current()
    days = days if days is not None else (program.reward_days if program else 0)
    if not days:
        raise ReferralError("No referral programme is running, so there is nothing to grant.")

    referrer = referral.referrer
    latest = get_latest_completed_payment(referrer)
    if latest is None:
        raise ReferralError(
            f"{referrer.username} has no plan on file, so there is no membership to extend."
        )

    with transaction.atomic():
        payment = record_payment(
            member=referrer,
            plan=latest.plan,
            amount=Decimal("0.00"),
            method=PaymentMethod.OTHER,
            status=PaymentStatus.COMPLETED,
            duration_days=days,
            notes=f"Referral reward: {days} free days for referring {referral.name}.",
            recorded_by=granted_by,
        )
        return ReferralReward.objects.create(
            referral=referral,
            days_granted=days,
            payment=payment,
            granted_by=granted_by,
            notes=notes,
        )
