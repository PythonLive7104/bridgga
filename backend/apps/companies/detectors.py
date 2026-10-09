"""Signal detectors (PRD section 33).

Each detector reads a company's stored evidence and returns ``DetectedSignal``
values. They never touch the database: writing, deduplicating and refreshing
belong to ``apps.companies.signal_engine``, and keeping detection pure means a
detector can be tested against a fixture in a millisecond with no tenant, no
migration and no network.

Three rules shape all of them.

**Deterministic first, model second.** Diffing two strings does not need a
language model, and paying for one per prospect per day would be indefensible
at any volume. Every detector here is free and repeatable. The one AI-backed
interpreter lives in ``apps.companies.signal_agents`` and runs only where
deterministic detection has already found a change it cannot characterise.

**No evidence, no signal.** Every ``DetectedSignal`` carries at least one
``Evidence`` entry naming the page it came from, usually with a verbatim
quote. Section 58 requires that the platform can produce the source behind any
claim, and a signal nobody can check is worse than no signal: it spends the
customer's credibility in a conversation with a real buyer.

**Silence is a valid answer.** A detector that always finds something is a
detector whose output means nothing. A careers page with no open roles, a
homepage whose only change is a rotating testimonial, and a pricing page that
reads the same both times all produce no signal at all.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from urllib.parse import urlsplit

from django.utils import timezone

from apps.ai.schemas import Confidence, Evidence, SignalType

# --------------------------------------------------------------------------- #
# What a detector returns
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class DetectedSignal:
    """One detection, before it is reconciled with what is already stored."""

    signal_type: str
    title: str
    #: Identity of the observation. See ``LeadSignal.fingerprint``: this is
    #: what makes re-running a detector idempotent.
    fingerprint: str
    detector: str = ""
    description: str = ""
    strength: int = 50
    confidence: str = Confidence.MEDIUM
    occurred_at: datetime | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    source: str = ""
    source_url: str = ""
    source_event_id: int | None = None
    source_snapshot_id: int | None = None
    #: True when re-detecting this observation means it is *still true*, so
    #: seeing it again should extend its life.
    #:
    #: It matters more than it looks. An open role that is still listed next
    #: week is still an open role, so the hiring signal should stay live. But
    #: "we raised $4M" sits on an About page indefinitely, and renewing that
    #: on every crawl would make a round from 2023 permanently fresh --
    #: exactly the staleness failure section 33 exists to prevent. Only the
    #: detector knows which kind of claim it is making, so only it can say.
    renewable: bool = False


def fingerprint_of(*parts: Any) -> str:
    """Stable hash of whatever identifies an observation.

    Order-insensitive within each part because a careers page listing the same
    three roles in a different order is the same observation, and a detector
    that treated it as new would re-signal on every shuffle.
    """
    pieces: list[str] = []
    for part in parts:
        if isinstance(part, (list, tuple, set, frozenset)):
            pieces.append("|".join(sorted(str(item).strip().lower() for item in part)))
        else:
            pieces.append(str(part).strip().lower())
    return hashlib.sha256("::".join(pieces).encode("utf-8")).hexdigest()


def evidence_entry(
    *,
    claim: str,
    source_type: str,
    source_url: str = "",
    quote: str = "",
    retrieved_at: datetime | None = None,
    confidence: str = Confidence.MEDIUM,
) -> dict[str, Any]:
    """Build an evidence entry in the same shape the agents produce.

    Routed through the Pydantic model deliberately: a detector and an agent
    both end up in ``LeadSignal.evidence``, and the interface that renders it
    should not have to know which wrote the row.
    """
    return Evidence(
        claim=claim[:500],
        source_type=source_type,
        source_url=source_url[:2048],
        quote=quote[:500],
        retrieved_at=retrieved_at,
        confidence=Confidence(confidence),
    ).model_dump(mode="json")


# --------------------------------------------------------------------------- #
# What a detector reads
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class SnapshotPair:
    """The latest fetch of one page, and the one before it.

    ``previous`` is None on a first crawl, which is why every diffing detector
    has to answer "no signal" rather than "everything is new". A company whose
    site we have seen once has not changed anything.
    """

    current: Any
    previous: Any = None

    @property
    def url(self) -> str:
        return self.current.final_url or self.current.requested_url

    @property
    def has_history(self) -> bool:
        return self.previous is not None


@dataclass(slots=True)
class DetectionContext:
    """Everything the detectors are allowed to look at, gathered once."""

    company: Any
    pages: list[SnapshotPair] = field(default_factory=list)
    technologies: list[Any] = field(default_factory=list)
    events: list[Any] = field(default_factory=list)
    now: datetime = field(default_factory=timezone.now)

    def page_matching(self, *hints: str) -> SnapshotPair | None:
        """The first page whose path looks like one of ``hints``."""
        for pair in self.pages:
            path = urlsplit(pair.url).path.lower()
            if any(hint in path for hint in hints):
                return pair
        return None

    def homepage(self) -> SnapshotPair | None:
        for pair in self.pages:
            if urlsplit(pair.url).path.strip("/") == "":
                return pair
        return self.pages[0] if self.pages else None


class Detector(Protocol):
    """One thing worth watching for."""

    name: str

    def detect(self, context: DetectionContext) -> list[DetectedSignal]: ...


# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")

#: Currency amounts, Africa-first: the launch markets' symbols are listed
#: alongside the usual ones, because a Nigerian pricing page states naira and
#: a detector that only knew the dollar would read it as having no prices.
_AMOUNT = re.compile(
    r"(?:US\$|\$|€|£|₦|R|KSh|Ksh|GH₵|₵|EGP|ZAR|NGN|KES|GHS|USD|EUR|GBP)\s?"
    r"\d[\d,]*(?:\.\d+)?"
    # The scale suffix must end on a word boundary. Without it, "KSh 6,500
    # monthly" reads the "m" of "monthly" as millions and a 6,500-shilling
    # plan becomes a 6.5-billion one -- which then looks like a price change
    # the next time the page says the same thing a different way.
    r"(?:\s?(?:k|m|bn|b|million|billion|thousand)\b)?",
    re.IGNORECASE,
)

#: Completed funding, not aspirational funding. The verb list is finite and
#: deliberately excludes the bare infinitive: a marketing page offering to
#: "help you raise $1M" is not a funding round, and "raise" would match it.
_FUNDING_VERB = re.compile(
    r"\b(raised|raises|secured|secures|closed|closes|landed|lands|"
    r"announced|announces|completed|completes|received|receives)\b",
    re.IGNORECASE,
)
_FUNDING_NOUN = re.compile(
    r"\b(pre-seed|seed(?:\s+round)?|series\s+[a-f]\b|funding|investment|"
    r"round|venture\s+capital|valuation)\b",
    re.IGNORECASE,
)
#: Money that is not funding. Revenue, savings and transaction volume are all
#: stated in the same shape and are not a reason to call anybody.
_NOT_FUNDING = re.compile(
    r"\b(revenue|arr|mrr|turnover|savings?|saved|save|processed|transaction|"
    r"gmv|payroll|salary|discount|refund|cashback|worth of goods)\b",
    re.IGNORECASE,
)

#: Words that make a heading look like a job title rather than page furniture.
_ROLE_WORDS = (
    "manager",
    "engineer",
    "developer",
    "officer",
    "analyst",
    "supervisor",
    "driver",
    "accountant",
    "designer",
    "director",
    "specialist",
    "coordinator",
    "executive",
    "representative",
    "technician",
    "operator",
    "consultant",
    "administrator",
    "assistant",
    "head of",
    "lead ",
    "intern",
    "architect",
    "controller",
    "nurse",
    "agronomist",
    "dispatcher",
)

#: Headings on a careers page that are not roles.
_NOT_A_ROLE = (
    "open roles",
    "open positions",
    "current openings",
    "join us",
    "why join",
    "our culture",
    "benefits",
    "perks",
    "life at",
    "careers",
    "vacancies",
    "we are hiring",
    "no open",
    "apply",
    "equal opportunity",
    "values",
)


def sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_SPLIT.split(text or "") if part.strip()]


def normalise_path(url: str) -> str:
    """A page's identity for diffing: path only, no query, no trailing slash."""
    parts = urlsplit(url)
    path = (parts.path or "/").rstrip("/").lower()
    return path or "/"


def looks_like_a_role(heading: str) -> bool:
    text = heading.strip().lower()
    if not text or len(text) > 90:
        return False
    if any(phrase in text for phrase in _NOT_A_ROLE):
        return False
    return any(word in text for word in _ROLE_WORDS)


def role_from_job_url(url: str) -> str:
    """Turn ``/careers/senior-fleet-manager`` into ``Senior Fleet Manager``."""
    slug = normalise_path(url).rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"[-_]+", " ", slug).strip()
    slug = re.sub(r"\b\d{3,}\b", "", slug).strip()
    return slug.title() if len(slug) > 3 else ""


def prices_in(text: str) -> list[str]:
    """Distinct currency amounts in a page, normalised for comparison."""
    found = {re.sub(r"\s+", "", m.group(0)).upper() for m in _AMOUNT.finditer(text or "")}
    return sorted(found)


# --------------------------------------------------------------------------- #
# Detectors
# --------------------------------------------------------------------------- #


class HiringPageDetector:
    """Open roles on a company's own careers page (section 33, hiring).

    The single most useful signal in the set, because what a company is hiring
    for says what it is about to spend money on. A careers page with no roles
    on it produces nothing: the page existing is not news.
    """

    name = "hiring_page"
    MAX_EVIDENCE = 3

    def detect(self, context: DetectionContext) -> list[DetectedSignal]:
        pair = context.page_matching("career", "job", "vacanc", "hiring", "work-with-us")
        if pair is None:
            return []

        page = pair.current
        roles = self._roles(page)
        if not roles:
            return []

        evidence = [
            evidence_entry(
                claim=f"{page.title or 'The careers page'} lists an open role: {role}",
                source_type="careers_page",
                source_url=pair.url,
                quote=role,
                retrieved_at=page.fetched_at,
                confidence=Confidence.HIGH,
            )
            for role in roles[: self.MAX_EVIDENCE]
        ]

        listed = ", ".join(roles[:3])
        more = f" and {len(roles) - 3} more" if len(roles) > 3 else ""

        return [
            DetectedSignal(
                signal_type=SignalType.HIRING,
                title=f"Hiring: {listed}{more}",
                description=(
                    f"{len(roles)} open role(s) on the careers page. What a company "
                    "hires for is what it is about to spend on."
                ),
                fingerprint=fingerprint_of("hiring", roles),
                detector=self.name,
                # Each additional role is more evidence of the same thing, so
                # the count raises confidence quickly and then flattens.
                strength=min(45 + 12 * len(roles), 90),
                confidence=Confidence.HIGH if len(roles) > 1 else Confidence.MEDIUM,
                # A role still on the page next week is still open.
                renewable=True,
                evidence=evidence,
                source="website_crawl",
                source_url=pair.url,
                source_snapshot_id=page.pk,
            )
        ]

    @staticmethod
    def _roles(page: Any) -> list[str]:
        roles: list[str] = []

        for heading in page.headings or []:
            if looks_like_a_role(str(heading)):
                roles.append(str(heading).strip())

        for link in page.internal_links or []:
            path = normalise_path(str(link))
            # A link under /jobs/<slug> or /careers/<slug> is a posting; the
            # index page itself is not.
            if not re.search(r"/(jobs?|careers?|vacanc(?:y|ies)|positions?)/[^/]+$", path):
                continue
            title = role_from_job_url(str(link))
            if title:
                roles.append(title)

        seen: set[str] = set()
        unique: list[str] = []
        for role in roles:
            key = role.lower()
            if key not in seen:
                seen.add(key)
                unique.append(role)
        return unique[:20]


class FundingNewsDetector:
    """A completed funding round stated on the company's own site.

    **Known limitation, stated rather than hidden.** This reads prose, so it
    cannot date the round: a page that says "we raised $4M" says nothing about
    when, and the signal is therefore dated from when it was read. Confidence
    is capped at medium for that reason and the matched sentence is quoted so
    a human can see the claim before using it. A news or funding-database
    integration is the right source for this signal, and when one exists it
    will arrive as a ``CompanyEvent`` and be picked up with a real date by
    ``EventSignalDetector`` instead.
    """

    name = "funding_text"
    MAX_SIGNALS = 2

    def detect(self, context: DetectionContext) -> list[DetectedSignal]:
        signals: list[DetectedSignal] = []

        for pair in context.pages:
            page = pair.current
            for sentence in sentences(page.text):
                if len(signals) >= self.MAX_SIGNALS:
                    return signals
                if not self._is_funding(sentence):
                    continue

                amount = _AMOUNT.search(sentence)
                signals.append(
                    DetectedSignal(
                        signal_type=SignalType.FUNDING,
                        title=f"Funding mentioned: {amount.group(0).strip() if amount else ''}",
                        description=sentence[:500],
                        fingerprint=fingerprint_of(
                            "funding", re.sub(r"\s+", " ", sentence.lower())
                        ),
                        detector=self.name,
                        strength=70,
                        # Capped at medium: see the class docstring. The page
                        # states the round, not its date.
                        confidence=Confidence.MEDIUM,
                        evidence=[
                            evidence_entry(
                                claim="The site states a completed funding round.",
                                source_type="website_page",
                                source_url=pair.url,
                                quote=sentence,
                                retrieved_at=page.fetched_at,
                            )
                        ],
                        source="website_crawl",
                        source_url=pair.url,
                        source_snapshot_id=page.pk,
                    )
                )

        return signals

    @staticmethod
    def _is_funding(sentence: str) -> bool:
        if not _AMOUNT.search(sentence):
            return False
        if _NOT_FUNDING.search(sentence):
            return False
        # A verb alone is too loose ("announced $5M in savings") and a noun
        # alone too loose the other way ("our seed customers pay $50"), so the
        # sentence has to carry both.
        return bool(_FUNDING_VERB.search(sentence) and _FUNDING_NOUN.search(sentence))


class WebsiteChangeDetector:
    """The homepage changed in a way that is more than cosmetic.

    The weakest signal in the set and priced accordingly. It earns its place
    by being the trigger for the AI interpreter, which can say *what* changed;
    on its own it says only that something did.
    """

    name = "website_diff"
    #: Below this, a text-length change is a rotating testimonial or a date
    #: stamp rather than news.
    MIN_TEXT_DELTA = 0.05

    def detect(self, context: DetectionContext) -> list[DetectedSignal]:
        pair = context.homepage()
        if pair is None or not pair.has_history:
            return []

        current, previous = pair.current, pair.previous
        if current.content_hash and current.content_hash == previous.content_hash:
            return []

        added = [h for h in (current.headings or []) if h not in (previous.headings or [])]
        removed = [h for h in (previous.headings or []) if h not in (current.headings or [])]

        before, after = len(previous.text or ""), len(current.text or "")
        delta = abs(after - before) / max(before, after, 1)

        if not added and not removed and delta < self.MIN_TEXT_DELTA:
            # The bytes differ but nothing a buyer would notice does.
            return []

        evidence = [
            evidence_entry(
                claim=f"New section on the homepage: {heading}",
                source_type="website_page",
                source_url=pair.url,
                quote=str(heading),
                retrieved_at=current.fetched_at,
            )
            for heading in added[:3]
        ]
        if removed:
            evidence.append(
                evidence_entry(
                    claim="Sections removed from the homepage: " + "; ".join(removed[:3]),
                    source_type="website_page",
                    source_url=pair.url,
                    retrieved_at=current.fetched_at,
                    confidence=Confidence.LOW,
                )
            )
        if not evidence:
            evidence = [
                evidence_entry(
                    claim=f"Homepage text changed by {delta:.0%} since the last crawl.",
                    source_type="website_page",
                    source_url=pair.url,
                    retrieved_at=current.fetched_at,
                    confidence=Confidence.LOW,
                )
            ]

        return [
            DetectedSignal(
                signal_type=SignalType.WEBSITE_CHANGE,
                title=(
                    f"Homepage changed: {added[0]}"
                    if added
                    else f"Homepage content changed by {delta:.0%}"
                ),
                description="; ".join(added[:5]) or f"{len(removed)} section(s) removed",
                fingerprint=fingerprint_of("website_change", current.content_hash or after),
                detector=self.name,
                strength=min(30 + 8 * (len(added) + len(removed)), 60),
                confidence=Confidence.MEDIUM if added else Confidence.LOW,
                evidence=evidence,
                source="website_crawl",
                source_url=pair.url,
                source_snapshot_id=current.pk,
            )
        ]


class NewPagesDetector:
    """Pages that appeared in the site's navigation since the last crawl.

    A new /integrations or /enterprise page is a roadmap announcement nobody
    sent a press release about.
    """

    name = "new_pages"
    MAX_EVIDENCE = 5

    def detect(self, context: DetectionContext) -> list[DetectedSignal]:
        pair = context.homepage()
        if pair is None or not pair.has_history:
            return []

        before = {normalise_path(link) for link in pair.previous.internal_links or []}
        after = {normalise_path(link) for link in pair.current.internal_links or []}
        new = sorted(after - before)

        if not new:
            return []

        evidence = [
            evidence_entry(
                claim=f"New page linked from the homepage: {path}",
                source_type="website_page",
                source_url=pair.url,
                quote=path,
                retrieved_at=pair.current.fetched_at,
            )
            for path in new[: self.MAX_EVIDENCE]
        ]

        return [
            DetectedSignal(
                signal_type=SignalType.NEW_PAGES,
                title=f"{len(new)} new page(s): {', '.join(new[:3])}",
                description="New paths in the site navigation: " + ", ".join(new[:10]),
                fingerprint=fingerprint_of("new_pages", new),
                detector=self.name,
                strength=min(35 + 8 * len(new), 75),
                confidence=Confidence.HIGH,
                evidence=evidence,
                source="website_crawl",
                source_url=pair.url,
                source_snapshot_id=pair.current.pk,
            )
        ]


class PricingChangeDetector:
    """The published prices on a pricing page are not what they were.

    One of the strongest signals available, and one of the few that is
    unambiguous: the numbers either match or they do not. A company that has
    just repriced is a company thinking about its revenue model.
    """

    name = "pricing_change"

    def detect(self, context: DetectionContext) -> list[DetectedSignal]:
        pair = context.page_matching("pricing", "plans", "price", "packages")
        if pair is None or not pair.has_history:
            return []

        after = prices_in(pair.current.text)
        before = prices_in(pair.previous.text)

        if after == before:
            return []
        if not after:
            # Prices came down off the page. That is a change, but "contact us"
            # replacing a price list is a different signal from a repricing and
            # this detector should not claim to have read numbers it did not.
            return []

        first_publication = not before
        added = [price for price in after if price not in before]
        removed = [price for price in before if price not in after]

        evidence = [
            evidence_entry(
                claim=(
                    "Pricing page now shows: " + ", ".join(added[:5])
                    if added
                    else "The pricing page changed."
                ),
                source_type="pricing_page",
                source_url=pair.url,
                quote=self._quote_for(pair.current.text, added),
                retrieved_at=pair.current.fetched_at,
                confidence=Confidence.HIGH,
            )
        ]
        if removed:
            evidence.append(
                evidence_entry(
                    claim="Prices no longer shown: " + ", ".join(removed[:5]),
                    source_type="pricing_page",
                    source_url=pair.url,
                    quote=self._quote_for(pair.previous.text, removed),
                    retrieved_at=pair.previous.fetched_at,
                    confidence=Confidence.HIGH,
                )
            )

        return [
            DetectedSignal(
                signal_type=SignalType.PRICING_CHANGE,
                title=(
                    f"Pricing published: {', '.join(after[:3])}"
                    if first_publication
                    else f"Pricing changed: {', '.join(removed[:2]) or '—'} "
                    f"to {', '.join(added[:2]) or '—'}"
                ),
                description=(
                    f"Published prices were [{', '.join(before) or 'none'}] "
                    f"and are now [{', '.join(after)}]."
                ),
                fingerprint=fingerprint_of("pricing", after),
                detector=self.name,
                strength=65 if first_publication else 75,
                confidence=Confidence.HIGH,
                evidence=evidence,
                source="website_crawl",
                source_url=pair.url,
                source_snapshot_id=pair.current.pk,
            )
        ]

    @staticmethod
    def _quote_for(text: str, prices: list[str]) -> str:
        """The sentence a changed price appears in, so the claim is checkable."""
        if not prices:
            return ""
        needle = re.sub(r"\s+", "", prices[0]).upper()
        for sentence in sentences(text):
            if needle in re.sub(r"\s+", "", sentence).upper():
                return sentence
        return ""


class TechnologyChangeDetector:
    """A technology adopted or dropped (section 33, technology changes).

    Reads ``CompanyTechnology``, where ``first_seen`` and ``last_seen`` already
    carry the dates -- which is what that model's docstring said they were for.
    """

    name = "technology_change"
    MAX_SIGNALS = 5

    def detect(self, context: DetectionContext) -> list[DetectedSignal]:
        from apps.companies.signal_models import ttl_days_for

        window = ttl_days_for(SignalType.TECHNOLOGY_CHANGE)
        cutoff = context.now - timezone.timedelta(days=window)
        signals: list[DetectedSignal] = []

        for technology in context.technologies:
            if len(signals) >= self.MAX_SIGNALS:
                break

            adopted = (
                technology.is_current
                and technology.first_seen is not None
                and technology.first_seen >= cutoff
            )
            dropped = (
                not technology.is_current
                and technology.last_seen is not None
                and technology.last_seen >= cutoff
            )
            if not (adopted or dropped):
                continue

            verb = "started using" if adopted else "stopped using"
            when = technology.first_seen if adopted else technology.last_seen

            signals.append(
                DetectedSignal(
                    signal_type=SignalType.TECHNOLOGY_CHANGE,
                    title=f"{technology.name}: {verb}",
                    description=(
                        f"{technology.name}"
                        + (f" ({technology.category})" if technology.category else "")
                        + f" was {verb.replace('using', 'in use')} as of "
                        + when.date().isoformat()
                    ),
                    fingerprint=fingerprint_of(
                        "technology", technology.name, "adopted" if adopted else "dropped"
                    ),
                    detector=self.name,
                    strength=55 if adopted else 50,
                    confidence=technology.confidence or Confidence.MEDIUM,
                    occurred_at=when,
                    evidence=[
                        evidence_entry(
                            claim=f"{technology.name} {verb} at this company.",
                            source_type=technology.source or "technology_detection",
                            source_url=technology.source_url,
                            retrieved_at=when,
                            confidence=technology.confidence or Confidence.MEDIUM,
                        )
                    ],
                    source=technology.source or "technology_detection",
                    source_url=technology.source_url,
                )
            )

        return signals


class EventSignalDetector:
    """Turns recorded company events into signals.

    The bridge between the two models: an event is a dated fact, and this is
    what decides that a recent one is also a reason to call. It is the path by
    which anything that arrives as news -- an integration, an importer, a
    person typing it in -- becomes a signal without that source needing to
    know the signal engine exists.
    """

    name = "company_event"

    #: Not every kind of news is worth the same call. Funding and acquisition
    #: move budgets; a social post does not.
    STRENGTH_BY_TYPE: dict[str, int] = {
        SignalType.FUNDING: 80,
        SignalType.ACQUISITION: 80,
        SignalType.EXPANSION: 70,
        SignalType.NEW_OFFICE: 65,
        SignalType.PROCUREMENT: 65,
        SignalType.LEADERSHIP_CHANGE: 60,
        SignalType.PRODUCT_LAUNCH: 60,
    }

    def detect(self, context: DetectionContext) -> list[DetectedSignal]:
        from apps.companies.signal_models import ttl_days_for

        signals: list[DetectedSignal] = []

        for event in context.events:
            occurred = event.occurred_at or event.collected_at or event.created_at
            # An event older than its signal window is history. Recording it
            # would create a signal that is expired on arrival.
            if occurred < context.now - timezone.timedelta(days=ttl_days_for(event.event_type)):
                continue

            signals.append(
                DetectedSignal(
                    signal_type=event.event_type,
                    title=event.title[:300],
                    description=event.description,
                    fingerprint=fingerprint_of("event", event.public_id),
                    detector=self.name,
                    strength=self.STRENGTH_BY_TYPE.get(event.event_type, 55),
                    confidence=event.confidence or Confidence.MEDIUM,
                    occurred_at=occurred,
                    evidence=[
                        evidence_entry(
                            claim=event.title,
                            source_type=event.source or "company_event",
                            source_url=event.url or event.source_url,
                            quote=event.description[:300],
                            retrieved_at=event.collected_at or event.created_at,
                            confidence=event.confidence or Confidence.MEDIUM,
                        )
                    ],
                    source=event.source or "company_event",
                    source_url=event.url or event.source_url,
                    source_event_id=event.pk,
                )
            )

        return signals


#: The detectors that run, in the order they run. Deterministic and free, all
#: of them -- the AI interpreter is invoked separately and by choice.
DETECTORS: tuple[Detector, ...] = (
    EventSignalDetector(),
    HiringPageDetector(),
    FundingNewsDetector(),
    PricingChangeDetector(),
    TechnologyChangeDetector(),
    NewPagesDetector(),
    WebsiteChangeDetector(),
)


def detector_named(name: str) -> Detector:
    for detector in DETECTORS:
        if detector.name == name:
            return detector
    raise KeyError(f"No detector named {name!r}")


__all__ = [
    "DETECTORS",
    "DetectedSignal",
    "DetectionContext",
    "Detector",
    "EventSignalDetector",
    "FundingNewsDetector",
    "HiringPageDetector",
    "NewPagesDetector",
    "PricingChangeDetector",
    "SnapshotPair",
    "TechnologyChangeDetector",
    "WebsiteChangeDetector",
    "detector_named",
    "evidence_entry",
    "fingerprint_of",
    "normalise_path",
    "prices_in",
]
