from django.db.models import Sum
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from core.dates import read_window
from core.permissions import IsAdmin
from core.views import RefuseProtectedDeleteMixin

from .models import Expense, ExpenseCategory
from .serializers import ExpenseCategorySerializer, ExpenseSerializer


class ExpenseCategoryViewSet(RefuseProtectedDeleteMixin, ModelViewSet):
    protected_delete_message = (
        "This category has expenses recorded against it, so it can't be deleted. "
        "Deactivate it instead."
    )

    def get_queryset(self):
        # Built per request, not at import: the scoped manager needs a
        # tenant in scope and a class attribute is evaluated on load.
        return ExpenseCategory.objects.prefetch_related("expenses")
    serializer_class = ExpenseCategorySerializer
    permission_classes = [IsAdmin]


class ExpenseViewSet(ModelViewSet):
    """Spending is admin-only -- nothing about the gym's costs belongs in a
    member or trainer view."""

    serializer_class = ExpenseSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        queryset = Expense.objects.select_related("category", "recorded_by")
        params = self.request.query_params
        if params.get("category"):
            queryset = queryset.filter(category_id=params["category"])
        # Parsed before it reaches the ORM: a malformed date was a 500 there,
        # and a `to` before `from` quietly listed nothing.
        start, end = read_window(params)
        if start:
            queryset = queryset.filter(spent_on__gte=start)
        if end:
            queryset = queryset.filter(spent_on__lte=end)
        return queryset

    def perform_create(self, serializer):
        serializer.save(recorded_by=self.request.user)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Totals by category for the period, for the expenses panel and the
        P&L in reports."""
        queryset = self.get_queryset()
        by_category = (
            queryset.values("category__name")
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )
        return Response(
            {
                "total": queryset.aggregate(total=Sum("amount"))["total"] or 0,
                "count": queryset.count(),
                "by_category": [
                    {"category": row["category__name"], "total": row["total"]}
                    for row in by_category
                ],
            }
        )
