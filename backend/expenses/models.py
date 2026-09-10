from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from core.storage import private_media_storage
from tenancy.managers import TenantManager, UnscopedManager
from django.utils import timezone


class ExpenseCategory(models.Model):
    """Rent, salaries, equipment, utilities -- whatever this gym actually spends
    on. Seeded with sensible defaults but fully editable."""
    # Shared across the brand's branches: a chain maintains one price list, one
    # badge ladder, one identity -- not one copy per building. Nullable for now;
    # the backfill fills it and a later migration makes it required.
    organisation = models.ForeignKey(
        "tenancy.Organisation",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    name = models.CharField(max_length=80)
    description = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    # Shared across the brand's branches, so scoping follows the organisation.
    tenant_field = "organisation"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "expense categories"
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "name"],
                name="one_expense_category_per_organisation",
            )
        ]

    @property
    def total_spent(self):
        return sum((e.amount for e in self.expenses.all()), 0)

    def __str__(self):
        return self.name


class Expense(models.Model):
    """One outgoing payment. The other half of the P&L: revenue lives in the
    billing ledger, costs live here, and the reports app subtracts one from the
    other rather than either side storing a running total."""
    # The branch this belongs to. Operational data is isolated per building:
    # "who came in yesterday" is a question about a gym, not about a brand.
    # Nullable for now; the backfill fills it and a later migration requires it.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    category = models.ForeignKey(
        ExpenseCategory, on_delete=models.PROTECT, related_name="expenses"
    )
    amount = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )
    spent_on = models.DateField(default=timezone.localdate)
    vendor = models.CharField(max_length=150, blank=True)
    reference = models.CharField(max_length=100, blank=True, help_text="Bill or invoice number.")
    notes = models.TextField(blank=True)
    # Private delivery, not Cloudinary's default public one: a receipt is a
    # financial document belonging to one branch, and the public URL carried no
    # authentication and no tenant. See core.storage.
    receipt = models.FileField(
        upload_to="receipts/",
        storage=private_media_storage,
        null=True,
        blank=True,
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="expenses_recorded",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-spent_on", "-id"]
        indexes = [models.Index(fields=["spent_on"])]

    def __str__(self):
        return f"{self.category} - {self.amount} on {self.spent_on}"
