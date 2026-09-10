import re

from rest_framework import serializers

from .domains import expected_record
from .models import Domain, LeadApiKey, SendingDomain

#: Deliberately strict. A hostname with a scheme, a path or a port in it is the
#: commonest paste error ("https://app.mygym.com/"), and storing it would make
#: the domain silently never match an incoming request -- a failure the owner
#: cannot diagnose from the screen. Better to refuse it with a reason.
HOSTNAME = re.compile(
    r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$"
)


class DomainSerializer(serializers.ModelSerializer):
    is_verified = serializers.BooleanField(read_only=True)
    #: The row to paste into a registrar, as data rather than prose.
    dns_record = serializers.SerializerMethodField()

    class Meta:
        model = Domain
        fields = [
            "id",
            "hostname",
            "is_verified",
            "verified_at",
            "is_primary",
            "certificate",
            "dns_record",
            "last_checked_at",
            "last_error",
            "created_at",
        ]
        read_only_fields = [
            "id", "is_verified", "verified_at", "certificate",
            "last_checked_at", "last_error", "created_at",
        ]

    def get_dns_record(self, obj):
        # Shown until the domain is verified; afterwards it is noise, and
        # leaving it on screen invites someone to delete the record they still
        # need for re-verification.
        return expected_record(obj) if not obj.is_verified else None

    def validate_hostname(self, value):
        hostname = value.strip().lower().rstrip(".")
        if hostname.startswith(("http://", "https://")):
            raise serializers.ValidationError(
                "Just the hostname, without http:// or https:// -- for example "
                "app.yourgym.com."
            )
        if "/" in hostname:
            raise serializers.ValidationError(
                "Just the hostname, with no path after it."
            )
        if ":" in hostname:
            raise serializers.ValidationError("Leave the port off the hostname.")
        if not HOSTNAME.match(hostname):
            raise serializers.ValidationError(
                "That does not look like a hostname. Use something like "
                "app.yourgym.com."
            )
        # Unique across the platform, and the message says why without naming
        # the gym that holds it -- which would leak who else is on the platform.
        existing = Domain.unscoped.filter(hostname=hostname)
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError(
                "That domain is already registered on this platform."
            )
        return hostname


class SendingDomainSerializer(serializers.ModelSerializer):
    is_verified = serializers.BooleanField(read_only=True)
    from_email = serializers.CharField(read_only=True)
    dns_records = serializers.SerializerMethodField()

    class Meta:
        model = SendingDomain
        fields = [
            "id", "domain", "from_local_part", "from_name", "from_email",
            "spf_verified", "dkim_verified", "is_verified", "verified_at",
            "dns_records", "last_checked_at", "last_error", "created_at",
        ]
        read_only_fields = [
            "id", "spf_verified", "dkim_verified", "is_verified", "verified_at",
            "last_checked_at", "last_error", "created_at",
        ]

    def get_dns_records(self, obj):
        """The rows to publish, each with whether it is already satisfied.

        Carrying the per-record state is what lets the screen say "SPF done,
        DKIM still missing" instead of one undifferentiated failure -- with two
        records to add, "not verified" leaves an owner re-checking the one that
        was already right.
        """
        from .email_provider import provider

        include = provider().spf_include
        records = [
            {
                "purpose": "SPF",
                "explain": "Lets us send email using your domain.",
                "type": "TXT",
                "name": obj.domain,
                "value": f"v=spf1 include:{include} ~all",
                "note": (
                    "If you already have a line starting v=spf1, add "
                    f"include:{include} to it rather than adding a second one -- "
                    "two SPF records is an error and breaks your existing mail."
                ),
                "satisfied": obj.spf_verified,
            }
        ]
        if obj.dkim_selector:
            records.append({
                "purpose": "DKIM",
                "explain": "Signs your messages so they are not treated as forged.",
                "type": "TXT",
                "name": f"{obj.dkim_selector}._domainkey.{obj.domain}",
                "value": obj.dkim_value,
                "note": "Paste the value exactly; it is long and must not be wrapped.",
                "satisfied": obj.dkim_verified,
            })
        return records

    def validate_domain(self, value):
        hostname = value.strip().lower().rstrip(".")
        if "@" in hostname:
            raise serializers.ValidationError(
                "Just the domain, not a full address -- yourgym.com, not "
                "you@yourgym.com."
            )
        if not HOSTNAME.match(hostname):
            raise serializers.ValidationError(
                "That does not look like a domain. Use something like yourgym.com."
            )
        return hostname

    def validate_from_local_part(self, value):
        local = value.strip().lower()
        if not re.match(r"^[a-z0-9._-]{1,64}$", local):
            raise serializers.ValidationError(
                "Use letters, numbers, dots or dashes -- for example no-reply."
            )
        return local


class LeadApiKeySerializer(serializers.ModelSerializer):
    #: Present only in the response to a create. Never stored, never shown
    #: again -- the same contract as the device keys.
    plaintext = serializers.CharField(read_only=True)

    class Meta:
        model = LeadApiKey
        fields = [
            "id", "label", "allowed_origins", "is_active",
            "last_used_at", "leads_created", "created_at", "plaintext",
            "last_failure_at", "last_failure_reason", "failures_since_success",
        ]
        read_only_fields = [
            "id", "last_used_at", "leads_created", "created_at",
            "last_failure_at", "last_failure_reason", "failures_since_success",
        ]
