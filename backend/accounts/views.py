import openpyxl
from django.conf import settings
from django.http import HttpResponse
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import User
from .serializers import AdminMemberSerializer, SignupSerializer, UserSerializer

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
    return (
        User.objects.filter(is_staff=False)
        .select_related("profile")
        .prefetch_related("check_ins")
        .order_by("username")
    )


class MemberListView(generics.ListAPIView):
    """Admin dashboard's member list -- same queryset/serializer the Excel
    export below uses, so the download always matches what's on screen."""

    serializer_class = AdminMemberSerializer
    permission_classes = [IsAdminUser]
    queryset = _member_queryset()


class MemberExportView(APIView):
    """Streams the full member list as an .xlsx file for the admin
    dashboard's "download as Excel" button."""

    permission_classes = [IsAdminUser]

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
