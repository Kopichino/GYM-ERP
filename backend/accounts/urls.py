from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views
from .passwords import PasswordChangeView, PasswordForgotView, PasswordResetView

router = DefaultRouter()
router.register("admin/users", views.AdminUserViewSet, basename="admin-user")

urlpatterns = [
    path("signup/", views.SignupView.as_view(), name="signup"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("refresh/", views.RefreshView.as_view(), name="refresh"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.MeView.as_view(), name="me"),
    # About the person rather than a gym, so no tenant prefix -- see passwords.py.
    path("password/forgot/", PasswordForgotView.as_view(), name="password-forgot"),
    path("password/reset/", PasswordResetView.as_view(), name="password-reset"),
    path("password/change/", PasswordChangeView.as_view(), name="password-change"),
    path("admin/members/", views.MemberListView.as_view(), name="member-list"),
    path("admin/members/export/", views.MemberExportView.as_view(), name="member-export"),
    path(
        "admin/members/<int:pk>/set-password/",
        views.AdminSetPasswordView.as_view(),
        name="member-set-password",
    ),
    path("trainer/members/", views.MyMembersListView.as_view(), name="trainer-member-list"),
    path("", include(router.urls)),
]
