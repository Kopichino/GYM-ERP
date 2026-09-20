"""Two-step sign-in endpoints.

Grouped by what the caller has proven so far:

* **Signing in** -- `/auth/mfa/login/...`. The caller has given the right
  password and holds the pending token `LoginView` returned, and nothing more.
  No session exists yet, so these accept no bearer token: a stale one left in a
  browser must not turn a sign-in into a 401.
* **Signed in** -- `/auth/mfa/...`. Managing your own authenticator and recovery
  codes. Anything that changes how the account signs in asks for more than the
  session: the password to move to a new phone, a current code for a fresh set
  of recovery codes. A stolen access token lasts fifteen minutes, and should not
  be enough to lock the real owner out for good.
* **An admin resetting someone** who has lost both phone and codes -- an action
  on `AdminUserViewSet`, so it reaches accounts at the admin's own gym only.
"""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import mfa
from .models import MfaDevice, MfaRecoveryCode
from .throttling import MfaAttemptHourlyThrottle, MfaAttemptThrottle
from core.security_log import security_event
from .tokens import revoke_refresh_tokens
from .views import session_response

SIGN_IN_EXPIRED = {
    "detail": "This sign-in has expired. Enter your password again.",
    "reason": "mfa_token_invalid",
}
ALREADY_SET_UP = {
    "detail": "Two-step sign-in is already set up on this account. Sign in with a code.",
    "reason": "mfa_already_set_up",
}
NOT_SET_UP = {
    "detail": "Two-step sign-in is not set up on this account yet.",
    "reason": "mfa_setup_required",
}
NO_SETUP_STARTED = {
    "detail": "Start setting up your authenticator app first.",
    "reason": "mfa_setup_not_started",
}
WRONG_CODE = {
    "code": [
        "That code is not right. Codes change every 30 seconds, so use the one "
        "showing now, and check your phone sets its time automatically."
    ]
}

#: Every endpoint that checks a code: per IP, plus per account in two windows.
CODE_THROTTLES = [ScopedRateThrottle, MfaAttemptThrottle, MfaAttemptHourlyThrottle]


# ---------------------------------------------------------------- helpers


def confirmed_device(user):
    return (
        MfaDevice.objects.filter(user=user, confirmed_at__isnull=False).exclude(secret="").first()
    )


def remaining_recovery_codes(user):
    return MfaRecoveryCode.objects.filter(user=user, used_at__isnull=True).count()


def consume_code(device, code):
    """True if `code` is right for `device` and has not been accepted before.

    The update is conditional on the stored step, so two requests racing with
    the same code cannot both succeed -- one of them updates no row.
    """
    step = mfa.matching_step(device.secret, code, after=device.last_used_step)
    if step is None:
        return False
    won = (
        MfaDevice.objects.filter(pk=device.pk)
        .filter(Q(last_used_step__isnull=True) | Q(last_used_step__lt=step))
        .update(last_used_step=step)
    )
    return won == 1


def consume_recovery_code(user, code):
    """True if `code` is one of this person's unused recovery codes. Uses it up."""
    if not mfa.normalise_recovery_code(code):
        return False
    used = MfaRecoveryCode.objects.filter(
        user=user, code_hash=mfa.hash_recovery_code(code), used_at__isnull=True
    ).update(used_at=timezone.now())
    return used == 1


def issue_recovery_codes(user):
    """A fresh set, replacing the old one entirely. The plain codes are returned
    here and never again -- only their hashes are kept."""
    codes = mfa.new_recovery_codes()
    MfaRecoveryCode.objects.filter(user=user).delete()
    MfaRecoveryCode.objects.bulk_create(
        [MfaRecoveryCode(user=user, code_hash=mfa.hash_recovery_code(code)) for code in codes]
    )
    return codes


def setup_payload(user):
    """The key for a new authenticator, held as pending until a code proves it.

    Asking again returns the same pending key rather than a new one. The page
    may ask twice -- a reload, or React running an effect twice in development
    -- and replacing the key would leave the QR code already scanned useless.
    """
    device, _ = MfaDevice.objects.get_or_create(user=user)
    if not device.pending_secret:
        device.pending_secret = mfa.new_secret()
        device.save(update_fields=["pending_secret"])
    return {
        "secret": device.pending_secret,
        "otpauth_uri": mfa.provisioning_uri(device.pending_secret, user.username),
        "issuer": mfa.issuer(),
        "account_name": user.username,
    }


def confirm_pending(user, code):
    """Make the pending key the live one. Returns `(recovery_codes, error)`.

    The old key, if any, keeps working until this moment, so a setup abandoned
    halfway -- or a mistyped code -- never locks anyone out.
    """
    with transaction.atomic():
        device = MfaDevice.objects.select_for_update().filter(user=user).first()
        if device is None or not device.pending_secret:
            return None, NO_SETUP_STARTED
        step = mfa.matching_step(device.pending_secret, code)
        if step is None:
            return None, WRONG_CODE

        device.secret = device.pending_secret
        device.pending_secret = ""
        device.confirmed_at = timezone.now()
        device.last_used_step = step
        device.save(update_fields=["secret", "pending_secret", "confirmed_at", "last_used_step"])
        return issue_recovery_codes(user), None


def reset_mfa(user):
    """Forget someone's authenticator and codes; they set it up again at next sign-in.

    Their sessions end too. Whoever reports a lost phone may not be the only
    person holding it.
    """
    MfaDevice.objects.filter(user=user).delete()
    MfaRecoveryCode.objects.filter(user=user).delete()
    revoke_refresh_tokens(user)


# ---------------------------------------------------------------- signing in


class _SignInStep(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "mfa"
    throttle_classes = [ScopedRateThrottle]

    def pending_user(self, request):
        return mfa.user_from_pending(request.data.get("mfa_token"))


class MfaLoginVerifyView(_SignInStep):
    """Step two: a code from the authenticator app, or one recovery code."""

    throttle_classes = CODE_THROTTLES

    def post(self, request):
        user = self.pending_user(request)
        if user is None:
            return Response(SIGN_IN_EXPIRED, status=status.HTTP_400_BAD_REQUEST)
        device = confirmed_device(user)
        if device is None:
            return Response(NOT_SET_UP, status=status.HTTP_400_BAD_REQUEST)

        recovery_code = request.data.get("recovery_code")
        if recovery_code:
            if not consume_recovery_code(user, recovery_code):
                security_event("mfa_recovery_code_failed", request, warning=True, user=user.pk)
                return Response(
                    {"recovery_code": ["That recovery code is not right, or has already been used."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            security_event("mfa_recovery_code_used", request, user=user.pk, count=remaining_recovery_codes(user))
            # Said on the way in, so someone down to their last code finds out
            # while they can still do something about it.
            return session_response(
                user,
                {
                    "used_recovery_code": True,
                    "recovery_codes_remaining": remaining_recovery_codes(user),
                },
            )

        if not consume_code(device, request.data.get("code")):
            security_event("mfa_code_failed", request, warning=True, user=user.pk)
            return Response(WRONG_CODE, status=status.HTTP_400_BAD_REQUEST)
        return session_response(user)


class MfaLoginSetupView(_SignInStep):
    """First sign-in since two-step became required: the key to scan."""

    def post(self, request):
        user = self.pending_user(request)
        if user is None:
            return Response(SIGN_IN_EXPIRED, status=status.HTTP_400_BAD_REQUEST)
        # The password alone must never be able to swap the authenticator on an
        # account that has one -- that would make the second step pointless.
        if confirmed_device(user) is not None:
            return Response(ALREADY_SET_UP, status=status.HTTP_409_CONFLICT)
        return Response(setup_payload(user))


class MfaLoginConfirmView(_SignInStep):
    """Finishes setup at sign-in: a code from the new app opens the session."""

    throttle_classes = CODE_THROTTLES

    def post(self, request):
        user = self.pending_user(request)
        if user is None:
            return Response(SIGN_IN_EXPIRED, status=status.HTTP_400_BAD_REQUEST)
        if confirmed_device(user) is not None:
            return Response(ALREADY_SET_UP, status=status.HTTP_409_CONFLICT)

        codes, error = confirm_pending(user, request.data.get("code"))
        if error:
            return Response(error, status=status.HTTP_400_BAD_REQUEST)
        return session_response(user, {"recovery_codes": codes})


# ---------------------------------------------------------------- signed in


class MfaStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        device = confirmed_device(request.user)
        return Response(
            {
                "enabled": device is not None,
                "confirmed_at": device.confirmed_at if device else None,
                "recovery_codes_remaining": remaining_recovery_codes(request.user) if device else 0,
                "required": mfa.required_for(request.user),
            }
        )


class MfaSetupView(APIView):
    """Start moving to a new phone. Asks for the password, like changing it does."""

    permission_classes = [IsAuthenticated]
    # This checks a password, so it gets the same budget as logging in.
    throttle_scope = "login"

    def post(self, request):
        if not request.user.check_password(str(request.data.get("password") or "")):
            return Response(
                {"password": ["That is not your current password."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(setup_payload(request.user))


class MfaConfirmView(APIView):
    """Finish moving to a new phone."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [MfaAttemptThrottle, MfaAttemptHourlyThrottle]

    def post(self, request):
        codes, error = confirm_pending(request.user, request.data.get("code"))
        if error:
            return Response(error, status=status.HTTP_400_BAD_REQUEST)
        # Sessions opened with the old authenticator end -- the usual reason to
        # replace one is that the old phone is gone. This one is re-issued, so
        # the page you did it on stays signed in.
        revoke_refresh_tokens(request.user)
        return session_response(request.user, {"recovery_codes": codes})


class MfaRecoveryCodesView(APIView):
    """A new set of recovery codes, for a current code from the app."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [MfaAttemptThrottle, MfaAttemptHourlyThrottle]

    def post(self, request):
        device = confirmed_device(request.user)
        if device is None:
            return Response(NOT_SET_UP, status=status.HTTP_400_BAD_REQUEST)
        if not consume_code(device, request.data.get("code")):
            return Response(WRONG_CODE, status=status.HTTP_400_BAD_REQUEST)
        return Response({"recovery_codes": issue_recovery_codes(request.user)})
