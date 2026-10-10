"""The opportunity score (PRD sections 32 and 119).

Section 32 asks for a number out of 100 from eight weighted components, and
then for one more thing: "The platform must explain the score." Section 119
says what explaining means here -- recommendation, reason, evidence,
confidence, editable assumptions.

The hard part is not the arithmetic. It is that most of what the components
need does not exist yet for most prospects, and the obvious handling of that
produces a number that is confidently wrong.

**An unmeasured component is not a zero.** A company nobody has crawled has no
signals, and scoring its buying intent as 0/20 says "we looked and there is no
intent" when the truth is "we have not looked". Engagement data does not exist
at all until campaigns ship, so every prospect in the product would be capped
at 90 for a whole phase. So a scorer returns ``None`` for "cannot assess", its
weight is redistributed across the components that *can* be assessed, and the
score means "82% of what we were able to judge" rather than "82% of
everything".

**That redistribution is what confidence is for.** A score of 82 from three of
eight components is not the same claim as 82 from all eight, and the only
honest way to show both is the number plus its coverage. ``confidence`` is the
share of the configured weight that was actually assessed, discounted when the
underlying company record is stale (section 61). Section 119's worked example
shows a percentage next to the recommendation for exactly this reason.

**Every component states its evidence.** A score a salesperson cannot
interrogate is a score they will either ignore or over-trust, and both are
expensive. The payload carries the quotes and source URLs from the signals
that moved the number, so "high opportunity" can be checked rather than
believed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog
from django.utils import timezone

from apps.ai.schemas import SignalType
from apps.common.models import UNSENDABLE_CONTACT_STATUSES, ContactStatus
from apps.leads.scoring_models import (
    DEFAULT_WEIGHTS,
    ScoreComponent,
    band_for,
    weights_for,
)

logger = structlog.get_logger(__name__)

#: Signals that suggest a company is in a buying posture. Funding and
#: procurement are the obvious ones; a leadership change belongs here because
#: a new owner of a function reviews the tools that function uses, which is
#: ordinary sales knowledge rather than a guess.
INTENT_SIGNALS = frozenset(
    {
        SignalType.FUNDING,
        SignalType.PROCUREMENT,
        SignalType.PRICING_CHANGE,
        SignalType.PRODUCT_LAUNCH,
        SignalType.ADVERTISING,
        SignalType.LEADERSHIP_CHANGE,
    }
)

#: Signals that suggest a company is getting bigger. Distinct from intent:
#: growth says they will need more of something, intent says they are shopping.
GROWTH_SIGNALS = frozenset(
    {
        SignalType.HIRING,
        SignalType.EXPANSION,
        SignalType.NEW_OFFICE,
        SignalType.ACQUISITION,
        SignalType.NEW_PAGES,
        SignalType.CONTENT_GROWTH,
        SignalType.SOCIAL_ACTIVITY,
    }
)

#: What a contact's email status is worth. ``unknown`` sits at half: an
#: unverified address is a real contact route, just not a reliable one.
EMAIL_STATUS_VALUE: dict[str, float] = {
    ContactStatus.VERIFIED: 1.0,
    ContactStatus.UNKNOWN: 0.5,
    ContactStatus.RISKY: 0.25,
}

#: Multiplier applied to confidence when the company record is itself stale.
#: Not applied to the score: the components were assessed, and how old the
#: underlying facts are is a statement about certainty, not about fit.
STALE_CONFIDENCE_FACTOR = 0.75


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class ComponentScore:
    """One of section 32's eight factors, judged.

    ``value`` is ``None`` when the component could not be assessed at all --
    which is different from 0.0, meaning "assessed, and it scores nothing".
    The distinction is the point of this class.
    """

    component: str
    weight: int
    value: float | None
    reason: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return self.value is not None

    @property
    def label(self) -> str:
        return str(ScoreComponent(self.component).label)

    def as_dict(self, *, effective_weight: float = 0.0) -> dict[str, Any]:
        return {
            "component": self.component,
            "label": self.label,
            "weight": self.weight,
            # What it actually counted for once unassessable components were
            # dropped. The difference between the two numbers is the
            # explanation people most often want and are least often given.
            "effective_weight": round(effective_weight, 1),
            "value": None if self.value is None else round(self.value, 3),
            "points": None if self.value is None else round(self.value * effective_weight, 1),
            "available": self.available,
            "reason": self.reason,
            "evidence": self.evidence,
            "detail": self.detail,
        }


@dataclass(slots=True)
class ScoreResult:
    score: int
    band: str
    confidence: int
    coverage: float
    components: list[ComponentScore]
    weights: dict[str, int]
    assumptions: dict[str, Any] = field(default_factory=dict)
    scored_at: datetime | None = None

    @property
    def assessed(self) -> list[ComponentScore]:
        return [component for component in self.components if component.available]

    @property
    def missing(self) -> list[ComponentScore]:
        return [component for component in self.components if not component.available]

    @property
    def recommendation(self) -> str:
        return {
            "high": "High opportunity",
            "medium": "Medium opportunity",
            "low": "Low opportunity",
        }[self.band]

    def effective_weight(self, component: ComponentScore) -> float:
        total = sum(item.weight for item in self.assessed)
        if not total or not component.available:
            return 0.0
        return component.weight / total * 100

    def reason(self) -> str:
        """One sentence a salesperson can read without opening anything."""
        contributors = sorted(
            (c for c in self.assessed if c.value),
            key=lambda c: (c.value or 0) * c.weight,
            reverse=True,
        )
        if not contributors:
            return "Nothing assessed so far supports contacting this company."

        leading = ", ".join(c.label.lower() for c in contributors[:2])
        sentence = f"{self.recommendation.lower().capitalize()}, mostly on {leading}."

        if self.missing:
            unassessed = ", ".join(c.label.lower() for c in self.missing)
            sentence += f" Not assessed: {unassessed}."
        return sentence

    def evidence(self) -> list[dict[str, Any]]:
        """The supporting evidence from every component that scored."""
        collected: list[dict[str, Any]] = []
        for component in sorted(
            self.assessed, key=lambda c: (c.value or 0) * c.weight, reverse=True
        ):
            collected.extend(component.evidence)
        return collected[:12]

    def payload(self) -> dict[str, Any]:
        """The section 119 explainability object, stored and served as-is."""
        return {
            "recommendation": self.recommendation,
            "band": self.band,
            "score": self.score,
            "confidence": self.confidence,
            "coverage": round(self.coverage, 3),
            "reason": self.reason(),
            "evidence": self.evidence(),
            "components": [
                component.as_dict(effective_weight=self.effective_weight(component))
                for component in self.components
            ],
            "not_assessed": [
                {"component": c.component, "label": c.label, "reason": c.reason}
                for c in self.missing
            ],
            "assumptions": self.assumptions,
            "scored_at": (self.scored_at or timezone.now()).isoformat(),
        }


# --------------------------------------------------------------------------- #
# Context
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class ScoringContext:
    company: Any
    icp: Any = None
    signals: list[Any] = field(default_factory=list)
    technologies: list[Any] = field(default_factory=list)
    people: list[Any] = field(default_factory=list)
    selected_countries: set[str] = field(default_factory=set)
    #: True when this company has been crawled at least once. Without it,
    #: "no signals found" and "never looked" are indistinguishable, and the
    #: whole availability distinction collapses.
    examined: bool = False
    now: datetime = field(default_factory=timezone.now)

    def live_signals(self, types: frozenset[str]) -> list[Any]:
        return [
            signal
            for signal in self.signals
            if signal.signal_type in types and signal.is_active(at=self.now)
        ]

    @property
    def live_signal_types(self) -> set[str]:
        return {s.signal_type for s in self.signals if s.is_active(at=self.now)}


def build_context(company: Any, *, icp: Any = None, now: datetime | None = None) -> ScoringContext:
    from apps.companies.models import CompanyTechnology, LeadSignal
    from apps.contacts.models import Person
    from apps.intelligence.models import ICP, MarketRecommendation, WebsiteSnapshot

    moment = now or timezone.now()
    organization_id = company.organization_id

    if icp is None:
        icp = (
            ICP.all_objects.filter(organization_id=organization_id, is_active=True)
            .order_by("-created_at")
            .first()
        )

    signals = list(LeadSignal.all_objects.filter(company_id=company.pk).strongest_first()[:50])
    technologies = list(
        CompanyTechnology.all_objects.filter(company_id=company.pk, is_current=True)[:50]
    )
    people = list(
        Person.all_objects.filter(company_id=company.pk).order_by("-is_decision_maker", "id")[:25]
    )
    selected = set(
        MarketRecommendation.all_objects.filter(
            organization_id=organization_id, is_selected=True
        ).values_list("country__code", flat=True)
    )

    examined = bool(signals) or WebsiteSnapshot.all_objects.filter(company_id=company.pk).exists()

    return ScoringContext(
        company=company,
        icp=icp,
        signals=signals,
        technologies=technologies,
        people=people,
        selected_countries={code.upper() for code in selected if code},
        examined=examined,
        now=moment,
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _evidence(
    *,
    claim: str,
    source_type: str,
    source_url: str = "",
    quote: str = "",
    retrieved_at: str = "",
    confidence: str = "medium",
    signal_type: str = "",
    strength: int | None = None,
    icp_pain: str = "",
) -> dict[str, Any]:
    """One evidence entry, in the same shape whichever component produced it.

    Uniform on purpose. These entries come from five different scorers and end
    up in one list that an interface iterates over, so a key that is present
    on some entries and absent on others is a crash waiting for the first
    prospect whose top evidence came from a different component. ``signal_type``
    is always present and empty when the evidence did not come from a signal,
    which is what lets the panel group by it without defensive reads.
    """
    return {
        "claim": claim,
        "source_type": source_type,
        "source_url": source_url,
        "quote": quote,
        "retrieved_at": retrieved_at,
        "confidence": confidence,
        "signal_type": signal_type,
        "strength": strength,
        "icp_pain": icp_pain,
    }


def _evidence_from_signal(signal: Any, *, icp_pain: str = "") -> dict[str, Any]:
    """Carry a signal's own evidence through to the score's explanation.

    The first stored evidence entry, with the signal's quote and URL where it
    has them, so following the score back to a page is one click rather than
    three screens.
    """
    first = (signal.evidence or [{}])[0] if signal.evidence else {}
    return _evidence(
        claim=signal.title,
        source_type=first.get("source_type") or signal.source or "signal",
        source_url=first.get("source_url") or signal.source_url,
        quote=first.get("quote", ""),
        retrieved_at=(signal.occurred_at or signal.detected_at).isoformat(),
        confidence=signal.confidence,
        signal_type=signal.signal_type,
        strength=signal.decayed_strength(),
        icp_pain=icp_pain,
    )


def _signal_value(signals: list[Any]) -> float:
    """Turn a set of live signals into a 0-1 value.

    The strongest signal dominates and each additional one adds a little: two
    hiring posts are better evidence than one, but not twice as good, and a
    linear sum would let six weak signals outrank one funding round.
    """
    if not signals:
        return 0.0
    strengths = sorted((signal.decayed_strength() for signal in signals), reverse=True)
    value = strengths[0] / 100
    value += min(len(strengths) - 1, 2) * 0.1
    return min(round(value, 4), 1.0)


# An ICP's headcount range is free text written by a model, which separates
# the two numbers with an en dash at least as often as with a hyphen. Built
# from its code point rather than typed, so neither a reader nor a linter has
# to guess which of the two look-alike characters is in the source.
_EN_DASH = chr(0x2013)
_RANGE = re.compile(rf"(\d[\d,]*)\s*(?:-|to|{_EN_DASH})\s*(\d[\d,]*)|(\d[\d,]*)\s*\+")


def parse_headcount_range(value: str) -> tuple[int, int] | None:
    """Read "25-250", "51-200" or "1000+" as a numeric interval.

    The ICP's range is written by a model in free text and the company's comes
    from a fixed band, so neither matching them as strings nor assuming a
    shared vocabulary works.
    """
    match = _RANGE.search(value or "")
    if not match:
        return None
    low, high, open_ended = match.groups()
    if open_ended:
        return int(open_ended.replace(",", "")), 10**9
    return int(low.replace(",", "")), int(high.replace(",", ""))


def ranges_overlap(left: str, right: str) -> bool | None:
    """Whether two headcount ranges intersect. None when either is unreadable."""
    first, second = parse_headcount_range(left), parse_headcount_range(right)
    if first is None or second is None:
        return None
    return first[0] <= second[1] and second[0] <= first[1]


#: Words that carry no meaning when comparing two industry descriptions.
_NOISE_WORDS = frozenset(
    {
        "and",
        "the",
        "for",
        "with",
        "their",
        "that",
        "who",
        "run",
        "running",
        "inhouse",
        "house",
        "team",
        "teams",
        "business",
        "businesses",
        "company",
        "companies",
        "service",
        "services",
        "solution",
        "solutions",
    }
)


def _singular(word: str) -> str:
    """Crude singularisation. Enough to make "agency" and "agencies" meet."""
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("ses", "xes", "zes", "ches", "shes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def significant_words(text: str) -> set[str]:
    """The words in a description that actually carry its meaning."""
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {_singular(word) for word in words if len(word) > 2} - _NOISE_WORDS


#: How much of the shorter description must be present in the longer one for
#: two industries to count as the same. A judgement: lower starts matching any
#: two things that share the word "agency".
MATCH_THRESHOLD = 0.6


def _matches_any(value: str, candidates: list[str]) -> str:
    """The first candidate that describes the same thing as ``value``, or "".

    Compared word by word rather than as substrings, which is the fix for a
    failure found on real data: an ICP reading "Digital marketing agencies
    (paid media/performance)" scored 0.00 against a company recorded as
    "Digital marketing agency" -- an exact conceptual match, defeated by a
    plural and a parenthetical. ICP fit is a quarter of the opportunity
    score, so that one `s` quietly took 25 points off every prospect the
    customer most wanted to see.

    A match is a subset of significant words, or enough overlap to be the
    same subject. Still deliberately blunt: the customer can edit the ICP,
    and a matcher that tried to be clever would be wrong in ways nobody could
    predict from the text in front of them.
    """
    target = significant_words(value)
    if not target:
        return ""

    for candidate in candidates:
        words = significant_words(str(candidate))
        if not words:
            continue
        shared = target & words
        if not shared:
            continue
        if shared == target or shared == words:
            return str(candidate)
        if len(shared) / min(len(target), len(words)) >= MATCH_THRESHOLD:
            return str(candidate)
    return ""


# --------------------------------------------------------------------------- #
# The eight components
# --------------------------------------------------------------------------- #


def score_icp_fit(context: ScoringContext, weight: int) -> ComponentScore:
    icp = context.icp
    if icp is None:
        return ComponentScore(
            component=ScoreComponent.ICP_FIT,
            weight=weight,
            value=None,
            reason="No active ICP to compare against.",
        )

    company = context.company
    checks: list[tuple[str, bool, str]] = []

    if icp.industries:
        matched = _matches_any(company.industry, icp.industries)
        checks.append(("industry", bool(matched), matched or company.industry or "not recorded"))
    if icp.countries:
        wanted = {str(code).upper() for code in icp.countries}
        checks.append(
            ("country", company.country.upper() in wanted, company.country or "not recorded")
        )
    if icp.employee_range and company.employee_range:
        overlap = ranges_overlap(icp.employee_range, company.employee_range)
        if overlap is not None:
            checks.append(("size", overlap, f"{company.employee_range} vs {icp.employee_range}"))
    if icp.business_models:
        matched = _matches_any(company.business_model, icp.business_models)
        checks.append(("business model", bool(matched), matched or "not recorded"))

    if not checks:
        return ComponentScore(
            component=ScoreComponent.ICP_FIT,
            weight=weight,
            value=None,
            reason="The ICP does not specify anything comparable to this record.",
        )

    hits = [name for name, ok, _ in checks if ok]
    value = len(hits) / len(checks)

    return ComponentScore(
        component=ScoreComponent.ICP_FIT,
        weight=weight,
        value=value,
        reason=(
            f"Matches {len(hits)} of {len(checks)} ICP criteria: {', '.join(hits)}."
            if hits
            else f"Matches none of the {len(checks)} ICP criteria checked."
        ),
        evidence=[
            _evidence(
                claim=f"{name.capitalize()} matches the ICP: {detail}",
                source_type="icp_match",
                source_url=company.website,
                confidence="high",
            )
            for name, ok, detail in checks
            if ok
        ],
        detail={
            "matched": hits,
            "missed": [name for name, ok, _ in checks if not ok],
            "icp": icp.name or str(icp.public_id),
        },
    )


def _signal_component(
    context: ScoringContext,
    *,
    component: str,
    weight: int,
    types: frozenset[str],
    nothing_found: str,
) -> ComponentScore:
    if not context.examined:
        return ComponentScore(
            component=component,
            weight=weight,
            value=None,
            # The distinction this whole module is built around.
            reason="This company has not been examined for signals yet.",
        )

    matching = context.live_signals(types)
    value = _signal_value(matching)

    return ComponentScore(
        component=component,
        weight=weight,
        value=value,
        reason=(
            f"{len(matching)} live signal(s): "
            + ", ".join(sorted({s.signal_type.replace("_", " ") for s in matching}))
            if matching
            else nothing_found
        ),
        evidence=[_evidence_from_signal(signal) for signal in matching[:4]],
        detail={
            "signal_types": sorted({s.signal_type for s in matching}),
            "strongest": max((s.decayed_strength() for s in matching), default=0),
        },
    )


def score_buying_intent(context: ScoringContext, weight: int) -> ComponentScore:
    return _signal_component(
        context,
        component=ScoreComponent.BUYING_INTENT,
        weight=weight,
        types=INTENT_SIGNALS,
        nothing_found="No live signals of a buying posture.",
    )


def score_company_growth(context: ScoringContext, weight: int) -> ComponentScore:
    return _signal_component(
        context,
        component=ScoreComponent.COMPANY_GROWTH,
        weight=weight,
        types=GROWTH_SIGNALS,
        nothing_found="No live growth signals.",
    )


def score_pain_evidence(context: ScoringContext, weight: int) -> ComponentScore:
    """The ICP's pain signals, matched against what the engine actually found.

    This is the join the closed ``SignalType`` vocabulary exists for: the ICP
    says what to watch for, the detectors watch for it, and this is where the
    two meet as a number.
    """
    icp = context.icp
    wanted = {
        str(entry.get("type"))
        for entry in (getattr(icp, "pain_signals", None) or [])
        if isinstance(entry, dict) and entry.get("type")
    }

    if not wanted:
        return ComponentScore(
            component=ScoreComponent.PAIN_EVIDENCE,
            weight=weight,
            value=None,
            reason="The ICP names no observable pain signals to look for.",
        )
    if not context.examined:
        return ComponentScore(
            component=ScoreComponent.PAIN_EVIDENCE,
            weight=weight,
            value=None,
            reason="This company has not been examined for signals yet.",
        )

    matching = context.live_signals(frozenset(wanted))
    matched_types = sorted({signal.signal_type for signal in matching})
    value = len(matched_types) / len(wanted)

    descriptions = {
        str(entry.get("type")): str(entry.get("description", ""))
        for entry in (icp.pain_signals or [])
        if isinstance(entry, dict)
    }

    return ComponentScore(
        component=ScoreComponent.PAIN_EVIDENCE,
        weight=weight,
        value=min(value, 1.0),
        reason=(
            "Shows "
            + ", ".join(t.replace("_", " ") for t in matched_types)
            + f" — {len(matched_types)} of the {len(wanted)} pain signals the ICP watches for."
            if matched_types
            else f"None of the {len(wanted)} pain signals the ICP watches for are present."
        ),
        evidence=[
            _evidence_from_signal(signal, icp_pain=descriptions.get(signal.signal_type, ""))
            for signal in matching[:4]
        ],
        detail={
            "watched": sorted(wanted),
            "matched": matched_types,
            "missing": sorted(wanted - set(matched_types)),
        },
    )


def score_technology_fit(context: ScoringContext, weight: int) -> ComponentScore:
    icp = context.icp
    wanted = [str(name) for name in (getattr(icp, "technologies", None) or [])]

    if not wanted:
        return ComponentScore(
            component=ScoreComponent.TECHNOLOGY_FIT,
            weight=weight,
            value=None,
            reason="The ICP does not name any technologies.",
        )
    if not context.technologies:
        return ComponentScore(
            component=ScoreComponent.TECHNOLOGY_FIT,
            weight=weight,
            value=None,
            reason="Nothing is known about this company's technology yet.",
        )

    present = {technology.name.strip().lower(): technology for technology in context.technologies}
    matched = [name for name in wanted if name.strip().lower() in present]
    value = len(matched) / len(wanted)

    return ComponentScore(
        component=ScoreComponent.TECHNOLOGY_FIT,
        weight=weight,
        value=min(value, 1.0),
        reason=(
            f"Uses {', '.join(matched)}, which the ICP names."
            if matched
            else "Uses none of the technologies the ICP names."
        ),
        evidence=[
            _evidence(
                claim=f"{name} detected in use",
                source_type=present[name.strip().lower()].source or "technology_detection",
                source_url=present[name.strip().lower()].source_url,
                confidence=present[name.strip().lower()].confidence,
            )
            for name in matched[:4]
        ],
        detail={"wanted": wanted, "matched": matched},
    )


def score_geographic_fit(context: ScoringContext, weight: int) -> ComponentScore:
    company = context.company
    icp_countries = {str(code).upper() for code in (getattr(context.icp, "countries", None) or [])}
    selected = context.selected_countries

    if not company.country:
        return ComponentScore(
            component=ScoreComponent.GEOGRAPHIC_FIT,
            weight=weight,
            value=None,
            reason="No country recorded for this company.",
        )
    if not icp_countries and not selected:
        return ComponentScore(
            component=ScoreComponent.GEOGRAPHIC_FIT,
            weight=weight,
            value=None,
            reason="No target markets chosen or implied by the ICP.",
        )

    country = company.country.upper()
    in_selected = country in selected
    in_icp = country in icp_countries

    # A market the customer *chose* outranks one the agent merely suggested.
    # The selection is a decision; the ICP's country list is a recommendation.
    if in_selected:
        value, reason = 1.0, f"{country} is one of the markets this workspace selected."
    elif in_icp:
        value, reason = 0.85, f"{country} is in the ICP's countries but is not a selected market."
    else:
        value, reason = 0.0, f"{country} is not a target market."

    return ComponentScore(
        component=ScoreComponent.GEOGRAPHIC_FIT,
        weight=weight,
        value=value,
        reason=reason,
        evidence=(
            [
                _evidence(
                    claim=reason,
                    source_type="market_selection" if in_selected else "icp_match",
                    confidence="high",
                )
            ]
            if value
            else []
        ),
        detail={
            "country": country,
            "selected_markets": sorted(selected),
            "icp_countries": sorted(icp_countries),
        },
    )


def score_contact_quality(context: ScoringContext, weight: int) -> ComponentScore:
    if not context.people:
        return ComponentScore(
            component=ScoreComponent.CONTACT_QUALITY,
            weight=weight,
            value=None,
            reason="No contact identified at this company yet.",
        )

    best_value = 0.0
    best_person = context.people[0]

    for person in context.people:
        if not person.email:
            continue
        if person.email_status in UNSENDABLE_CONTACT_STATUSES:
            continue
        value = EMAIL_STATUS_VALUE.get(person.email_status, 0.5)
        if person.is_decision_maker:
            value += 0.15
        if person.phone and person.phone_status not in UNSENDABLE_CONTACT_STATUSES:
            value += 0.1
        value = min(value, 1.0)
        if value > best_value:
            best_value, best_person = value, person

    if not best_value:
        return ComponentScore(
            component=ScoreComponent.CONTACT_QUALITY,
            weight=weight,
            value=0.0,
            # Assessed, and the answer is nothing: we have contacts and none
            # of them can be written to. That is a real negative, not a gap.
            reason="Contacts exist but none can be contacted (bounced, invalid or unsubscribed).",
            detail={"contacts": len(context.people), "contactable": 0},
        )

    return ComponentScore(
        component=ScoreComponent.CONTACT_QUALITY,
        weight=weight,
        value=best_value,
        reason=(
            f"{best_person.display_name or 'A contact'}"
            + (f" ({best_person.job_title})" if best_person.job_title else "")
            + f" with a {best_person.email_status} email address"
            + (", a decision maker" if best_person.is_decision_maker else "")
            + "."
        ),
        evidence=[
            _evidence(
                claim=f"Contact found: {best_person.display_name}",
                source_type=best_person.email_source or best_person.source or "contact",
                source_url=best_person.linkedin_url,
                confidence=(
                    "high" if best_person.email_status == ContactStatus.VERIFIED else "medium"
                ),
            )
        ],
        detail={
            "email_status": best_person.email_status,
            "is_decision_maker": best_person.is_decision_maker,
            "contacts": len(context.people),
        },
    )


def score_engagement(context: ScoringContext, weight: int) -> ComponentScore:
    """Replies, opens and meetings -- which do not exist until Phase 3.

    Returning "not assessed" rather than zero is what stops the whole product
    reporting a ceiling of 90 for an entire phase. When campaigns ship, this
    is the one function to fill in; nothing else needs to change, because the
    weight redistribution already handles a component appearing.
    """
    return ComponentScore(
        component=ScoreComponent.ENGAGEMENT,
        weight=weight,
        value=None,
        reason="No campaign activity to measure yet.",
    )


SCORERS: dict[str, Any] = {
    ScoreComponent.ICP_FIT: score_icp_fit,
    ScoreComponent.BUYING_INTENT: score_buying_intent,
    ScoreComponent.PAIN_EVIDENCE: score_pain_evidence,
    ScoreComponent.COMPANY_GROWTH: score_company_growth,
    ScoreComponent.TECHNOLOGY_FIT: score_technology_fit,
    ScoreComponent.GEOGRAPHIC_FIT: score_geographic_fit,
    ScoreComponent.CONTACT_QUALITY: score_contact_quality,
    ScoreComponent.ENGAGEMENT: score_engagement,
}


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #


def score_prospect(
    company: Any,
    *,
    icp: Any = None,
    weights: dict[str, int] | None = None,
    context: ScoringContext | None = None,
    now: datetime | None = None,
) -> ScoreResult:
    """Score one company, with the explanation section 119 requires."""
    moment = now or timezone.now()
    context = context or build_context(company, icp=icp, now=moment)
    weights = weights or weights_for(company.organization)

    components: list[ComponentScore] = []
    for component, scorer in SCORERS.items():
        weight = int(weights.get(component, DEFAULT_WEIGHTS.get(component, 0)))
        try:
            components.append(scorer(context, weight))
        except Exception as exc:
            # One broken component must not cost the whole score, and a
            # silently absent one would quietly change the weighting, so it
            # is recorded as unassessed with the reason visible.
            logger.warning(
                "score_component_failed",
                component=component,
                company_id=str(company.public_id),
                error=str(exc)[:200],
            )
            components.append(
                ComponentScore(
                    component=component,
                    weight=weight,
                    value=None,
                    reason="This component could not be calculated.",
                )
            )

    assessed = [component for component in components if component.available]
    assessed_weight = sum(component.weight for component in assessed)
    total_weight = sum(component.weight for component in components) or 1

    if assessed_weight:
        earned = sum((component.value or 0) * component.weight for component in assessed)
        score = round(100 * earned / assessed_weight)
    else:
        score = 0

    coverage = assessed_weight / total_weight
    stale = bool(getattr(company, "is_stale", False))
    confidence = round(100 * coverage * (STALE_CONFIDENCE_FACTOR if stale else 1.0))

    result = ScoreResult(
        score=max(0, min(score, 100)),
        band=band_for(score),
        confidence=max(0, min(confidence, 100)),
        coverage=coverage,
        components=components,
        weights=dict(weights),
        scored_at=moment,
        assumptions={
            # Section 119's "editable assumptions": the things a person can
            # change that would change this number, and where to change them.
            "weights": dict(weights),
            "icp": (
                {"id": str(context.icp.public_id), "name": context.icp.name}
                if context.icp
                else None
            ),
            "selected_markets": sorted(context.selected_countries),
            "company_record_is_stale": stale,
            "editable_at": {
                "weights": "/api/v1/scoring/profile",
                "icp": "/api/v1/intelligence/icps",
                "selected_markets": "/api/v1/intelligence/markets/select",
            },
        },
    )
    return result


def score_lead(lead: Any, *, now: datetime | None = None, weights: dict[str, int] | None = None):
    """Score a lead and store the result on it."""
    from apps.common.tenancy import tenant_context

    result = score_prospect(lead.company, icp=lead.icp, weights=weights, now=now)

    with tenant_context(organization=lead.organization):
        lead.score = result.score
        lead.score_breakdown = result.payload()
        lead.scored_at = result.scored_at
        lead.save(update_fields=["score", "score_breakdown", "scored_at", "updated_at"])

    logger.info(
        "lead_scored",
        lead_id=str(lead.public_id),
        score=result.score,
        band=result.band,
        confidence=result.confidence,
        assessed=len(result.assessed),
    )
    return result


def score_organization_leads(*, organization: Any, limit: int = 1_000) -> int:
    """Rescore an organization's leads. Returns how many were scored."""
    from apps.leads.models import Lead

    weights = weights_for(organization)
    leads = (
        Lead.all_objects.filter(organization_id=organization.pk)
        .select_related("company", "icp", "organization")
        .order_by("-created_at")[:limit]
    )

    count = 0
    for lead in leads:
        score_lead(lead, weights=weights)
        count += 1
    return count


__all__ = [
    "EMAIL_STATUS_VALUE",
    "GROWTH_SIGNALS",
    "INTENT_SIGNALS",
    "MATCH_THRESHOLD",
    "SCORERS",
    "STALE_CONFIDENCE_FACTOR",
    "ComponentScore",
    "ScoreResult",
    "ScoringContext",
    "build_context",
    "parse_headcount_range",
    "ranges_overlap",
    "score_lead",
    "score_organization_leads",
    "score_prospect",
    "significant_words",
]
