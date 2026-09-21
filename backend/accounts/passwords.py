"""Forgotten, reset and changed passwords.

Every way a password changes here ends the sessions the old one opened. A
refresh token lives for a week and survives a new password hash on its own
(see `tokens.revoke_refresh_tokens`), so a reset meant to lock someone out of a
compromised account would otherwise leave them signed in.

These are about the *person*, not a gym -- one account can belong to several --
so they sit on the platform routes with no tenant in the path, and the reset
email comes from the platform address rather than from any one gym's.
"""

import logging
import re

from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from tenancy.email_identity import platform_sender

from .models import User
from core.security_log import security_event
from .tokens import revoke_refresh_tokens
from .views import _set_refresh_cookie

logger = logging.getLogger(__name__)

#: Addresses the importer invents for phone-only rows. Nobody can receive mail
#: there, so a reset link is never sent to one -- an admin sets the password.
PLACEHOLDER_EMAIL = re.compile(r"@imported\.local$", re.IGNORECASE)

#: One reply for every forgot-password request, known address or not.
FORGOT_REPLY = {
    "detail": "If that email has an account, a link to reset the password is on its way."
}


def reset_link(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?uid={uid}&token={token}"


def send_reset_email(user):
    """Email `user` a single-use link to choose a new password."""
    hours = max(1, settings.PASSWORD_RESET_TIMEOUT // 3600)
    name = user.first_name or user.username
    body = (
        f"Hi {name},\n\n"
        f"Someone asked to reset the password for your account ({user.username}). "
        "If that was you, choose a new one here:\n\n"
        f"{reset_link(user)}\n\n"
        f"The link works once and expires in {hours} hours. If you did not ask for "
        "this, you can ignore this email -- your password has not changed.\n"
    )
    send_mail(
        subject="Reset your password",
        message=body,
        from_email=platform_sender(),
        recipient_list=[user.email],
    )


def _user_from_uid(uid):
    try:
        return User.objects.get(pk=force_str(urlsafe_base64_decode(str(uid or ""))))
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None


def _password_errors(password, user):
    try:
        password_validation.validate_password(password, user)
    except DjangoValidationError as exc:
        return list(exc.messages)
    return []


class PasswordForgotView(APIView):
    """Asks for a reset link.

    Answers identically whether or not the address has an account. Saying which
    emails are registered would turn this into a way to learn who belongs to a
    gym.

    This is also how an imported member sets their *first* password. They are
    created without a usable one, and Django's own reset form silently skips
    exactly those accounts -- which is why this uses the token generator
    directly instead.
    """

    permission_classes = [AllowAny]
    # A stale bearer token in a signed-out browser must not turn this into a 401.
    authentication_classes = []
    throttle_scope = "password_reset"

    def post(self, request):
        email = str(request.data.get("email") or "").strip()
        if email and not PLACEHOLDER_EMAIL.search(email):
            user = User.objects.filter(email__iexact=email, is_active=True).first()
            if user is not None:
                try:
                    send_reset_email(user)
                except Exception:  # noqa: BLE001 -- the reply must not reveal this
                    logger.exception("could not send a password reset email to user %s", user.pk)
        return Response(FORGOT_REPLY)


class PasswordResetView(APIView):
    """Sets a new password from an emailed link.

    Single use with no bookkeeping: the token is derived from the current
    password hash, so the moment the password changes the link stops working.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "password_reset"

    def post(self, request):
        user = _user_from_uid(request.data.get("uid"))
        token = str(request.data.get("token") or "")
        if (
            user is None
            or not user.is_active
            or not default_token_generator.check_token(user, token)
        ):
            security_event("password_reset_link_invalid", request, warning=True)
            return Response(
                {"detail": "This reset link is invalid or has expired. Ask for a new one."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        password = str(request.data.get("password") or "")
        errors = _password_errors(password, user)
        if errors:
            return Response({"password": errors}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(password)
        user.save(update_fields=["password"])
        revoke_refresh_tokens(user)
        security_event("password_reset_completed", request, user=user.pk)
        return Response({"detail": "Your password has been changed. You can log in now."})


class PasswordChangeView(APIView):
    """Change your own password while signed in.

    Asks for the current password first. Changing it is the one thing a stolen
    session should not be able to do quietly, because it locks the real owner
    out -- so holding a valid token is not enough on its own.
    """

    permission_classes = [IsAuthenticated]
    # The same budget as logging in: this checks a password, and without a limit
    # a stolen session could guess the current one here instead.
    throttle_scope = "login"

    def post(self, request):
        user = request.user
        if not user.check_password(str(request.data.get("current_password") or "")):
            security_event("password_change_failed", request, warning=True, user=user.pk)
            return Response(
                {"current_password": ["That is not your current password."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_password = str(request.data.get("new_password") or "")
        errors = _password_errors(new_password, user)
        if errors:
            return Response({"new_password": errors}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save(update_fields=["password"])
        revoke_refresh_tokens(user)
        security_event("password_changed", request, user=user.pk)

        # Revoking ended this session's refresh token along with every other.
        # Issue a fresh one, so changing a password does not also log you out of
        # the page you changed it on.
        refresh = RefreshToken.for_user(user)
        response = Response({"access": str(refresh.access_token)})
        _set_refresh_cookie(response, str(refresh))
        return response
