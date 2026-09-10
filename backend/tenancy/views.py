from rest_framework import status as http
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

import logging

from django.utils import timezone

from core.permissions import IsAdmin
from crm.models import Enquiry, EnquirySource

from . import context
from .leads import (
    IsLeadKey,
    LeadKeyAuthentication,
    LeadRateThrottle,
    looks_like_spam,
    record_failure,
    record_use,
)

from . import certificates

logger = logging.getLogger(__name__)
from .domains import VerificationError, verify
from .hosts import forget_hostnames
from .models import (
    Domain,
    LeadApiKey,
    LeadFailure,
    SendingDomain,
    generate_lead_key,
)
from .serializers import (
    DomainSerializer,
    LeadApiKeySerializer,
    SendingDomainSerializer,
)


class DomainViewSet(ModelViewSet):
    """A gym's own domains.

    Admin-only, and scoped: the manager confines this to the calling gym, so an
    admin cannot list, verify or delete a domain belonging to anyone else. That
    matters more here than on most endpoints -- a domain is the thing that
    decides which gym a request is served as.
    """

    serializer_class = DomainSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return Domain.objects.all()

    def perform_destroy(self, instance):
        instance.delete()
        # The allow-list is cached, and a removed domain must stop being served
        # immediately rather than up to a minute later.
        forget_hostnames()

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        """Check the TXT record and, if it matches, make the domain live."""
        domain = self.get_object()
        try:
            verify(domain)
        except VerificationError as exc:
            # 400 with the reason, not 500: "the record is not there yet" is an
            # ordinary answer during setup, not a fault.
            return Response(
                {"detail": str(exc), "dns_record": self.get_serializer(domain).data["dns_record"]},
                status=http.HTTP_400_BAD_REQUEST,
            )

        # Newly verified: it can serve traffic now, so the host cache has to
        # forget its old answer, and the host can be asked for a certificate.
        forget_hostnames()
        try:
            certificates.request_certificate(domain)
        except Exception:  # noqa: BLE001
            # A provider that is down must not undo a verification that
            # succeeded -- the domain is proved either way, and the certificate
            # can be requested again.
            pass

        return Response(self.get_serializer(domain).data)

    @action(detail=True, methods=["post"], url_path="make-primary")
    def make_primary(self, request, pk=None):
        """The address this gym advertises, used when building links in email."""
        domain = self.get_object()
        if not domain.is_verified:
            return Response(
                {"detail": "Verify the domain before making it primary."},
                status=http.HTTP_400_BAD_REQUEST,
            )
        # One primary per tenant is a database constraint, so the old one is
        # stood down first rather than relying on the write order.
        Domain.objects.filter(is_primary=True).exclude(pk=domain.pk).update(
            is_primary=False
        )
        domain.is_primary = True
        domain.save(update_fields=["is_primary"])
        return Response(self.get_serializer(domain).data)


class SendingDomainViewSet(ModelViewSet):
    """The address a gym's member email goes out from.

    One per gym, so this is a small ViewSet over a single row rather than a
    list. Admin-only and scoped: which domain a gym may send as decides what
    lands in a member's inbox wearing their name.
    """

    serializer_class = SendingDomainSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return SendingDomain.objects.all()

    def perform_create(self, serializer):
        identity = serializer.save()
        # Registering with the provider is what produces the DKIM record, so it
        # happens immediately -- an owner should land on the setup screen with
        # every row already filled in, not have to press something else first.
        from .email_identity import SendingSetupError
        from .email_provider import provider

        try:
            provider().register(identity)
        except SendingSetupError as exc:
            # Kept, not discarded. The domain and From address are still valid
            # choices; only the DKIM record is missing, and the screen says so.
            identity.last_error = str(exc)[:300]
            identity.save(update_fields=["last_error"])

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        """Re-check SPF and DKIM. Reports each separately, not one verdict."""
        from .email_identity import verify as run_verify

        identity = self.get_object()
        run_verify(identity)
        return Response(self.get_serializer(identity).data)

    @action(detail=True, methods=["post"], url_path="request-records")
    def request_records(self, request, pk=None):
        """Ask the provider for the DKIM record again.

        Its own action because the first attempt happens at creation, when the
        provider may have been unreachable or unconfigured -- and an owner who
        fixed that should not have to delete the domain and start again.
        """
        from .email_identity import SendingSetupError
        from .email_provider import provider

        identity = self.get_object()
        try:
            provider().register(identity)
        except SendingSetupError as exc:
            return Response({"detail": str(exc)}, status=http.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(identity).data)


class LeadApiKeyViewSet(ModelViewSet):
    """The keys a gym puts in their website's contact form.

    Several are allowed on purpose: replacing a compromised key should not mean
    taking the working form down first. Revoking is a flag rather than a delete
    so the usage trail survives the decision.
    """

    serializer_class = LeadApiKeySerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return LeadApiKey.objects.all()

    def create(self, request, *args, **kwargs):
        form = self.get_serializer(data=request.data)
        form.is_valid(raise_exception=True)

        raw, hashed = generate_lead_key()

        # `is_active=True` explicitly, not left to the model default. DRF reads
        # a missing BooleanField as False for form input -- an unchecked
        # checkbox sends nothing -- so a form-encoded create was issuing keys
        # that were born revoked. JSON callers were unaffected, which is what
        # made it invisible from the admin screen. Issuing an inactive key is
        # meaningless in any case, so this is the only value it can take.
        key = form.save(key_hash=hashed, is_active=True)

        # The only time the plaintext exists outside the caller's browser. Not
        # stored, so an owner who loses it issues a new key rather than being
        # able to look the old one up -- which is the point of hashing it.
        data = self.get_serializer(key).data
        data["plaintext"] = raw
        return Response(data, status=http.HTTP_201_CREATED)


class PublicLeadView(APIView):
    """Accepts one enquiry from a gym's own website.

    The only unauthenticated write path in the system. It is safe not because
    the key is secret -- it sits in a public contact form and is not -- but
    because it can do exactly one thing: add a row to one gym's enquiry list.
    See `tenancy/leads.py` for the reasoning behind each defence.

    Always answers 201 to a well-formed request, including one it silently
    dropped as spam. Telling a bot which check caught it is a free lesson in
    getting past it, and a real visitor whose message tripped a filter should
    not be shown an error they cannot act on.
    """

    authentication_classes = [LeadKeyAuthentication]
    permission_classes = [IsLeadKey]
    throttle_classes = [LeadRateThrottle]

    def post(self, request):
        key = request.lead_key
        payload = request.data

        spam = looks_like_spam(payload)
        if spam:
            logger.info("Dropped a website lead for %s: %s", key.tenant.slug, spam)
            record_use(key, created=False)
            return Response({"received": True}, status=http.HTTP_201_CREATED)

        name = str(payload.get("name", "")).strip()
        phone = str(payload.get("phone", "")).strip()
        email = str(payload.get("email", "")).strip()

        # A lead with no way to reach them is not a lead. Phone or email will
        # do -- insisting on both loses people who will only give one.
        if not name or not (phone or email):
            # One of these is a visitor who left a box empty. A run of them is
            # a form whose fields were renamed when it was pasted in, so every
            # submission is being dropped -- which is exactly the silent
            # failure the gym needs telling about.
            record_failure(key, LeadFailure.PAYLOAD)
            return Response(
                {"detail": "A name and either a phone number or an email are needed."},
                status=http.HTTP_400_BAD_REQUEST,
            )

        note = str(payload.get("message", "")).strip()

        # Written inside the gym's own scope, so the enquiry is stamped to them
        # by the same machinery every other row uses -- rather than this
        # endpoint setting the tenant by hand and being the one place that
        # could get it wrong.
        with context.scope(key.tenant):
            enquiry = Enquiry.objects.create(
                name=name[:150],
                phone=phone[:20],
                email=email[:254],
                source=EnquirySource.WEBSITE,
                # Today, so it lands in the front desk's call list straight
                # away. A lead from a website is at its warmest on arrival.
                follow_up_on=timezone.localdate(),
                notes=note[:2000],
            )

        record_use(key, created=True)
        # The id is not returned. A public caller has no use for it, and
        # handing back a primary key from a shared pipeline leaks how many
        # enquiries a gym has.
        return Response({"received": True}, status=http.HTTP_201_CREATED)
