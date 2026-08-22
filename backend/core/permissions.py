from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsAdminOrReadOnly(BasePermission):
    """Anyone authenticated can read; only staff (admin/instructor-managed
    content) can create/update/delete. Used for announcements, instructors,
    schedule, and gallery moderation."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return bool(request.user and request.user.is_staff)


class IsOwnerOrAdmin(BasePermission):
    """Members can only see/edit rows that belong to them (check-ins,
    workout logs); staff can see/edit everyone's."""

    owner_field = "user"

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        owner = getattr(obj, self.owner_field, None)
        return owner == request.user
