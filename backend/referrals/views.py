from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from core.permissions import access, IsAdmin
from crm.models import Enquiry, EnquiryStatus

from .models import Referral, ReferralProgram, ReferralStatus
from .serializers import (
    MyReferralsSerializer,
    ReferralProgramSerializer,
    ReferralSerializer,
)
from .services import ReferralError, code_for, grant_reward


class ReferralProgramViewSet(ModelViewSet):
    """What the gym is offering. Admin-only to change; the member-facing
    summary reads the active one for everybody."""

    serializer_class = ReferralProgramSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        # Built per request, not at import: the scoped manager needs a
        # tenant in scope and a class attribute is evaluated on load.
        return ReferralProgram.objects.all()

    def perform_create(self, serializer):
        # Only one programme runs at a time -- a partial unique index enforces
        # it, so the previous one is retired in the same transaction.
        with transaction.atomic():
            ReferralProgram.objects.filter(is_active=True).update(is_active=False)
            serializer.save(is_active=True)


class ReferralViewSet(ModelViewSet):
    """A member raises referrals and sees their own; an admin sees the lot."""

    serializer_class = ReferralSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Referral.objects.select_related(
            "referrer", "referred_user", "reward", "enquiry"
        )
        if access(self.request).is_admin:
            referrer = self.request.query_params.get("referrer")
            return queryset.filter(referrer_id=referrer) if referrer else queryset
        return queryset.filter(referrer=self.request.user)

    def perform_create(self, serializer):
        referral = serializer.save(referrer=self.request.user)
        # A referral is a lead like any other, so it joins the same call-back
        # queue the front desk already works rather than a second list.
        if referral.phone and not referral.enquiry:
            from django.utils import timezone

            referral.enquiry = Enquiry.objects.create(
                name=referral.name,
                phone=referral.phone,
                follow_up_on=timezone.localdate(),
                status=EnquiryStatus.OPEN,
                notes=f"Referred by {self.request.user.username}.",
                created_by=self.request.user,
            )
            referral.save(update_fields=["enquiry"])

    @action(detail=False, methods=["get"])
    def mine(self, request):
        """Everything the member's referral page needs, in one call."""
        program = ReferralProgram.current()
        referrals = list(
            Referral.objects.filter(referrer=request.user).select_related(
                "referred_user", "reward"
            )
        )
        joined = [r for r in referrals if r.status == ReferralStatus.JOINED]
        return Response(
            MyReferralsSerializer(
                {
                    "code": code_for(request.user),
                    "blurb": program.blurb if program else "",
                    "reward_days": program.reward_days if program else 0,
                    "program_active": program is not None,
                    "total_referred": len(referrals),
                    "joined_count": len(joined),
                    # What they've actually been given, not what they're owed.
                    "days_earned": sum(
                        r.reward.days_granted for r in referrals if hasattr(r, "reward")
                    ),
                    "referrals": referrals,
                }
            ).data
        )

    @action(detail=True, methods=["post"], permission_classes=[IsAdmin])
    def reward(self, request, pk=None):
        """Pays the referrer their free days, as a zero-amount renewal."""
        referral = self.get_object()
        days = request.data.get("days")
        try:
            grant_reward(
                referral,
                granted_by=request.user,
                days=int(days) if days else None,
                notes=request.data.get("notes", ""),
            )
        except ReferralError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        referral.refresh_from_db()
        return Response(ReferralSerializer(referral).data, status=status.HTTP_201_CREATED)
