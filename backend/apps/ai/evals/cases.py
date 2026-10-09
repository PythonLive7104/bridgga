"""Eval cases and expectations (PRD section 106).

An agent without an eval set cannot be changed safely: there is no way to tell
whether a prompt edit improved things, and no way to catch a model upgrade
silently degrading output.

The expectations here are deliberately weighted towards what actually goes
wrong with this product rather than towards scoring well:

* **Grounding.** The failure that matters most is a confident invention --
  a competitor the site never names, a price it never published. ``Grounded``
  and ``FieldEmpty`` test for restraint, which no accuracy metric rewards.
* **Honest uncertainty.** A model that fills every field always scores higher
  on coverage and is worse for the product. ``FieldEmpty`` makes leaving a
  field blank the correct answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


@dataclass(slots=True)
class CheckResult:
    passed: bool
    detail: str = ""

    @classmethod
    def ok(cls, detail: str = "") -> CheckResult:
        return cls(True, detail)

    @classmethod
    def fail(cls, detail: str) -> CheckResult:
        return cls(False, detail)


@runtime_checkable
class Expectation(Protocol):
    """One assertion about an output."""

    name: str

    def check(self, output: BaseModel, case: EvalCase) -> CheckResult: ...


def read_path(output: BaseModel, path: str) -> Any:
    """Read a dotted path, e.g. ``buyer.job_titles``."""
    value: Any = output
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            value = getattr(value, part, None)
        if value is None:
            return None
    return value


@dataclass(slots=True)
class FieldEquals:
    path: str
    expected: Any
    name: str = "field_equals"

    def check(self, output: BaseModel, case: EvalCase) -> CheckResult:
        actual = read_path(output, self.path)
        if actual == self.expected:
            return CheckResult.ok()
        return CheckResult.fail(f"{self.path}: expected {self.expected!r}, got {actual!r}")


@dataclass(slots=True)
class FieldContains:
    """Case-insensitive substring match on a string or any list member."""

    path: str
    needle: str
    name: str = "field_contains"

    def check(self, output: BaseModel, case: EvalCase) -> CheckResult:
        actual = read_path(output, self.path)
        needle = self.needle.lower()

        if isinstance(actual, str):
            found = needle in actual.lower()
        elif isinstance(actual, (list, tuple, set)):
            found = any(needle in str(item).lower() for item in actual)
        else:
            found = False

        if found:
            return CheckResult.ok()
        return CheckResult.fail(f"{self.path}: expected to contain {self.needle!r}, got {actual!r}")


@dataclass(slots=True)
class FieldEmpty:
    """The field must be empty.

    This is the anti-fabrication check. When a source does not publish pricing,
    the correct output is an empty string -- not a plausible guess.
    """

    path: str
    name: str = "field_empty"

    def check(self, output: BaseModel, case: EvalCase) -> CheckResult:
        actual = read_path(output, self.path)
        if actual in (None, "", [], {}, ()):
            return CheckResult.ok()
        return CheckResult.fail(f"{self.path}: expected empty, got {actual!r} (fabricated?)")


@dataclass(slots=True)
class FieldNotEmpty:
    path: str
    name: str = "field_not_empty"

    def check(self, output: BaseModel, case: EvalCase) -> CheckResult:
        actual = read_path(output, self.path)
        if actual in (None, "", [], {}, ()):
            return CheckResult.fail(f"{self.path}: expected a value, got {actual!r}")
        return CheckResult.ok()


@dataclass(slots=True)
class Grounded:
    """Every item at ``path`` must appear in the source text.

    The hallucination check. A competitor or product name the model produced
    that is nowhere in the source was invented, however plausible it reads.
    """

    path: str
    min_token_length: int = 4
    name: str = "grounded"

    def check(self, output: BaseModel, case: EvalCase) -> CheckResult:
        actual = read_path(output, self.path)
        if actual in (None, "", [], {}):
            return CheckResult.ok("nothing claimed")

        haystack = case.source_text().lower()
        items = actual if isinstance(actual, (list, tuple, set)) else [actual]

        ungrounded: list[str] = []
        for item in items:
            text = str(item).strip().lower()
            if not text:
                continue
            if text in haystack:
                continue
            # Allow a partial match on a significant token, so "Acme Logistics
            # Ltd" still counts as grounded when the page says "Acme Logistics".
            tokens = [t for t in re.split(r"\W+", text) if len(t) >= self.min_token_length]
            if tokens and any(token in haystack for token in tokens):
                continue
            ungrounded.append(str(item))

        if ungrounded:
            return CheckResult.fail(f"{self.path}: not found in source: {ungrounded}")
        return CheckResult.ok()


@dataclass(slots=True)
class EvidenceGrounded:
    """Every evidence entry must quote or cite something in the source."""

    path: str = "evidence"
    name: str = "evidence_grounded"

    def check(self, output: BaseModel, case: EvalCase) -> CheckResult:
        entries = read_path(output, self.path) or []
        haystack = case.source_text().lower()

        problems: list[str] = []
        for entry in entries:
            quote = (getattr(entry, "quote", "") or "").strip().lower()
            url = (getattr(entry, "source_url", "") or "").strip().lower()
            if quote and quote not in haystack:
                problems.append(f"quote not in source: {quote[:60]!r}")
            if url and url not in haystack and not case.allow_external_urls:
                problems.append(f"url not in source: {url}")

        if problems:
            return CheckResult.fail("; ".join(problems[:3]))
        return CheckResult.ok()


@dataclass(slots=True)
class AnyItemHas:
    """Some item in a list field carries ``value`` at ``item_path``.

    For outputs whose answer is a list of judgements rather than one: "did it
    find a pricing-change signal?" is a question about the set, not about a
    particular position in it.
    """

    path: str
    item_path: str
    value: Any
    name: str = "any_item_has"

    def check(self, output: BaseModel, case: EvalCase) -> CheckResult:
        items = read_path(output, self.path) or []
        found = [str(read_path(item, self.item_path)) for item in items]
        if str(self.value) in found:
            return CheckResult.ok()
        return CheckResult.fail(f"{self.path}[].{self.item_path}: {self.value!r} not in {found}")


@dataclass(slots=True)
class NoItemHas:
    """No item in a list field carries ``value`` at ``item_path``.

    The anti-fabrication check for list outputs, and the one an injection case
    needs: a diff that mentions no money must not produce a funding signal,
    however insistently the page asks for one.
    """

    path: str
    item_path: str
    value: Any
    name: str = "no_item_has"

    def check(self, output: BaseModel, case: EvalCase) -> CheckResult:
        items = read_path(output, self.path) or []
        found = [str(read_path(item, self.item_path)) for item in items]
        if str(self.value) not in found:
            return CheckResult.ok()
        return CheckResult.fail(f"{self.path}[].{self.item_path}: {self.value!r} was claimed")


@dataclass(slots=True)
class ItemEvidenceGrounded:
    """Every item's evidence quotes something in the source.

    The same rule ``EvidenceGrounded`` applies to a flat output, applied to
    each judgement in a list. Worth testing even though
    ``apps.companies.signal_agents`` also enforces it in code: the code check
    tells us an ungrounded signal was discarded, this tells us whether the
    prompt stopped it being produced.
    """

    path: str = "signals"
    name: str = "item_evidence_grounded"

    def check(self, output: BaseModel, case: EvalCase) -> CheckResult:
        haystack = re.sub(r"\s+", " ", case.source_text().lower())
        problems: list[str] = []

        for item in read_path(output, self.path) or []:
            quotes = [
                re.sub(r"\s+", " ", (getattr(entry, "quote", "") or "").strip().lower())
                for entry in (getattr(item, "evidence", None) or [])
            ]
            usable = [quote for quote in quotes if len(quote) >= 12]
            if not usable:
                problems.append(f"{read_path(item, 'type')}: no usable quote")
            elif not any(quote in haystack for quote in usable):
                problems.append(f"{read_path(item, 'type')}: quote not in source")

        if problems:
            return CheckResult.fail("; ".join(problems[:3]))
        return CheckResult.ok()


@dataclass(slots=True)
class MaxItems:
    path: str
    limit: int
    name: str = "max_items"

    def check(self, output: BaseModel, case: EvalCase) -> CheckResult:
        actual = read_path(output, self.path) or []
        if len(actual) <= self.limit:
            return CheckResult.ok()
        return CheckResult.fail(f"{self.path}: {len(actual)} items, limit {self.limit}")


@dataclass(slots=True)
class EvalCase:
    """One input with the expectations its output must satisfy."""

    id: str
    prompt_name: str
    user_content: str
    expectations: list[Any] = field(default_factory=list)
    cacheable_context: str = ""
    tags: list[str] = field(default_factory=list)
    # Some prompts legitimately cite a URL not present verbatim in the text.
    allow_external_urls: bool = False
    notes: str = ""

    def source_text(self) -> str:
        return f"{self.cacheable_context}\n{self.user_content}"


_CASES: list[EvalCase] = []


def register_case(case: EvalCase) -> EvalCase:
    if any(existing.id == case.id for existing in _CASES):
        raise ValueError(f"Duplicate eval case id {case.id!r}")
    _CASES.append(case)
    return case


def all_cases(*, prompt_name: str = "", tag: str = "") -> list[EvalCase]:
    cases = list(_CASES)
    if prompt_name:
        cases = [c for c in cases if c.prompt_name == prompt_name]
    if tag:
        cases = [c for c in cases if tag in c.tags]
    return cases
