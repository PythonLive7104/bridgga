"""Deterministic stub provider.

Used by the test suite and by local development without an API key. It builds a
schema-valid instance from the output schema itself, so a caller gets the right
shape without a network call, a key, or a cent of spend.

It is not a mock of model *quality* -- it says nothing about whether a prompt
works. That is what the eval harness is for. This exists so that everything
around the model (tenancy, cost accounting, retries, job records) can be tested
without one.
"""

from __future__ import annotations

import enum
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from apps.ai.pricing import ModelSpec
from apps.ai.providers.base import (
    AIProvider,
    AIProviderError,
    CompletionRequest,
    CompletionResponse,
    TokenUsage,
)


class StubProvider(AIProvider):
    """Returns a schema-valid placeholder instance."""

    name = "stub"

    def __init__(
        self,
        *,
        responses: list[BaseModel | Exception] | None = None,
        usage: TokenUsage | None = None,
    ) -> None:
        # A queue lets a test script a sequence -- e.g. raise once, then
        # succeed -- to exercise the runner's retry path.
        self._responses = list(responses or [])
        self._usage = usage or TokenUsage(input_tokens=1000, output_tokens=250)
        self.calls: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest, *, spec: ModelSpec) -> CompletionResponse:
        self.calls.append(request)

        if self._responses:
            nxt = self._responses.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            parsed: BaseModel = nxt
        else:
            parsed = build_placeholder(request.output_schema)

        return CompletionResponse(
            parsed=parsed,
            raw_text=parsed.model_dump_json(),
            usage=self._usage,
            model_id=spec.model_id,
            stop_reason="end_turn",
            latency_ms=1.0,
        )


def build_placeholder(schema: type[BaseModel]) -> BaseModel:
    """Construct a minimal valid instance of ``schema``.

    Walks the declared fields rather than guessing from JSON schema, so a
    nested model is built recursively and a required field is never omitted.
    """
    values: dict[str, Any] = {}

    for name, field in schema.model_fields.items():
        if field.default is not PydanticUndefined:
            continue
        if field.default_factory is not None:
            continue
        values[name] = _placeholder_for(field.annotation, name)

    return schema(**values)


def _placeholder_for(annotation: Any, field_name: str) -> Any:
    import types
    import typing

    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    # Optional[X] / X | None -> use the non-None arm.
    if origin in (typing.Union, types.UnionType):
        non_none = [arg for arg in args if arg is not type(None)]
        if not non_none:
            return None
        return _placeholder_for(non_none[0], field_name)

    if origin in (list, set, tuple):
        return []
    if origin is dict:
        return {}

    if isinstance(annotation, type):
        # Enum must be checked before str and int: StrEnum subclasses str and
        # IntEnum subclasses int, so the plain-scalar branches below would
        # otherwise produce a value the enum rejects.
        if issubclass(annotation, enum.Enum):
            return next(iter(annotation))
        if issubclass(annotation, BaseModel):
            return build_placeholder(annotation)
        if issubclass(annotation, bool):
            return False
        if issubclass(annotation, int):
            return 0
        if issubclass(annotation, float):
            return 0.0
        if issubclass(annotation, datetime):
            return datetime(2026, 1, 1, tzinfo=UTC)
        if issubclass(annotation, str):
            return f"stub-{field_name}"

    return None


class ExplodingProvider(AIProvider):
    """Always fails. For asserting the runner records failures properly."""

    name = "exploding"

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error or AIProviderError("stub failure")

    def complete(self, request: CompletionRequest, *, spec: ModelSpec) -> CompletionResponse:
        raise self.error


def to_json(model: BaseModel) -> str:
    return json.dumps(model.model_dump(mode="json"), sort_keys=True)
