from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework import status as http
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from accounts.models import Role, User
from core.dates import read_date, read_window
from core.permissions import access, IsTenantMember, IsTrainerOrAdmin
from tenancy import context
from tenancy.models import Membership
from tenancy.people import people_here, people_here_or_404

from .models import Availability, PTSession, SessionStatus, Unavailable
from .serializers import (
    AvailabilitySerializer,
    PTSessionSerializer,
    SlotSerializer,
    UnavailableSerializer,
)
from .services import BookingError, book_session, cancel_session, open_slots


def _trainer_pk(raw):
    """The trainer id a request names, as a positive integer.

    Handed to the ORM as it came, "abc" or a blank raised a ValueError nobody
    caught -- a 500. A malformed id is a 400 naming `trainer`, the way
    `core.dates` answers a malformed date. Left out altogether it stays None,
    which matches nobody, so that is still the lookup's 404.
    """
    if raw is None:
        return None
    try:
        return serializers.IntegerField(min_value=1).run_validation(raw)
    except serializers.ValidationError as exc:
        raise serializers.ValidationError({"trainer": exc.detail}) from exc


class _OwnRowsMixin:
    """A trainer manages their own rows; an admin manages anyone's."""

    permission_classes = [IsTrainerOrAdmin]

    def _target_trainer(self):
        requested = self.request.data.get("trainer") or self.request.query_params.get("trainer")
        if not requested or str(requested) == str(self.request.user.id):
            return self.request.user
        if not access(self.request).is_admin:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You can only manage your own availability.")
        return people_here_or_404(_trainer_pk(requested), Role.TRAINER)


class AvailabilityViewSet(_OwnRowsMixin, ModelViewSet):
    """The weekly pattern a trainer offers."""

    serializer_class = AvailabilitySerializer

    def get_queryset(self):
        return Availability.objects.filter(trainer=self._target_trainer()).select_related(
            "trainer"
        )

    def perform_create(self, serializer):
        serializer.save(trainer=self._target_trainer())


class UnavailableViewSet(_OwnRowsMixin, ModelViewSet):
    """Days taken back out of the pattern."""

    serializer_class = UnavailableSerializer

    def get_queryset(self):
        return Unavailable.objects.filter(trainer=self._target_trainer())

    def perform_create(self, serializer):
        serializer.save(trainer=self._target_trainer())


class TrainerSlotsView(APIView):
    """What a trainer has free on a given day.

    Anyone signed in can read this -- it is what a member needs before they can
    book, and it says nothing except which hours are open.
    """

    # Standing at the gym in the URL, not just a signed-in account: without it a
    # person from another gym could read this gym's (empty) list for them and
    # file new rows under a gym they do not belong to.
    permission_classes = [IsTenantMember]

    def get(self, request):
        trainer = people_here_or_404(
            _trainer_pk(request.query_params.get("trainer")), Role.TRAINER
        )
        on = read_date(request.query_params, "date", timezone.localdate())
        slots = open_slots(trainer, on)
        return Response(
            {
                "trainer": trainer.id,
                "trainer_name": trainer.get_full_name() or trainer.username,
                "date": on,
                "results": SlotSerializer(slots, many=True).data,
            }
        )


class TrainerListView(APIView):
    """The trainers a member can book at this gym.

    Read off Membership rather than `User.role`: a trainer at another gym is not
    bookable here, and neither is someone whose trainer role here has lapsed.
    Returns a name and an id and nothing more -- all the booking form needs to
    put the right person on a session. It replaced reading instructor profiles,
    which were removed.
    """

    permission_classes = [IsTenantMember]

    def get(self, request):
        today = timezone.localdate()
        memberships = Membership.objects.filter(
            tenant=context.require(), role=Role.TRAINER, is_active=True
        ).select_related("user")
        trainers = sorted(
            {m.user for m in memberships if m.is_current(today)},
            key=lambda user: (user.get_full_name() or user.username).lower(),
        )
        return Response(
            {"results": [{"id": u.id, "name": u.get_full_name() or u.username} for u in trainers]}
        )


class PTSessionViewSet(ModelViewSet):
    """Booking, cancelling and closing off one-to-one sessions."""

    serializer_class = PTSessionSerializer
    permission_classes = [IsTenantMember]

    def get_queryset(self):
        user = self.request.user
        here = access(self.request)
        queryset = PTSession.objects.select_related("trainer", "member")
        if here.is_admin:
            pass
        elif here.is_trainer:
            # Their own diary, plus anything they have booked as a member.
            from django.db.models import Q

            queryset = queryset.filter(Q(trainer=user) | Q(member=user))
        else:
            queryset = queryset.filter(member=user)

        params = self.request.query_params
        # Parsed before they reach the ORM: handed over raw, a malformed date
        # raised a validation error nothing caught -- a 500.
        start, end = read_window(params)
        if start:
            queryset = queryset.filter(date__gte=start)
        if end:
            queryset = queryset.filter(date__lte=end)
        if params.get("upcoming"):
            queryset = queryset.filter(
                date__gte=timezone.localdate(), status=SessionStatus.BOOKED
            )
        return queryset

    def create(self, request, *args, **kwargs):
        form = self.get_serializer(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data

        # A member books for themselves; staff may book on someone's behalf.
        member = data["member"]
        here = access(request)
        staff = here.is_admin or here.is_trainer
        # `trainer` and `member` are plain ids over every account on the
        # platform, so both have to be people at this gym -- otherwise staff
        # could book somebody from another gym, or book them with another
        # gym's trainer.
        if not people_here(Role.TRAINER).filter(pk=data["trainer"].pk).exists():
            return Response(
                {"trainer": ["That trainer does not work at this gym."]},
                status=http.HTTP_400_BAD_REQUEST,
            )
        if not people_here().filter(pk=member.pk).exists():
            return Response(
                {"member": ["That person is not a member of this gym."]},
                status=http.HTTP_400_BAD_REQUEST,
            )
        # The price is the gym's to set. A member's own booking never takes
        # one from the browser.
        price = data.get("price", 0) if staff else 0
        if member != request.user and not staff:
            return Response(
                {"detail": "You can only book sessions for yourself."},
                status=http.HTTP_403_FORBIDDEN,
            )

        try:
            session = book_session(
                trainer=data["trainer"],
                member=member,
                on=data["date"],
                start_time=data["start_time"],
                end_time=data["end_time"],
                price=price,
                booked_by=request.user,
                notes=data.get("notes", ""),
            )
        except BookingError as exc:
            return Response({"detail": str(exc)}, status=http.HTTP_400_BAD_REQUEST)

        return Response(self.get_serializer(session).data, status=http.HTTP_201_CREATED)

    #: The one thing a booking may be edited in place for. Moving a session or
    #: changing who is in it goes through cancel and rebook, which re-runs the
    #: booking rules; payment and price go through `complete`, which is the
    #: trainer's call. A PATCH naming anything else would sidestep all of that
    #: -- a member marking their own session paid, repricing it, or moving it
    #: into an hour that is already taken.
    EDITABLE_FIELDS = {"notes"}

    def update(self, request, *args, **kwargs):
        session = self.get_object()
        if not self._may_change(session):
            return Response({"detail": "Not yours to change."}, status=http.HTTP_403_FORBIDDEN)
        locked = sorted(set(request.data) - self.EDITABLE_FIELDS)
        if locked:
            return Response(
                {
                    field: ["This can't be edited here. Cancel and rebook, or close the session off."]
                    for field in locked
                },
                status=http.HTTP_400_BAD_REQUEST,
            )
        return super().update(request, *args, **kwargs)

    def _may_change(self, session):
        user = self.request.user
        return (
            access(self.request).is_admin
            or session.trainer_id == user.id
            or session.member_id == user.id
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        session = self.get_object()
        if not self._may_change(session):
            return Response({"detail": "Not yours to cancel."}, status=http.HTTP_403_FORBIDDEN)
        try:
            cancel_session(session)
        except BookingError as exc:
            return Response({"detail": str(exc)}, status=http.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(session).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        """Marking a session done is the trainer's call, not the member's."""
        session = self.get_object()
        user = request.user
        if not (access(request).is_admin or session.trainer_id == user.id):
            return Response(
                {"detail": "Only the trainer can close off a session."},
                status=http.HTTP_403_FORBIDDEN,
            )
        session.status = (
            SessionStatus.NO_SHOW
            if request.data.get("no_show")
            else SessionStatus.COMPLETED
        )
        if "is_paid" in request.data:
            session.is_paid = bool(request.data["is_paid"])
        session.save(update_fields=["status", "is_paid"])
        return Response(self.get_serializer(session).data)
