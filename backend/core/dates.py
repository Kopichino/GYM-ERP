"""Date windows read from a query string.

Reports parse their window once, at the edge (`reports.views.ReportWindowForm`).
Other read endpoints took `from` and `to` as they came: handed to the ORM, a
malformed date raised a validation error nobody caught -- a 500 -- and a `to`
before `from` quietly matched nothing, which reads as "nothing happened" rather
than "you asked for an impossible range".
"""

from rest_framework import serializers

#: The same words every report uses for a backwards window.
END_BEFORE_START = "The end date is before the start date."


def read_date(params, key, default=None):
    """One date from `params`, or `default` when it is left out or blank.

    A malformed date is a 400 naming its parameter, as in `read_window`.
    """
    raw = params.get(key)
    if raw in (None, ""):
        return default
    try:
        return serializers.DateField().to_internal_value(raw)
    except serializers.ValidationError as exc:
        raise serializers.ValidationError({key: exc.detail}) from exc


def read_window(params, start="from", end="to"):
    """`(start, end)` as dates from `params`, either one None when left out.

    A malformed date is a 400 naming its parameter, and so is an end before the
    start -- named on the end, which is the one to change.
    """
    field = serializers.DateField()
    values, errors = {}, {}
    for key in (start, end):
        raw = params.get(key)
        if raw in (None, ""):
            continue
        try:
            values[key] = field.to_internal_value(raw)
        except serializers.ValidationError as exc:
            errors[key] = exc.detail
    first, last = values.get(start), values.get(end)
    if not errors and first and last and last < first:
        errors[end] = [END_BEFORE_START]
    if errors:
        raise serializers.ValidationError(errors)
    return first, last
