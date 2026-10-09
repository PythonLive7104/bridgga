"""Interpreting a website change with a model (PRD sections 33, 58).

The deterministic detectors can tell that a homepage changed. They cannot tell
whether it changed because the company launched a product, opened an office or
rotated a testimonial -- and that difference is the whole value of the signal.
This is the one place in the signal engine that spends money, and the design
is shaped by keeping that spend honest:

* **It runs second, never first.** ``WebsiteChangeDetector`` has already
  established that something non-cosmetic changed. Without that gate this
  would be a model call per prospect per crawl, most of them to report that
  nothing happened.
* **It is shown the diff, not the page.** Sending the whole site would cost
  ten times as much and bury the change in unchanged text.
* **Its output is verified in code, not trusted.** Every interpreted signal
  must quote the supplied diff verbatim; anything else is dropped before it
  reaches the database. The prompt asks for grounding, but a prompt is a
  request and this is an enforcement. Page content is attacker-controlled --
  anyone can write "we just raised $20M" on a website, or an instruction
  aimed at this very prompt -- so the check belongs here where it cannot be
  talked out of.
"""

from __future__ import annotations

import re
from typing import Any

import structlog
from django.utils import timezone

from apps.ai.runner import run_prompt
from apps.ai.schemas import Confidence, SignalType
from apps.companies.detectors import (
    DetectedSignal,
    SnapshotPair,
    evidence_entry,
    fingerprint_of,
    normalise_path,
    sentences,
)
from apps.companies.signal_engine import build_context, record_signal
from apps.companies.signal_models import LeadSignal

logger = structlog.get_logger(__name__)

DETECTOR_NAME = "ai_website_change"

#: Caps on what is sent. Generous enough to carry a real change, small enough
#: that the call stays a fraction of a cent.
MAX_NEW_SENTENCES = 40
MAX_DIFF_CHARS = 6_000

#: Shortest quote accepted as grounding. A two-character quote matches almost
#: any text and proves nothing.
MIN_QUOTE_CHARS = 12

#: Strength per type, for signals that came from interpretation rather than
#: measurement. Uniformly below what the deterministic detectors assign for
#: the same type: this is a model's reading of prose, and a changed price
#: that was diffed numerically is better evidence than one a model described.
STRENGTH_BY_TYPE: dict[str, int] = {
    SignalType.FUNDING: 65,
    SignalType.ACQUISITION: 65,
    SignalType.EXPANSION: 60,
    SignalType.NEW_OFFICE: 60,
    SignalType.PRODUCT_LAUNCH: 60,
    SignalType.PRICING_CHANGE: 60,
    SignalType.LEADERSHIP_CHANGE: 55,
    SignalType.HIRING: 55,
    SignalType.TECHNOLOGY_CHANGE: 50,
    SignalType.PROCUREMENT: 55,
}
DEFAULT_STRENGTH = 45


def build_diff_text(pair: SnapshotPair) -> str:
    """Describe what changed, in the least text that still carries the change.

    A sentence-level diff rather than a character one: the model needs to read
    the new claims, and a character diff of rendered text is unreadable noise.
    """
    current, previous = pair.current, pair.previous
    if previous is None:
        return ""

    added_headings = [h for h in (current.headings or []) if h not in (previous.headings or [])]
    removed_headings = [h for h in (previous.headings or []) if h not in (current.headings or [])]

    before_paths = {normalise_path(link) for link in previous.internal_links or []}
    after_paths = {normalise_path(link) for link in current.internal_links or []}
    new_paths = sorted(after_paths - before_paths)

    seen = set(sentences(previous.text))
    new_sentences = [line for line in sentences(current.text) if line not in seen]

    parts = [f"URL: {pair.url}"]
    if current.title and current.title != previous.title:
        parts.append(f"Page title was: {previous.title}")
        parts.append(f"Page title is now: {current.title}")
    if added_headings:
        parts.append("New headings: " + " | ".join(str(h) for h in added_headings[:15]))
    if removed_headings:
        parts.append("Removed headings: " + " | ".join(str(h) for h in removed_headings[:15]))
    if new_paths:
        parts.append("New pages linked: " + ", ".join(new_paths[:15]))
    if new_sentences:
        parts.append("New text since the previous crawl:")
        parts.extend(new_sentences[:MAX_NEW_SENTENCES])

    return "\n".join(parts)[:MAX_DIFF_CHARS]


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def is_grounded(interpreted: Any, diff_text: str) -> bool:
    """True when at least one evidence quote appears in the supplied diff.

    Whitespace-insensitive, because a model reproducing a quote across a line
    break is quoting faithfully; anything looser than that would defeat the
    purpose of checking at all.
    """
    haystack = _normalise(diff_text)
    for item in interpreted.evidence or []:
        quote = _normalise(getattr(item, "quote", ""))
        if len(quote) >= MIN_QUOTE_CHARS and quote in haystack:
            return True
    return False


def interpret_website_change(
    *,
    company: Any,
    provider: Any = None,
    requested_by: Any = None,
    now: Any = None,
) -> list[LeadSignal]:
    """Ask a model what a company's website change means, and store the answer.

    Returns the signals that survived the grounding check, which may be none.
    """
    moment = now or timezone.now()
    context = build_context(company, now=moment)
    pair = context.homepage()

    if pair is None or not pair.has_history:
        return []
    if pair.current.content_hash and pair.current.content_hash == pair.previous.content_hash:
        return []

    diff_text = build_diff_text(pair)
    if len(_normalise(diff_text)) < 80:
        # Nothing substantive to interpret. Paying for this call would buy an
        # expensive "nothing happened".
        return []

    try:
        result = run_prompt(
            organization=company.organization,
            prompt="signal_interpretation",
            user_content=diff_text,
            feature="signal_interpretation",
            subject=company,
            requested_by=requested_by,
            provider=provider,
        )
    except Exception as exc:
        logger.warning(
            "signal_interpretation_failed",
            company_id=str(company.public_id),
            error=str(exc)[:200],
        )
        return []

    stored: list[LeadSignal] = []
    discarded = 0

    for interpreted in result.output.signals:
        if not is_grounded(interpreted, diff_text):
            # The model asserted something the diff does not support. Dropped
            # rather than stored with low confidence: an ungrounded claim is
            # not a weak signal, it is a wrong one.
            discarded += 1
            logger.info(
                "signal_interpretation_discarded",
                company_id=str(company.public_id),
                signal_type=str(interpreted.type),
                reason="no evidence quote found in the diff",
            )
            continue

        detected = DetectedSignal(
            signal_type=str(interpreted.type),
            title=interpreted.title[:300],
            description=interpreted.why_it_matters,
            fingerprint=fingerprint_of(
                DETECTOR_NAME, interpreted.type, pair.current.content_hash or interpreted.title
            ),
            detector=DETECTOR_NAME,
            strength=STRENGTH_BY_TYPE.get(str(interpreted.type), DEFAULT_STRENGTH),
            confidence=str(interpreted.confidence or Confidence.MEDIUM),
            evidence=[
                evidence_entry(
                    claim=item.claim or interpreted.title,
                    source_type=item.source_type or "website_page",
                    source_url=item.source_url or pair.url,
                    quote=item.quote,
                    retrieved_at=pair.current.fetched_at,
                    confidence=str(item.confidence or Confidence.MEDIUM),
                )
                for item in (interpreted.evidence or [])
            ],
            source="ai_interpretation",
            source_url=pair.url,
            source_snapshot_id=pair.current.pk,
        )
        signal, _ = record_signal(company=company, detected=detected, now=moment)
        stored.append(signal)

    logger.info(
        "signal_interpretation_complete",
        company_id=str(company.public_id),
        stored=len(stored),
        discarded=discarded,
        prompt=result.job.prompt_pin,
    )
    return stored


__all__ = [
    "DETECTOR_NAME",
    "build_diff_text",
    "interpret_website_change",
    "is_grounded",
]
