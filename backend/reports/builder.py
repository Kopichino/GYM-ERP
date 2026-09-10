"""The custom report builder.

A definition arrives as JSON from the browser, so nothing in it is trusted:
the source, every field, every filter operator and every aggregate is looked up
in a whitelist. A queryset is never assembled from a raw client string, which is
what turns "build me a report" into "read any table you like".
"""

from decimal import Decimal

from django.db.models import Avg, Count, Max, Min, Sum

from attendance.models import CheckInOut
from billing.models import Payment
from crm.models import Enquiry
from expenses.models import Expense
from workouts.models import WorkoutSession

# source -> what may be selected, grouped and filtered on.
SOURCES = {
    "payments": {
        "label": "Payments",
        "model": Payment,
        "fields": {
            "member": "member__username",
            "plan": "plan__name",
            "amount": "amount",
            "discount_amount": "discount_amount",
            "method": "method",
            "status": "status",
            "paid_date": "paid_date",
            "period_end": "period_end",
        },
        "date_field": "paid_date",
    },
    "attendance": {
        "label": "Check-ins",
        "model": CheckInOut,
        "fields": {
            "member": "user__username",
            "method": "method",
            "check_in": "check_in_time",
        },
        "date_field": "check_in_time__date",
    },
    "expenses": {
        "label": "Expenses",
        "model": Expense,
        "fields": {
            "category": "category__name",
            "amount": "amount",
            "vendor": "vendor",
            "spent_on": "spent_on",
        },
        "date_field": "spent_on",
    },
    "enquiries": {
        "label": "Enquiries",
        "model": Enquiry,
        "fields": {
            "name": "name",
            "phone": "phone",
            "status": "status",
            "follow_up_on": "follow_up_on",
        },
        "date_field": "follow_up_on",
    },
    "workouts": {
        "label": "Workout sessions",
        "model": WorkoutSession,
        "fields": {"member": "user__username", "date": "date"},
        "date_field": "date",
    },
}

OPERATORS = {
    "eq": "exact",
    "ne": "exact",  # negated below
    "contains": "icontains",
    "gt": "gt",
    "gte": "gte",
    "lt": "lt",
    "lte": "lte",
    "in": "in",
}

AGGREGATES = {"count": Count, "sum": Sum, "avg": Avg, "min": Min, "max": Max}

MAX_ROWS = 1000


class ReportError(Exception):
    """A definition that cannot be run, with a reason to show the builder."""


def _resolve(source, name):
    field = SOURCES[source]["fields"].get(name)
    if field is None:
        raise ReportError(f"'{name}' isn't a field you can use on {source}.")
    return field


def run(definition):
    """Executes a report definition and returns {columns, rows}."""
    source = definition.get("source")
    if source not in SOURCES:
        raise ReportError(f"Unknown source '{source}'. Choose one of: {', '.join(SOURCES)}.")

    spec = SOURCES[source]
    queryset = spec["model"].objects.all()

    # Date window, applied against the source's own natural date field.
    if definition.get("start"):
        queryset = queryset.filter(**{f"{spec['date_field']}__gte": definition["start"]})
    if definition.get("end"):
        queryset = queryset.filter(**{f"{spec['date_field']}__lte": definition["end"]})

    for clause in definition.get("filters", []) or []:
        field, operator, value = clause.get("field"), clause.get("op", "eq"), clause.get("value")
        if operator not in OPERATORS:
            raise ReportError(f"'{operator}' isn't a supported comparison.")
        lookup = f"{_resolve(source, field)}__{OPERATORS[operator]}"
        if operator == "ne":
            queryset = queryset.exclude(**{lookup: value})
        else:
            queryset = queryset.filter(**{lookup: value})

    group_by = definition.get("group_by")
    aggregates = definition.get("aggregates") or []

    if group_by:
        group_field = _resolve(source, group_by)
        queryset = queryset.values(group_field)
        annotations, columns = {}, [group_by]
        for agg in aggregates:
            kind = agg.get("fn", "count")
            if kind not in AGGREGATES:
                raise ReportError(f"'{kind}' isn't a supported aggregate.")
            target = _resolve(source, agg["field"]) if agg.get("field") else "id"
            alias = agg.get("alias") or f"{kind}_{agg.get('field', 'rows')}"
            annotations[alias] = AGGREGATES[kind](target)
            columns.append(alias)
        queryset = queryset.annotate(**annotations)

        rows = []
        for row in queryset[:MAX_ROWS]:
            out = {group_by: row[group_field]}
            for column in columns[1:]:
                value = row[column]
                out[column] = str(value) if isinstance(value, Decimal) else value
            rows.append(out)
        return {"columns": columns, "rows": rows, "row_count": len(rows)}

    # Plain listing.
    selected = definition.get("fields") or list(spec["fields"])
    mapped = {name: _resolve(source, name) for name in selected}
    queryset = queryset.values(*mapped.values())[:MAX_ROWS]

    rows = []
    for row in queryset:
        out = {}
        for name, field in mapped.items():
            value = row[field]
            out[name] = str(value) if isinstance(value, Decimal) else value
        rows.append(out)
    return {"columns": selected, "rows": rows, "row_count": len(rows)}


def schema():
    """What the builder UI offers -- derived from the whitelist itself, so the
    form can never present a field the runner would reject."""
    return [
        {
            "source": key,
            "label": spec["label"],
            "fields": sorted(spec["fields"]),
        }
        for key, spec in SOURCES.items()
    ]
