import openpyxl
from django.conf import settings
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from core.permissions import IsAdmin, IsTrainer

from .models import Role, User
from .serializers import (
    AdminMemberSerializer,
    AdminUserSerializer,
    SignupSerializer,
    TrainerMemberSerializer,
    UserSerializer,
)
from .throttling import LoginAttemptThrottle
from .tokens import revoke_refresh_tokens

COOKIE_KWARGS = dict(
    httponly=True,
    secure=settings.JWT_REFRESH_COOKIE_SECURE,
    samesite=settings.JWT_REFRESH_COOKIE_SAMESITE,
    path="/api/auth/",
)


def _set_refresh_cookie(response, refresh_token: str):
    response.set_cookie(
        settings.JWT_REFRESH_COOKIE_NAME,
        str(refresh_token),
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        **COOKIE_KWARGS,
    )


class SignupView(generics.CreateAPIView):
    serializer_class = SignupSerializer
    permission_classes = [AllowAny]
    throttle_scope = "login"


class LoginView(TokenObtainPairView):
    """Returns the access token in the JSON body; sets the refresh token as
    an httpOnly cookie instead of returning it in the body (XSS mitigation)."""

    permission_classes = [AllowAny]
    throttle_scope = "login"
    # ScopedRateThrottle keeps the per-IP "login" rate; LoginAttemptThrottle
    # adds a per-username one, so an attacker spreading attempts across
    # addresses is still limited on the account they are aiming at.
    throttle_classes = [ScopedRateThrottle, LoginAttemptThrottle]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        refresh = response.data.pop("refresh", None)
        if refresh:
            _set_refresh_cookie(response, refresh)
        return response


class RefreshView(APIView):
    """Reads the refresh token from the httpOnly cookie (not the body),
    rotates it, and returns a fresh access token."""

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        raw_token = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
        if not raw_token:
            return Response({"detail": "No refresh token cookie."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            refresh = RefreshToken(raw_token)
            access = refresh.access_token
            # Mirror SimpleJWT's own TokenRefreshSerializer rotation order:
            # blacklist the old jti first, then mutate this token into a new
            # one (new jti/exp/iat) so ROTATE_REFRESH_TOKENS is honored.
            try:
                refresh.blacklist()
            except AttributeError:
                pass
            refresh.set_jti()
            refresh.set_exp()
            refresh.set_iat()
            new_refresh = str(refresh)
        except TokenError:
            return Response({"detail": "Invalid or expired refresh token."}, status=status.HTTP_401_UNAUTHORIZED)

        response = Response({"access": str(access)})
        _set_refresh_cookie(response, new_refresh)
        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        raw_token = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
        if raw_token:
            try:
                RefreshToken(raw_token).blacklist()
            except TokenError:
                pass
        response = Response(status=status.HTTP_204_NO_CONTENT)
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
        .select_related("profile")
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
        workbook.save(response)
        return response


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
            .select_related("profile")
            .order_by("username")
        )
