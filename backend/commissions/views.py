from django.db.models import Sum
from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from accounts.models import User
from core.permissions import IsAdmin, IsTrainer

from .models import CommissionEntry, CommissionRule, EntryStatus, Payout
from .serializers import CommissionEntrySerializer, CommissionRuleSerializer, PayoutSerializer
from .services import settle


class CommissionRuleViewSet(ModelViewSet):

    def get_queryset(self):
        # Built per request, not at import: the scoped manager needs a
        # tenant in scope and a class attribute is evaluated on load.
        return CommissionRule.objects.select_related("trainer", "plan")
    serializer_class = CommissionRuleSerializer
    permission_classes = [IsAdmin]


class CommissionEntryViewSet(ReadOnlyModelViewSet):
    """Entries are raised by the payment flow, never typed in by hand -- so
    they're read-only, and a correction happens by voiding the payment."""

    serializer_class = CommissionEntrySerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        queryset = CommissionEntry.objects.select_related(
            "trainer", "payment__member", "payment__plan"
        )
        params = self.request.query_params
        if params.get("trainer"):
            queryset = queryset.filter(trainer_id=params["trainer"])
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        return queryset


class PayoutViewSet(ModelViewSet):

    def get_queryset(self):
        # Built per request, not at import: the scoped manager needs a
        # tenant in scope and a class attribute is evaluated on load.
        return Payout.objects.select_related("trainer").prefetch_related("entries")
    serializer_class = PayoutSerializer
    permission_classes = [IsAdmin]

    def create(self, request, *args, **kwargs):
        """Settles every pending entry in the window rather than taking a total
        from the client -- the figure has to come from the entries themselves."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        payout = settle(
            trainer=data["trainer"],
            period_start=data["period_start"],
            period_end=data["period_end"],
            notes=data.get("notes", ""),
        )
        return Response(self.get_serializer(payout).data, status=201)


class MyEarningsView(ReadOnlyModelViewSet):
    """A trainer's own commission. Scoped hard to the caller -- one trainer must
    not be able to read another's earnings."""

    serializer_class = CommissionEntrySerializer
    permission_classes = [IsTrainer]

    def get_queryset(self):
        return CommissionEntry.objects.filter(trainer=self.request.user).select_related(
            "payment__member", "payment__plan"
        )

    @action(detail=False, methods=["get"])
    def summary(self, request):
        entries = self.get_queryset()
        pending = entries.filter(status=EntryStatus.PENDING)
        paid = entries.filter(status=EntryStatus.PAID)
        return Response(
            {
                "pending_total": pending.aggregate(t=Sum("amount"))["t"] or 0,
                "pending_count": pending.count(),
                "paid_total": paid.aggregate(t=Sum("amount"))["t"] or 0,
                "paid_count": paid.count(),
            }
        )
