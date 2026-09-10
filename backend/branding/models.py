from django.core.validators import RegexValidator
from django.db import models

from tenancy.managers import TenantManager, UnscopedManager

HEX = RegexValidator(r"^#(?:[0-9a-fA-F]{3}){1,2}$", "Use a hex colour like #ff3d5a.")


class DisplayFont(models.TextChoices):
    """Headline fonts a gym may pick from.

    A closed list, not free text. Two reasons: an arbitrary font name is a
    network request to a third party the gym chose and we cannot vouch for, and
    a font that fails to load leaves the portal rendering headings in whatever
    the browser falls back to -- which looks broken and is nobody's brand.

    Only the *display* face is configurable. Body copy stays Inter, for the
    same reason the dark surfaces are not editable: legibility is the product's
    job, and a decorative body font makes every screen worse.
    """

    BEBAS = "Bebas Neue", "Bebas Neue - condensed, athletic (default)"
    ANTON = "Anton", "Anton - heavy and blunt"
    OSWALD = "Oswald", "Oswald - condensed, quieter"
    ARCHIVO = "Archivo Black", "Archivo Black - very heavy"
    TEKO = "Teko", "Teko - squared, sporty"


class Branding(models.Model):
    """The gym's own identity, editable at runtime.

    White-label without a rebuild: one deployment renders as whichever gym is
    configured, because the portal reads its name, logo and colours from here at
    boot rather than from compiled-in constants.

    A single row, kept as a row rather than settings because a gym changes its
    accent colour on a whim and should not need a redeploy to do it. Settings
    still supply the fallback, so an unconfigured install looks like IRONCORE
    instead of looking broken.
    """
    # Shared across the brand's branches: a chain maintains one price list, one
    # badge ladder, one identity -- not one copy per building. Nullable for now;
    # the backfill fills it and a later migration makes it required.
    organisation = models.ForeignKey(
        "tenancy.Organisation",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    name = models.CharField(max_length=80, help_text="Shown in the header and on invoices.")
    tagline = models.CharField(max_length=140, blank=True)
    logo = models.ImageField(upload_to="branding/", null=True, blank=True)
    # Only the two brand hues are configurable. The dark surfaces are part of
    # the product's design rather than a gym's identity, and letting someone set
    # a white background on a dark theme produces an unreadable portal.
    accent = models.CharField(max_length=7, default="#ff3d5a", validators=[HEX])
    accent_2 = models.CharField(max_length=7, default="#ffb020", validators=[HEX])
    display_font = models.CharField(
        max_length=20,
        choices=DisplayFont.choices,
        default=DisplayFont.BEBAS,
        help_text="Headline font. Body text is always Inter, for legibility.",
    )
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True, help_text="Printed on invoices.")
    website = models.URLField(blank=True)
    instagram = models.CharField(max_length=100, blank=True)
    # Invoicing reads these when set, falling back to settings otherwise, so a
    # gym can be fully configured without touching environment variables.
    gstin = models.CharField(max_length=20, blank=True)
    state = models.CharField(max_length=60, blank=True, help_text="For CGST/SGST vs IGST.")
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    #: Scoped to the brand that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "organisation"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-is_active", "-updated_at"]
        verbose_name_plural = "branding"
        constraints = [
            # One identity at a time: the portal asks "who is this gym?" and
            # that has to have a single answer.
            # One identity per brand, not one per platform. The old constraint
            # keyed on is_active alone, which meant the second gym to configure
            # itself was refused.
            models.UniqueConstraint(
                fields=["organisation", "is_active"],
                condition=models.Q(is_active=True),
                name="one_active_branding_per_organisation",
            )
        ]

    @classmethod
    def current(cls):
        return cls.objects.filter(is_active=True).first()

    def __str__(self):
        return self.name
