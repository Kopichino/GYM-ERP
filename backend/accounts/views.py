import openpyxl
from django.conf import settings
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenObtainSerializer
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from core.permissions import IsAdmin, IsTrainer
from core.spreadsheets import neutralise_formulas

from . import mfa
from .auth_sessions import (
    SECRET_CLAIM,
    access_for,
    ceiling,
    end_session,
    find_session,
    kind_for_login,
    note_token,
    open_session,
    seconds_left,
    session_from_cookie,
    start_session,
)
from .models import AuthSession, Role, User
from .session_policy import NORMAL
from .serializers import (
    AdminMemberSerializer,
    AdminUserSerializer,
    SignupSerializer,
    TrainerMemberSerializer,
    UserSerializer,
)
from .throttling import LoginAttemptThrottle, RefreshAnonymousThrottle, RefreshSessionThrottle
from tenancy.people import holds_standing_elsewhere
from core.security_log import security_event
from .tokens import revoke_refresh_tokens

def cookie_kwargs():
    """How the refresh cookie is written.

    Read per call rather than once at import: `SameSite` is deployment
    configuration (see settings), and a value frozen at import time cannot be
    exercised or overridden by anything that changes it afterwards.
    """
    return dict(
        httponly=True,
        secure=settings.JWT_REFRESH_COOKIE_SECURE,
        samesite=settings.JWT_REFRESH_COOKIE_SAMESITE,
        path="/api/auth/",
    )


def _set_refresh_cookie(response, refresh_token: str, max_age=None):
    """Write the refresh cookie.

    `max_age` is how long the *session* has left, not a fixed lifetime: it is a
    persistent cookie that outlives the browser, but never the session it carries.
    """
    if max_age is None:
        max_age = int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds())
    response.set_cookie(
        settings.JWT_REFRESH_COOKIE_NAME,
        str(refresh_token),
        max_age=max_age,
        **cookie_kwargs(),
    )


def session_response(user, extra=None, *, kind=NORMAL, request=None):
    """Sign `user` in: the access token in the body, the refresh token as the
    httpOnly cookie. The one place a session is opened, so every way in -- a
    code, a recovery code, finishing setup -- hands out the same thing.

    `kind` is the person's choice at the password step ("remember me", "trust this
    device"), carried through two-step sign-in in the signed pending token. It sets
    how long the session lasts and nothing else: it is never a reason to skip a
    password or a code.
    """
    session, refresh = open_session(user, kind, request)
    response = Response({"access": str(access_for(refresh)), **(extra or {})})
    _set_refresh_cookie(response, str(refresh), max_age=seconds_left(session))
    if kind != NORMAL:
        security_event("persistent_session_opened", request, user=user.pk, reason=kind)
    return response


class SignupView(generics.CreateAPIView):
    serializer_class = SignupSerializer
    permission_classes = [AllowAny]
    throttle_scope = "login"


class PasswordStepSerializer(TokenObtainSerializer):
    """Checks the username and password, and issues nothing.

    SimpleJWT's pair serializer mints a refresh token while validating. Here
    that would be a live session handed out before the second step, plus an
    outstanding-token row for every sign-in left half finished.
    """

    token_class = RefreshToken


class LoginView(TokenObtainPairView):
    """Step one of signing in: the password.

    A right password opens a session straight away only where two-step sign-in
    is not required and the account has not set it up. Otherwise the reply is a
    short-lived pending token, which `mfa_views` exchanges for a code -- or, for
    an account that has never set it up, for setting it up there and then.

    A session, when there is one, is the access token in the body and the
    refresh token as an httpOnly cookie rather than in the body (XSS mitigation).
    """

    permission_classes = [AllowAny]
    serializer_class = PasswordStepSerializer
    throttle_scope = "login"
    # ScopedRateThrottle keeps the per-IP "login" rate; LoginAttemptThrottle
    # adds a per-username one, so an attacker spreading attempts across
    # addresses is still limited on the account they are aiming at.
    throttle_classes = [ScopedRateThrottle, LoginAttemptThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc
        except AuthenticationFailed:
            security_event("login_failed", request, warning=True, username=request.data.get("username"))
            raise
        user = serializer.user
        # Asked for only after the password was right, and used only to decide how
        # long the session lasts. Kept in the pending token across the second step.
        kind = kind_for_login(request.data.get("remember_me"), request.data.get("trust_device"))

        # An account with an authenticator always uses it, whatever the setting:
        # switching the requirement off must not quietly weaken the accounts of
        # people who set it up.
        if mfa.has_confirmed_device(user):
            return Response({"mfa_required": True, "mfa_token": mfa.pending_token(user, kind)})
        if mfa.required_for(user):
            return Response({"mfa_setup_required": True, "mfa_token": mfa.pending_token(user, kind)})
        return session_response(user, kind=kind, request=request)


#: How long after rotation a second use of the old refresh token still counts as
#: a race rather than a theft. Two tabs refreshing together, or a request retried
#: on a flaky connection, both present the same token within a second or two.
REFRESH_REUSE_GRACE_SECONDS = 30


def _end_sessions_if_replayed(raw_token):
    """End every session of an account whose rotated refresh token came back.

    Rotation means each refresh token is used once. The old one turning up again
    long after it was rotated means two parties hold the session -- the owner
    and whoever copied the cookie -- and nothing here can tell which is which.
    So both lose it: every refresh and access token of the account ends, and the
    owner signs in again, which the other party cannot do.
    """
    import logging
    from datetime import timedelta

    from django.utils import timezone
    from rest_framework_simplejwt.state import token_backend
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

    from .revocation import RevocationUnavailable

    try:
        # Signature and expiry still have to be genuine: only a real token of
        # ours, refused solely for being used up, is evidence of a replay.
        payload = token_backend.decode(raw_token, verify=True)
    except Exception:  # noqa: BLE001 -- anything unreadable is simply invalid
        return
    if payload.get(jwt_settings.TOKEN_TYPE_CLAIM) != "refresh":
        return
    blacklisted_at = (
        BlacklistedToken.objects.filter(token__jti=payload.get(jwt_settings.JTI_CLAIM))
        .values_list("blacklisted_at", flat=True)
        .first()
    )
    if blacklisted_at is None:
        return
    if timezone.now() - blacklisted_at < timedelta(seconds=REFRESH_REUSE_GRACE_SECONDS):
        return
    user = User.objects.filter(pk=payload.get(jwt_settings.USER_ID_CLAIM)).first()
    if user is None:
        return
    # Recorded before the revocation runs, and the revocation's own failure
    # caught: a replay is the one event here that must reach the log whatever
    # else is broken, and the caller is inside the branch that answers a reused
    # token with a 401. Letting a cache outage turn that into a 503 would hand
    # whoever is replaying the token a different answer than everyone else gets
    # -- and the durable half, blacklisting every refresh token, has already
    # happened by the time this can raise.
    security_event("refresh_token_replayed", warning=True, user=user.pk, reason="ended_every_session")
    try:
        revoke_refresh_tokens(user)
    except RevocationUnavailable:
        logging.getLogger(__name__).warning(
            "replay defence: refresh tokens blacklisted, access tokens left to expire"
        )


def _record_outstanding(refresh, user, raw):
    """Track a freshly rotated refresh token so it can be revoked later."""
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
    from rest_framework_simplejwt.utils import datetime_from_epoch

    OutstandingToken.objects.get_or_create(
        jti=refresh[jwt_settings.JTI_CLAIM],
        defaults={
            "user": user,
            "token": raw,
            "created_at": refresh.current_time,
            "expires_at": datetime_from_epoch(refresh["exp"]),
        },
    )


def _session_gone(reason):
    """The refresh cookie names a session that is over. Not a theft: nothing here
    touches anyone else's sessions, and the browser is told to forget the cookie."""
    detail = {
        "session_ended": "This session has ended. Sign in again.",
        "session_expired": "This session has expired. Sign in again.",
    }[reason]
    response = Response({"detail": detail, "reason": reason}, status=status.HTTP_401_UNAUTHORIZED)
    response.delete_cookie(settings.JWT_REFRESH_COOKIE_NAME, path="/api/auth/")
    return response


class RefreshView(APIView):
    """Reads the refresh token from the httpOnly cookie (not the body),
    rotates it, and returns a fresh access token.

    A session is kept alive only for an account that meets the sign-in rules as
    they stand now, not as they stood when it was opened. Without that, turning
    two-step sign-in on would leave every existing session running without it
    until it ended.

    Rotating never extends a session. Each token is good until the session's
    ceiling, fixed at login, so a session that is used every day still ends on
    the day it was always going to -- and is refused here, by the server, even if
    the token in the cookie has time left on it.
    """

    permission_classes = [AllowAny]
    # Not the shared anonymous bucket: a genuine session is counted per account,
    # anything else per address. See accounts.throttling.
    throttle_classes = [RefreshSessionThrottle, RefreshAnonymousThrottle]

    def post(self, request, *args, **kwargs):
        raw_token = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
        if not raw_token:
            return Response({"detail": "No refresh token cookie."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            refresh = RefreshToken(raw_token)
        except TokenError:
            _end_sessions_if_replayed(raw_token)
            return Response({"detail": "Invalid or expired refresh token."}, status=status.HTTP_401_UNAUTHORIZED)

        user = User.objects.filter(
            pk=refresh.payload.get(jwt_settings.USER_ID_CLAIM), is_active=True
        ).first()
        if user is None:
            return Response({"detail": "Invalid or expired refresh token."}, status=status.HTTP_401_UNAUTHORIZED)
        if mfa.required_for(user) and not mfa.has_confirmed_device(user):
            response = Response(
                {"detail": "Sign in again to set up two-step sign-in.", "reason": "mfa_setup_required"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            response.delete_cookie(settings.JWT_REFRESH_COOKIE_NAME, path="/api/auth/")
            return response

        # Is the session behind this token still allowed to continue? Checked in
        # the database, so a revocation holds whatever the cache is doing.
        secret = refresh.payload.get(SECRET_CLAIM)
        session = find_session(secret, user)
        if secret:
            if session is None or session.revoked_at is not None:
                return _session_gone("session_ended")
            if session.expires_at <= timezone.now():
                return _session_gone("session_expired")

        try:
            with transaction.atomic():
                if not secret:
                    # A token from before sessions were recorded, still in somebody's
                    # browser. It is taken in as a normal session counted from now,
                    # rather than refused, so shipping this signs nobody out.
                    session, secret = start_session(user, NORMAL, request)
                    refresh[SECRET_CLAIM] = secret
                # Taken before the rotation below, as SimpleJWT's own serializer does.
                access = access_for(refresh)
                # Mirror SimpleJWT's own TokenRefreshSerializer rotation order:
                # blacklist the old jti first, then mutate this token into a new
                # one (new jti/iat) so ROTATE_REFRESH_TOKENS is honored. The expiry
                # is the session's ceiling and does not move.
                try:
                    refresh.blacklist()
                except AttributeError:
                    pass
                refresh.set_jti()
                refresh.payload["exp"] = ceiling(session)
                refresh.set_iat()
                new_refresh = str(refresh)
                # Record the rotated token as outstanding. Without the row, revoking
                # "every" refresh token of the account -- a password change, a
                # reset, a detected replay -- only reached the token issued at
                # sign-in, and the one actually in the browser lived on.
                _record_outstanding(refresh, user, new_refresh)
                note_token(session, refresh)
        except TokenError:
            return Response({"detail": "Invalid or expired refresh token."}, status=status.HTTP_401_UNAUTHORIZED)

        response = Response({"access": str(access)})
        _set_refresh_cookie(response, new_refresh, max_age=seconds_left(session))
        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        raw_token = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
        if raw_token:
            # The session first, then the token: ending the session is what stops
            # this device being signed back in, and it is found through the
            # cookie's secret, so a cookie one rotation behind still reaches it.
            session = session_from_cookie(request)
            if session is not None:
                end_session(session)
            try:
                RefreshToken(raw_token).blacklist()
            except TokenError:
                pass
        # The access token that asked to log out ends too -- not in fifteen
        # minutes. Only this one: another device stays signed in.
        if request.auth is not None:
            from .revocation import revoke_access_token

            revoke_access_token(request.auth)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(settings.JWT_REFRESH_COOKIE_NAME, path="/api/auth/")
        return response


def _describe_session(session, current_pk):
    """What a person is shown about one of their sessions. No secret, no token."""
    return {
        "id": session.pk,
        "kind": session.kind,
        "label": session.label or "Unknown device",
        "created_at": session.created_at,
        "last_seen_at": session.last_seen_at,
        "expires_at": session.expires_at,
        "current": session.pk == current_pk,
    }


def _live_sessions(user):
    return AuthSession.objects.filter(
        user=user, revoked_at__isnull=True, expires_at__gt=timezone.now()
    )


class SessionListView(APIView):
    """Your own signed-in devices, newest use first.

    About the person, so it is not under a gym. Another account's sessions are
    not reachable here at all: the query starts from `request.user`.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        current = session_from_cookie(request)
        current_pk = current.pk if current is not None else None
        rows = _live_sessions(request.user).order_by("-last_seen_at")
        return Response([_describe_session(row, current_pk) for row in rows])


class SessionDetailView(APIView):
    """Sign one of your own devices out.

    The device's refresh token is deliberately left alone rather than blacklisted:
    a blacklisted token turning up again is read as a theft and ends *every*
    session, which is the wrong reward for revoking an old laptop. The session row
    is what refresh checks, and it holds whatever the cache is doing. Its access
    token, at most fifteen minutes old, simply runs out.
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        session = _live_sessions(request.user).filter(pk=pk).first()
        if session is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        current = session_from_cookie(request)
        end_session(session)
        security_event("session_revoked", request, user=request.user.pk, reason=session.kind)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        if current is not None and current.pk == session.pk:
            response.delete_cookie(settings.JWT_REFRESH_COOKIE_NAME, path="/api/auth/")
        return response


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


def _member_queryset():
    """Members *of this gym*.

    `User` is not tenant-scoped -- one account can belong to several gyms -- so
    filtering on `role` alone listed every member on the platform, and the admin
    screen and Excel export showed one gym's owner every other gym's members. A
    Membership at the tenant in scope is what makes someone a member here.

    One `filter()` call on purpose. Split across two, each condition could be met
    by a *different* membership, so a trainer here who is a member at some other
    gym would match.
    """
    from tenancy import context

    return (
        User.objects.filter(
            memberships__tenant=context.require(),
            memberships__role=Role.MEMBER,
            memberships__is_active=True,
        )
        .distinct()
        .select_related("profile", "mfa_device")
        .prefetch_related("check_ins")
        .order_by("username")
    )


class MemberListView(generics.ListAPIView):
    """Admin dashboard's member list -- same queryset/serializer the Excel
    export below uses, so the download always matches what's on screen."""

    serializer_class = AdminMemberSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        # Built per request, not at import: the scoped manager needs a
        # tenant in scope and a class attribute is evaluated on load.
        return _member_queryset()


class MyMembersListView(generics.ListAPIView):
    """Trainer portal's roster: only the members assigned to the signed-in
    trainer, never the whole gym."""

    serializer_class = TrainerMemberSerializer
    permission_classes = [IsTrainer]

    def get_queryset(self):
        return _member_queryset().filter(profile__trainer=self.request.user)


class MyMemberDetailView(generics.RetrieveAPIView):
    """One of the signed-in trainer's members, for the member page.

    The same rows as the roster, so a member not assigned to this trainer -- or
    not at this gym, or whose standing here has ended, or who does not exist --
    is one 404 that says nothing about which. The page asks this first, and only
    offers the workout logger for a member it gets back.
    """

    serializer_class = TrainerMemberSerializer
    permission_classes = [IsTrainer]

    def get_queryset(self):
        return _member_queryset().filter(profile__trainer=self.request.user)


class MemberExportView(APIView):
    """Streams the full member list as an .xlsx file for the admin
    dashboard's "download as Excel" button."""

    permission_classes = [IsAdmin]

    def get(self, request, *args, **kwargs):
        members = AdminMemberSerializer(_member_queryset(), many=True).data

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Members"
        headers = [
            "Username",
            "Email",
            "First name",
            "Last name",
            "Phone",
            "Join date",
            "Membership status",
            "Last check-in",
        ]
        sheet.append(headers)
        for member in members:
            sheet.append(
                [
                    member["username"],
                    member["email"],
                    member["first_name"],
                    member["last_name"],
                    member["phone"],
                    member["join_date"],
                    member["membership_status"],
                    member["last_check_in"],
                ]
            )

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = "attachment; filename=gym_members.xlsx"
        neutralise_formulas(sheet)
        workbook.save(response)
        return response


#: Refusal for an account that also belongs to another gym. Said the same way
#: everywhere, because the reason matters to the admin reading it.
SHARED_ACCOUNT = (
    "That account also belongs to another gym, so its sign-in details can only "
    "be changed by an admin there."
)


class AdminSetPasswordView(APIView):
    """An admin gives a member of this gym a password.

    For accounts that have none. Imported members are created without a usable
    password, and a phone-only import has no real email to receive a reset link
    at -- so without this, that member could never log in.

    Found through `_member_queryset`, so it reaches members *here* only: an admin
    cannot set the password of an account at another gym.
    """

    permission_classes = [IsAdmin]

    def post(self, request, pk):
        user = get_object_or_404(_member_queryset(), pk=pk)
        if holds_standing_elsewhere(user):
            security_event("shared_account_change_refused", request, warning=True, user=request.user.pk, target=user.pk, reason="set_password")
            return Response({"detail": SHARED_ACCOUNT}, status=status.HTTP_403_FORBIDDEN)
        password = str(request.data.get("password") or "")
        try:
            password_validation.validate_password(password, user)
        except DjangoValidationError as exc:
            return Response({"password": list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(password)
        user.save(update_fields=["password"])
        # A new password ends the sessions the old one opened -- which matters
        # when the admin is resetting an account they think someone else has.
        revoke_refresh_tokens(user)
        security_event("password_set_by_admin", request, user=request.user.pk, target=user.pk)
        return Response({"detail": "Password set."})


class AdminUserViewSet(ModelViewSet):
    """Admin-only account management -- create trainer/admin accounts, change
    roles, and assign a trainer to a member."""

    serializer_class = AdminUserSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        # Only accounts that belong to this gym. `User` spans every gym on the
        # platform, so without this an admin here could list, edit, delete or
        # set the password of an account at a gym they have no standing in. One
        # `filter()`, so tenant and role are matched on the same membership.
        from tenancy import context

        conditions = {"memberships__tenant": context.require(), "memberships__is_active": True}
        role = self.request.query_params.get("role")
        if role:
            conditions["memberships__role"] = role
        return (
            User.objects.filter(**conditions)
            .distinct()
            .select_related("profile", "mfa_device")
            .order_by("username")
        )

    #: Changing any of these re-keys the account itself rather than its standing
    #: here, so they are refused on an account shared with another gym.
    SIGN_IN_FIELDS = {"password", "email", "username"}

    def update(self, request, *args, **kwargs):
        if set(request.data) & self.SIGN_IN_FIELDS and holds_standing_elsewhere(
            self.get_object()
        ):
            security_event("shared_account_change_refused", request, warning=True, user=request.user.pk, target=kwargs.get("pk"), reason="sign_in_details")
            return Response({"detail": SHARED_ACCOUNT}, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)

    def perform_destroy(self, instance):
        """Removing somebody ends their standing here; it does not delete them.

        The account may be a person at another gym, and deleting the row would
        take this gym's own history with it -- payments, invoices and check-ins
        all cascade off `User`. Ending the membership is what "remove from this
        gym" actually means.
        """
        from tenancy import context
        from tenancy.models import Membership

        Membership.objects.filter(user=instance, tenant=context.require()).update(
            is_active=False
        )

    @action(detail=True, methods=["post"], url_path="reset-mfa")
    def reset_mfa(self, request, pk=None):
        """Clear someone's authenticator, so they set up a new one at next sign-in.

        For a person who has lost their phone *and* their recovery codes, who is
        otherwise locked out for good. Found through `get_queryset`, so only an
        account at this gym.
        """
        from .mfa_views import reset_mfa

        user = self.get_object()
        if holds_standing_elsewhere(user):
            security_event("shared_account_change_refused", request, warning=True, user=request.user.pk, target=user.pk, reason="reset_mfa")
            return Response({"detail": SHARED_ACCOUNT}, status=status.HTTP_403_FORBIDDEN)
        reset_mfa(user)
        security_event("mfa_reset_by_admin", request, user=request.user.pk, target=user.pk)
        return Response(
            {"detail": "Two-step sign-in reset. They will set it up again when they next sign in."}
        )
