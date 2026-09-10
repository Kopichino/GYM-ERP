from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("admin/users", views.AdminUserViewSet, basename="admin-user")

urlpatterns = [
    path("signup/", views.SignupView.as_view(), name="signup"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("refresh/", views.RefreshView.as_view(), name="refresh"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.MeView.as_view(), name="me"),
    path("admin/members/", views.MemberListView.as_view(), name="member-list"),
    path("admin/members/export/", views.MemberExportView.as_view(), name="member-export"),
    path("trainer/members/", views.MyMembersListView.as_view(), name="trainer-member-list"),
    path("", include(router.urls)),
]
