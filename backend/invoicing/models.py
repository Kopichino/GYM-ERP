from decimal import Decimal

from django.db import models, transaction

from tenancy.managers import TenantManager, UnscopedManager
from django.utils import timezone


def financial_year_for(day):
    """India's financial year runs April-March, so an invoice dated
    2026-02-11 belongs to FY 2025-26, not 2026-27."""
    year = day.year if day.month >= 4 else day.year - 1
    return f"{year}-{str(year + 1)[-2:]}"


class InvoiceCounter(models.Model):
    """One row per financial year, holding the last number issued.

    Statutory invoice numbers must be sequential with no gaps, and two
    simultaneous checkouts computing `count() + 1` would collide. Allocation
    takes a row lock so numbers are handed out one caller at a time -- the same
    discipline the one-open-check-in rule uses.
    """
    # The branch this belongs to. Operational data is isolated per building:
    # "who came in yesterday" is a question about a gym, not about a brand.
    # Nullable for now; the backfill fills it and a later migration requires it.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    financial_year = models.CharField(max_length=9)
    last_number = models.PositiveIntegerField(default=0)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-financial_year"]
        constraints = [
            # One counter per branch per year. Previously unique on the year
            # alone, which would have had two gyms drawing from a single
            # sequence -- leaving each of their own runs full of holes, and a
            # gapless statutory sequence is the entire point of this table.
            models.UniqueConstraint(
                fields=["tenant", "financial_year"],
                name="one_counter_per_tenant_per_year",
            )
        ]

    @classmethod
    def next_for(cls, tenant, day):
        """Allocate the next number for one branch's financial year.

        Keyed on the branch as well as the year. Sharing a sequence between two
        gyms would leave each of their own runs full of holes, which is exactly
        the filing problem a gapless counter exists to avoid -- and a burnt
        number cannot be recovered afterwards.
        """
        fy = financial_year_for(day)
        with transaction.atomic():
            # `.unscoped` because the tenant is an argument here: this runs from
            # checkout inside a request and from tooling outside one, and the
            # caller has already said which branch's sequence to draw from.
            counter, _ = cls.unscoped.select_for_update().get_or_create(
                tenant=tenant, financial_year=fy
            )
            counter.last_number += 1
            counter.save(update_fields=["last_number"])
            return fy, counter.last_number

    def __str__(self):
        return f"{self.financial_year}: {self.last_number}"


class Invoice(models.Model):
    """A GST invoice for one payment.

    Tax is stored rather than derived, unlike most figures in this project:
    an invoice is a statutory record of what was charged on the day, so it must
    not silently restate itself if the tax rate or the plan price changes later.
    """
    # The branch this belongs to. Operational data is isolated per building:
    # "who came in yesterday" is a question about a gym, not about a brand.
    # Nullable for now; the backfill fills it and a later migration requires it.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    payment = models.OneToOneField(
        "billing.Payment", on_delete=models.CASCADE, related_name="invoice"
    )
    number = models.CharField(max_length=40)
    financial_year = models.CharField(max_length=9)
    sequence = models.PositiveIntegerField()
    issued_on = models.DateField(default=timezone.localdate)

    # Snapshotted so a reprint years later matches the original.
    seller_gstin = models.CharField(max_length=15, blank=True)
    buyer_gstin = models.CharField(max_length=15, blank=True)
    place_of_supply = models.CharField(max_length=60, blank=True)

    taxable_value = models.DecimalField(max_digits=10, decimal_places=2)
    cgst = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    sgst = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    igst = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField(max_digits=10, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("18"))

    pdf = models.FileField(upload_to="invoices/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-issued_on", "-sequence"]
        constraints = [
            # Unique within the branch that issued it. Globally unique would
            # have been wrong the moment two gyms adopted the same numbering
            # format, which the tenant prefix makes likely rather than rare.
            models.UniqueConstraint(
                fields=["tenant", "number"], name="one_invoice_number_per_tenant"
            )
        ]

    @property
    def is_interstate(self):
        return self.igst > 0

    def __str__(self):
        return self.number
