from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from billing.models import Payment
from core.permissions import access, IsAdmin, IsTenantMember

from .models import Invoice
from .pdf import render_invoice
from .serializers import InvoiceSerializer
from .services import issue_invoice


class InvoiceViewSet(ReadOnlyModelViewSet):
    """Invoices are issued by the system and never hand-edited -- a statutory
    document that can be rewritten isn't worth much. Hence read-only."""

    serializer_class = InvoiceSerializer
    # Standing at the gym in the URL, not just a signed-in account: without it a
    # person from another gym could read this gym's (empty) list for them and
    # file new rows under a gym they do not belong to.
    permission_classes = [IsTenantMember]

    def get_queryset(self):
        queryset = Invoice.objects.select_related("payment__member", "payment__plan")
        # A member sees only their own; an admin sees the whole book.
        if not access(self.request).is_admin:
            return queryset.filter(payment__member=self.request.user)
        member = self.request.query_params.get("member")
        return queryset.filter(payment__member_id=member) if member else queryset

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        invoice = self.get_object()
        response = HttpResponse(render_invoice(invoice), content_type="application/pdf")
        filename = invoice.number.replace("/", "-")
        response["Content-Disposition"] = 'inline; filename="%s.pdf"' % filename
        return response

    @action(detail=False, methods=["post"], permission_classes=[IsAdmin])
    def issue(self, request):
        """Issue (or fetch) the invoice for a payment that lacks one -- used for
        payments recorded before invoicing existed."""
        payment = get_object_or_404(Payment, pk=request.data.get("payment"))
        invoice = issue_invoice(
            payment,
            place_of_supply=request.data.get("place_of_supply", ""),
            buyer_gstin=request.data.get("buyer_gstin", ""),
        )
        return Response(InvoiceSerializer(invoice).data, status=201)
