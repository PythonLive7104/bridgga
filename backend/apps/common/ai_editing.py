"""Applying agent output to a record a human can correct.

The counterpart to :class:`apps.common.models.AIEditableModel`. These three
functions are the whole contract, and every agent that writes an editable
record goes through them rather than assigning fields itself:

``apply_ai_output``
    Write what the agent produced, skipping anything a human has edited.
``apply_edits``
    Record a human's change, and mark only what actually changed.
``reset_fields``
    Drop an edit and restore the agent's version.

Keeping them generic is deliberate. The rules below are subtle enough that a
second hand-written copy for the next model would get one of them wrong, and
the failure would be silent: a customer's correction quietly reverting the
next time their website changed.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.common.models import AIEditableModel
from apps.common.tenancy import tenant_context


@transaction.atomic
def apply_ai_output[ModelT: AIEditableModel](
    *,
    record: ModelT,
    values: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> ModelT:
    """Write agent output into a record, preserving human edits.

    Takes a plain dict rather than the schema object, because an agent may need
    to reshape its output first -- the ICP's buyer profile arrives nested and
    is stored flat, so each part stays separately editable.

    ``extra`` carries the fields that are the system's account of the run --
    evidence, confidence, timestamps, the prompt version. They are not part of
    ``AI_FIELDS`` because they are never edited by hand: they describe what
    happened, not what is true about the business.
    """
    with tenant_context(organization=record.organization):
        ai_values: dict[str, Any] = {}
        for field in type(record).AI_FIELDS:
            ai_values[field] = values.get(field)
            if record.was_edited(field):
                continue
            setattr(record, field, values.get(field) or record.empty_value_for(field))

        record.ai_values = ai_values
        for field, value in (extra or {}).items():
            setattr(record, field, value)
        record.save()

    return record


@transaction.atomic
def apply_edits[ModelT: AIEditableModel](*, record: ModelT, data: dict[str, Any]) -> list[str]:
    """Apply human edits and record which fields they touched.

    Returns the fields that actually changed. A value re-submitted unchanged
    does **not** mark the field as edited: a form posts every field whether or
    not the person touched it, and treating that as an edit of all of them
    would freeze the whole record against future analysis the first time
    anybody pressed Save.
    """
    changed: list[str] = []

    with tenant_context(organization=record.organization):
        for field, value in data.items():
            if field not in type(record).AI_FIELDS:
                continue
            if getattr(record, field) == value:
                continue
            setattr(record, field, value)
            changed.append(field)

        if changed:
            record.edited_fields = sorted(set(record.edited_fields) | set(changed))
            record.save()

    return changed


@transaction.atomic
def reset_fields[ModelT: AIEditableModel](*, record: ModelT, fields: list[str]) -> list[str]:
    """Drop a human edit and restore what the agent said.

    Needed because an edit is otherwise permanent: once a field is marked
    edited, no later run will touch it again. Without a way back, someone who
    mistypes a value has silently pinned that mistake forever.
    """
    restored: list[str] = []

    with tenant_context(organization=record.organization):
        for field in fields:
            if field not in type(record).AI_FIELDS or not record.was_edited(field):
                continue
            setattr(record, field, record.ai_value_for(field) or record.empty_value_for(field))
            restored.append(field)

        if restored:
            record.edited_fields = [f for f in record.edited_fields if f not in restored]
            record.save()

    return restored


__all__ = ["apply_ai_output", "apply_edits", "reset_fields"]
