from django.db.models import Prefetch
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListAPIView
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from .models import BookingStatus, ClassBooking, ClassSession
from .serializers import ClassBookingSerializer, ClassSessionSerializer
from .services import BookingError, book, cancel, mark_attended
from core.permissions import access, IsTenantMember


def _id_list(data, key):
    """The ids under `key`, however the body was encoded.

    A JSON body gives a real list. A form-encoded one gives a QueryDict, whose
    `.get()` returns only the last value -- as a string. Handing that to an
    `__in` lookup iterates its characters, so "42" silently becomes ["4", "2"]
    and matches nobody: the endpoint answers 200 with nothing marked. Single
    digit ids happened to survive that, which is why it went unnoticed.
    """
    if hasattr(data, "getlist"):
        values = data.getlist(key)
    else:
        values = data.get(key) or []
        if isinstance(values, (str, int)):
            values = [values]
    return [v for v in values if str(v).strip()]


class CanManageClass(BasePermission):
    """Anyone who belongs to this gym may read its schedule. Admins may edit
    any class; a trainer may edit only the classes they run.

    Reading once asked only whether the caller was signed in, which let a
    member of any gym on the platform read this one's timetable."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(
                request.user
                and request.user.is_authenticated
                and access(request).belongs
            )
        return bool(
            request.user
            and request.user.is_authenticated
            and (access(request).is_admin or access(request).is_trainer)
        )

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS or access(request).is_admin:
            return True
        return obj.trainer_id == request.user.id


def _class_id(pk):
    """The class id from the URL, or None when it cannot be one.

    The booking service looks the class up with a row lock, and handed "abc" that
    raised a ValueError nobody caught -- a 500 for a mistyped link.
    """
    try:
        return int(pk)
    except (TypeError, ValueError):
        return None


class ClassSessionViewSet(ModelViewSet):
    serializer_class = ClassSessionSerializer
    permission_classes = [CanManageClass]

    def _can_see_roster(self, session):
        user = self.request.user
        if access(self.request).is_admin:
            return True
        return session.trainer_id == user.id

    @action(detail=True, methods=["post"], permission_classes=[IsTenantMember])
    def book(self, request, pk=None):
        """Take a seat on this class, or join the waitlist if it's full."""
        session_id = _class_id(pk)
        if session_id is None:
            return Response({"detail": "No such class."}, status=404)
        try:
            booking = book(session_id, request.user)
        except ClassSession.DoesNotExist:
            return Response({"detail": "No such class."}, status=404)
        except BookingError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(ClassBookingSerializer(booking).data, status=201)

    @action(detail=True, methods=["post"], permission_classes=[IsTenantMember])
    def cancel(self, request, pk=None):
        session_id = _class_id(pk)
        if session_id is None:
            return Response({"detail": "No such class."}, status=404)
        try:
            booking, promoted = cancel(session_id, request.user)
        except ClassSession.DoesNotExist:
            return Response({"detail": "No such class."}, status=404)
        except BookingError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(
            {
                "booking": ClassBookingSerializer(booking).data,
                "promoted_from_waitlist": (
                    ClassBookingSerializer(promoted).data if promoted else None
                ),
            }
        )

    @action(detail=True, methods=["get"], permission_classes=[IsTenantMember])
    def roster(self, request, pk=None):
        """Who is coming. Visible to the class's own trainer and to admins."""
        session = self.get_object()
        if not self._can_see_roster(session):
            raise PermissionDenied("Not one of your classes.")
        bookings = session.bookings.exclude(status=BookingStatus.CANCELLED).select_related("member")
        return Response(ClassBookingSerializer(bookings, many=True).data)

    @action(detail=True, methods=["post"], permission_classes=[IsTenantMember])
    def attendance(self, request, pk=None):
        """Mark off who actually turned up."""
        session = self.get_object()
        if not self._can_see_roster(session):
            raise PermissionDenied("Not one of your classes.")
        updated = mark_attended(session.pk, _id_list(request.data, "member_ids"))
        return Response({"marked_attended": updated})

    def get_queryset(self):
        # Built here rather than from a class-level `queryset`: the scoped
        # manager needs a tenant in scope, and a class attribute is evaluated
        # at import when there is none.
        queryset = ClassSession.objects.all().order_by("date", "start_time")
        # The trainer portal asks for `?mine=1` to get just its own classes.
        if self.request.query_params.get("mine") and access(self.request).is_trainer:
            return queryset.filter(trainer=self.request.user)
        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        if access(self.request).is_trainer:
            # A trainer can only put their own name on a class.
            serializer.save(trainer=user)
            return
        serializer.save()


class MyBookingsView(ListAPIView):
    """A member's own upcoming and past bookings."""

    serializer_class = ClassBookingSerializer
    permission_classes = [IsTenantMember]

    def get_queryset(self):
        return (
            ClassBooking.objects.filter(member=self.request.user)
            .exclude(status=BookingStatus.CANCELLED)
            .select_related("session", "session__trainer", "member")
            .order_by("session__date", "session__start_time")
        )
