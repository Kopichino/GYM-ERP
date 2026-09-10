from rest_framework.decorators import action
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from core.permissions import IsAdmin

from .access import MESSAGES, Decision, request_access
from .authentication import DeviceKeyAuthentication, IsDevice
from .models import Device, DeviceEvent, EventOutcome, generate_key
from .serializers import (
    AccessRequestSerializer,
    DeviceEventSerializer,
    DeviceSerializer,
    PunchBatchSerializer,
)
from .services import record_punch, reprocess


class DeviceViewSet(ModelViewSet):
    """Admin registration and health for door terminals."""


    def get_queryset(self):
        # Built per request, not at import: the scoped manager needs a
        # tenant in scope and a class attribute is evaluated on load.
        return Device.objects.all()
    serializer_class = DeviceSerializer
    permission_classes = [IsAdmin]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw, hashed = generate_key()
        device = serializer.save(api_key_hash=hashed)
        # The only time the plaintext key exists. It is not recoverable later --
        # a lost key is rotated, not looked up.
        return Response({**self.get_serializer(device).data, "api_key": raw}, status=201)

    @action(detail=True, methods=["post"])
    def rotate_key(self, request, pk=None):
        device = self.get_object()
        raw, hashed = generate_key()
        device.api_key_hash = hashed
        device.save(update_fields=["api_key_hash"])
        return Response({"api_key": raw})


class DeviceEventListView(ListAPIView):
    """The raw punch log. `?outcome=unmatched` surfaces punches that found no
    member, which is the queue an admin works through."""

    serializer_class = DeviceEventSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        queryset = DeviceEvent.objects.select_related("device", "member")
        outcome = self.request.query_params.get("outcome")
        if outcome:
            queryset = queryset.filter(outcome=outcome)
        device = self.request.query_params.get("device")
        if device:
            queryset = queryset.filter(device_id=device)
        return queryset


class DeviceEventReprocessView(APIView):
    """Re-resolve a punch after its member's enrolment id has been corrected."""

    permission_classes = [IsAdmin]

    def post(self, request, pk, *args, **kwargs):
        event = DeviceEvent.objects.filter(pk=pk).first()
        if event is None:
            return Response({"detail": "No such event."}, status=404)
        return Response(DeviceEventSerializer(reprocess(event)).data)


class PunchIngestView(APIView):
    """Where terminals push punches. Authenticated by device key, not a JWT."""

    authentication_classes = [DeviceKeyAuthentication]
    permission_classes = [IsDevice]

    def post(self, request, *args, **kwargs):
        serializer = PunchBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        results = []
        for punch in serializer.validated_data["punches"]:
            event, created = record_punch(
                device=request.device,
                biometric_id=punch["biometric_id"],
                event_time=punch["event_time"],
                raw_payload=punch.get("raw", {}),
            )
            results.append(
                {
                    "biometric_id": punch["biometric_id"],
                    "event_time": punch["event_time"],
                    "outcome": event.outcome if event else EventOutcome.DUPLICATE,
                    "accepted": created,
                }
            )

        return Response({"received": len(results), "results": results})


class AccessRequestView(APIView):
    """What a turnstile or door lock calls before it opens.

    Answers in one round trip -- allow or not, why, and who -- because the
    member is standing at the gate while this runs. On an allow the visit is
    toggled through the normal attendance service, so a turnstile cannot open a
    second visit for someone who is already inside.
    """

    authentication_classes = [DeviceKeyAuthentication]
    permission_classes = [IsDevice]

    def post(self, request, *args, **kwargs):
        form = AccessRequestSerializer(data=request.data)
        form.is_valid(raise_exception=True)

        allow, reason, event = request_access(
            device=request.device,
            identifier=form.validated_data["identifier"],
            at=form.validated_data.get("event_time"),
            raw_payload=form.validated_data.get("raw", {}),
        )

        member = event.member if event else None
        return Response(
            {
                "allow": allow,
                "reason": reason,
                # Wording the gate can put on its own screen. Empty on an
                # allow: there is nothing to explain when the door opens.
                "message": "" if allow else MESSAGES.get(reason, "Refused entry."),
                "member": (member.get_full_name() or member.username) if member else None,
                "action": event.outcome if event else None,
            }
        )
