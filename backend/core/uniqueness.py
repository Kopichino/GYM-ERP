"""Unique names and codes, reported on the field rather than as a 500.

The database guarantees these: each model carries a UniqueConstraint scoped to
its brand. DRF cannot turn those into validators by itself, because the brand is
not a field the client sends -- so a duplicate went straight to the INSERT and
escaped as an IntegrityError.

Two pieces, because either alone leaves a gap:

* `UniqueInScope`, a serializer validator, catches the predictable duplicate
  before anything is written and names the field to change.
* `SaveConflictsAsValidationErrors`, a serializer mixin, catches the duplicate
  validation cannot see: two saves racing past it together. The constraint stops
  the second, and this reports that as the same field error. It re-runs the
  check rather than parsing the database's message, which differs between SQLite
  and Postgres, and re-raises anything the check cannot explain -- a genuine
  integrity bug must still surface as one.
"""

from django.db import IntegrityError, transaction
from rest_framework import serializers


class Rule:
    """One uniqueness rule, mirroring one constraint.

    `fields` is a field name, or several that are unique together. `field` is
    the one the admin is told to change (the last by default). `normalise` maps
    a field to what the model does to it before saving, so the check compares
    what will actually be stored. `applies` limits a rule to the rows a
    conditional constraint covers.
    """

    def __init__(self, fields, message, *, field=None, normalise=None, applies=None):
        self.fields = (fields,) if isinstance(fields, str) else tuple(fields)
        self.field = field or self.fields[-1]
        self.message = message
        self.normalise = normalise or {}
        self.applies = applies


class UniqueInScope:
    """Serializer validator: no two rows in scope may break these rules.

    "In scope" comes from the model's tenant-scoped manager, so it is the brand
    or branch the request is for -- the same scope the constraint uses.
    """

    requires_context = True

    def __init__(self, *rules):
        self.rules = rules

    def conflicts(self, serializer, attrs):
        """{field: [message]} for every rule the values in `attrs` would break."""
        model = serializer.Meta.model
        instance = serializer.instance
        errors = {}
        for rule in self.rules:
            if not any(name in attrs for name in rule.fields):
                # Nothing this rule covers is being set.
                continue
            values = {}
            for name in rule.fields:
                value = attrs[name] if name in attrs else getattr(instance, name, None)
                normalise = rule.normalise.get(name)
                values[name] = normalise(value) if normalise and value is not None else value
            if any(value is None for value in values.values()):
                # NULLs never collide in a unique index.
                continue
            if rule.applies and not rule.applies(values):
                continue
            clashes = model.objects.filter(**values)
            if instance is not None:
                clashes = clashes.exclude(pk=instance.pk)
            if clashes.exists():
                errors[rule.field] = [rule.message]
        return errors

    def __call__(self, attrs, serializer):
        errors = self.conflicts(serializer, attrs)
        if errors:
            raise serializers.ValidationError(errors)


class SaveConflictsAsValidationErrors:
    """Serializer mixin: a unique constraint that stops a save is a 400 on the field.

    Pair with a `UniqueInScope` in `Meta.validators`. The save runs in its own
    savepoint, so the failed INSERT does not break a surrounding transaction and
    the follow-up check can still query.
    """

    def create(self, validated_data):
        try:
            with transaction.atomic():
                return super().create(validated_data)
        except IntegrityError:
            self._raise_conflict(validated_data)

    def update(self, instance, validated_data):
        try:
            with transaction.atomic():
                return super().update(instance, validated_data)
        except IntegrityError:
            self._raise_conflict(validated_data)

    def _raise_conflict(self, data):
        errors = {}
        for validator in self.validators:
            if isinstance(validator, UniqueInScope):
                errors.update(validator.conflicts(self, data))
        if not errors:
            # Not a duplicate this serializer knows about: let it surface.
            raise
        raise serializers.ValidationError(errors)
