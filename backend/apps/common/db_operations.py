"""Migration operations that apply on Postgres and skip elsewhere.

Full-text and trigram indexes have no SQLite equivalent, and a migration that
tries to create one there fails outright. ADR 0006 keeps SQLite as a local
convenience while CI and production run Postgres, so the migration has to be
able to do less on the lesser database rather than refuse to run.

The state change is applied either way -- Django's model state must match on
both, or every later `makemigrations` would see a difference and try to
"fix" it.
"""

from __future__ import annotations

from typing import Any

from django.db import migrations


class PostgresOnlyIndex(migrations.AddIndex):
    """Create an index only where the database supports it."""

    def database_forwards(
        self, app_label: str, schema_editor: Any, from_state: Any, to_state: Any
    ) -> None:
        if schema_editor.connection.vendor != "postgresql":
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(
        self, app_label: str, schema_editor: Any, from_state: Any, to_state: Any
    ) -> None:
        if schema_editor.connection.vendor != "postgresql":
            return
        super().database_backwards(app_label, schema_editor, from_state, to_state)


__all__ = ["PostgresOnlyIndex"]
