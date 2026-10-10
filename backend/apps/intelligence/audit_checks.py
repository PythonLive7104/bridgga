"""What can be measured about a page (PRD section 49).

Section 49 asks for eight scores, some performance observations and a list of
recommendations. The decision that shapes this module is which of those a
model should be allowed to produce.

**Most of it is measurable, so a model never guesses at it.** Whether a page
has one `h1`, a meta description, alt text on its images, structured data, a
canonical link, a price, a privacy policy, a testimonial or a call to action
are all facts about the HTML. Asking a language model to score them produces a
number that sounds authoritative, cannot be reproduced, and leaves the
customer with nothing to fix. Every check here returns what it found and, when
it fails, what to do about it.

**Three dimensions are genuinely judgement** -- is the value proposition
clear, is it obvious who this is for, does the page lead anywhere -- and those
go to the model in ``apps.intelligence.audit_agents``, which is also shown
these findings so its recommendations cannot contradict them.

The division matters more here than anywhere else in the product, because
this audit is the free tool a stranger meets first (section 17). It has to be
right in front of somebody who knows their own website better than we do.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Comment

#: Section 49's dimensions. The first three are judgement, the rest measured.
VALUE_PROPOSITION = "value_proposition"
ICP_CLARITY = "icp_clarity"
CONVERSION = "conversion"
CTA = "cta"
TRUST = "trust"
PRICING_CLARITY = "pricing_clarity"
SEO = "seo"
AEO = "aeo"

MEASURED_DIMENSIONS = (CTA, TRUST, PRICING_CLARITY, SEO, AEO)
JUDGED_DIMENSIONS = (VALUE_PROPOSITION, ICP_CLARITY, CONVERSION)
ALL_DIMENSIONS = JUDGED_DIMENSIONS + MEASURED_DIMENSIONS

DIMENSION_LABELS: dict[str, str] = {
    VALUE_PROPOSITION: "Value proposition",
    ICP_CLARITY: "ICP clarity",
    CONVERSION: "Conversion",
    CTA: "Calls to action",
    TRUST: "Trust",
    PRICING_CLARITY: "Pricing clarity",
    SEO: "SEO",
    AEO: "AEO readiness",
}

#: How much each dimension contributes to the headline score. Judgement
#: carries more than mechanics on purpose: a page with perfect meta tags that
#: nobody understands is a worse page than one with a missing canonical and a
#: clear promise.
DIMENSION_WEIGHTS: dict[str, int] = {
    VALUE_PROPOSITION: 20,
    ICP_CLARITY: 15,
    CONVERSION: 15,
    CTA: 15,
    TRUST: 10,
    PRICING_CLARITY: 10,
    SEO: 10,
    AEO: 5,
}

#: Characters of body text treated as "the first screen". Not a pixel
#: measurement -- we have no rendering engine here -- but a reasonable stand-in
#: for what somebody reads before deciding whether to stay.
FIRST_SCREEN_CHARS = 1_200

_WHITESPACE = re.compile(r"\s+")

_CTA_WORDS = (
    "get started",
    "start free",
    "start now",
    "try free",
    "try it",
    "free trial",
    "book a",
    "book demo",
    "request a demo",
    "get a demo",
    "see it",
    "sign up",
    "create account",
    "talk to",
    "contact sales",
    "get in touch",
    "buy now",
    "subscribe",
    "join",
    "download",
    "get my",
    "claim",
    "schedule",
)

#: CTA text that tells the visitor nothing about what happens next.
_VAGUE_CTA = ("submit", "click here", "learn more", "read more", "more info", "continue", "go")

_TRUST_MARKERS = {
    "testimonial": (
        "testimonial",
        "what our customers",
        "what clients say",
        "loved by",
        "trusted by",
    ),
    "case study": ("case study", "case studies", "success story", "customer story"),
    "review": ("review", "rated", "stars", "g2", "capterra", "trustpilot"),
    "guarantee": ("money-back", "money back", "guarantee", "refund policy", "cancel anytime"),
    "security": ("gdpr", "soc 2", "soc2", "iso 27001", "pci", "encrypted", "ssl", "privacy-first"),
    "numbers": ("customers", "users", "businesses", "companies trust", "+ clients"),
}

_PRICE = re.compile(
    r"(?:US\$|\$|€|£|₦|R|KSh|GH₵|₵|EGP|ZAR|NGN|KES|GHS|USD|EUR|GBP)\s?"
    r"\d[\d,]*(?:\.\d+)?(?:\s?(?:k|m|bn|million|billion)\b)?",
    re.IGNORECASE,
)

_PRICE_WALL = (
    "contact us for pricing",
    "contact sales for pricing",
    "request a quote",
    "get a quote",
    "pricing on request",
    "talk to sales for pricing",
)

_QUESTION_WORDS = ("what", "why", "how", "who", "when", "where", "can i", "do i", "is ", "does ")


# --------------------------------------------------------------------------- #
# Facts
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class PageFacts:
    """Everything the audit measured. No judgement, no scores."""

    url: str = ""
    title: str = ""
    description: str = ""
    language: str = ""
    canonical: str = ""
    robots: str = ""
    has_viewport: bool = False

    h1s: list[str] = field(default_factory=list)
    h2s: list[str] = field(default_factory=list)
    question_headings: list[str] = field(default_factory=list)

    open_graph: list[str] = field(default_factory=list)
    json_ld_types: list[str] = field(default_factory=list)

    images: int = 0
    images_with_alt: int = 0

    internal_links: int = 0
    external_links: int = 0
    forms: int = 0

    cta_texts: list[str] = field(default_factory=list)
    first_screen_ctas: list[str] = field(default_factory=list)
    vague_ctas: list[str] = field(default_factory=list)

    trust_markers: list[str] = field(default_factory=list)
    has_contact_details: bool = False
    has_privacy_link: bool = False
    has_about_link: bool = False
    social_profiles: int = 0

    prices: list[str] = field(default_factory=list)
    pricing_link: str = ""
    price_wall_phrases: list[str] = field(default_factory=list)

    scripts: int = 0
    inline_scripts: int = 0
    stylesheets: int = 0
    bytes: int = 0
    word_count: int = 0
    elapsed_ms: float = 0.0

    first_screen_text: str = ""

    @property
    def alt_coverage(self) -> float:
        return (self.images_with_alt / self.images) if self.images else 1.0


def _text(node: Any) -> str:
    return _WHITESPACE.sub(" ", node.get_text(" ") if node else "").strip()


def _looks_like_cta(label: str) -> bool:
    lowered = label.lower()
    return any(word in lowered for word in _CTA_WORDS)


def measure(html: str, *, url: str, elapsed_ms: float = 0.0) -> PageFacts:
    """Read a page's structure. Pure: same HTML in, same facts out."""
    facts = PageFacts(url=url, bytes=len(html.encode("utf-8", "replace")), elapsed_ms=elapsed_ms)
    soup = BeautifulSoup(html, "html.parser")

    facts.scripts = len(soup.find_all("script", src=True))
    facts.inline_scripts = len([s for s in soup.find_all("script") if not s.get("src")])
    facts.stylesheets = len(soup.find_all("link", attrs={"rel": "stylesheet"}))

    for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(node.string or "{}")
        except (ValueError, TypeError):
            continue
        for entry in data if isinstance(data, list) else [data]:
            if isinstance(entry, dict) and entry.get("@type"):
                kind = entry["@type"]
                facts.json_ld_types.extend(kind if isinstance(kind, list) else [kind])

    if soup.title and soup.title.string:
        facts.title = _WHITESPACE.sub(" ", soup.title.string).strip()[:300]

    description = soup.find("meta", attrs={"name": "description"})
    if description:
        facts.description = (description.get("content") or "").strip()[:600]

    html_tag = soup.find("html")
    facts.language = (html_tag.get("lang", "") if html_tag else "").strip()[:10]

    canonical = soup.find("link", attrs={"rel": "canonical"})
    if canonical and canonical.get("href"):
        facts.canonical = urljoin(url, canonical["href"])[:2048]

    robots = soup.find("meta", attrs={"name": "robots"})
    facts.robots = (robots.get("content", "") if robots else "").strip().lower()
    facts.has_viewport = soup.find("meta", attrs={"name": "viewport"}) is not None

    facts.open_graph = sorted(
        {
            str(tag.get("property"))
            for tag in soup.find_all("meta", attrs={"property": True})
            if str(tag.get("property")).startswith("og:")
        }
    )

    images = soup.find_all("img")
    facts.images = len(images)
    facts.images_with_alt = sum(1 for image in images if (image.get("alt") or "").strip())

    # Scripts and styles go before any text is read, exactly as the extractor
    # does: their contents are not page copy and must not be scored as if
    # they were.
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    for comment in soup.find_all(string=lambda node: isinstance(node, Comment)):
        comment.extract()

    facts.h1s = [_text(node)[:200] for node in soup.find_all("h1") if _text(node)]
    facts.h2s = [_text(node)[:200] for node in soup.find_all("h2", limit=30) if _text(node)]
    facts.question_headings = [
        heading
        for heading in facts.h1s + facts.h2s
        if heading.rstrip().endswith("?") or heading.lower().startswith(_QUESTION_WORDS)
    ]

    body_text = _WHITESPACE.sub(" ", soup.get_text(" ")).strip()
    facts.word_count = len(body_text.split())
    facts.first_screen_text = body_text[:FIRST_SCREEN_CHARS]

    host = urlsplit(url).hostname or ""
    for link in soup.find_all("a", href=True):
        href = link["href"].strip()
        if href.startswith(("mailto:", "tel:")):
            facts.has_contact_details = True
            continue
        target = urljoin(url, href)
        target_host = urlsplit(target).hostname or ""
        if not target_host or target_host == host or target_host == f"www.{host}":
            facts.internal_links += 1
        else:
            facts.external_links += 1
            if any(
                social in target_host
                for social in ("linkedin", "twitter", "x.com", "facebook", "instagram", "youtube")
            ):
                facts.social_profiles += 1

        path = urlsplit(target).path.lower()
        label = _text(link).lower()
        if "privacy" in path or "privacy" in label:
            facts.has_privacy_link = True
        if "/about" in path or label in {"about", "about us"}:
            facts.has_about_link = True
        if not facts.pricing_link and ("pricing" in path or "/plans" in path):
            facts.pricing_link = target[:2048]

    facts.forms = len(soup.find_all("form"))

    for node in soup.find_all(["a", "button"]):
        label = _text(node)[:80]
        if not label or len(label) > 60:
            continue
        lowered = label.lower()
        if _looks_like_cta(label):
            facts.cta_texts.append(label)
            if lowered in facts.first_screen_text.lower()[:FIRST_SCREEN_CHARS]:
                facts.first_screen_ctas.append(label)
        elif lowered.strip(" →>»") in _VAGUE_CTA:
            facts.vague_ctas.append(label)

    lowered_text = body_text.lower()
    facts.trust_markers = sorted(
        {
            name
            for name, markers in _TRUST_MARKERS.items()
            if any(marker in lowered_text for marker in markers)
        }
    )
    facts.has_contact_details = facts.has_contact_details or bool(
        re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", body_text)
    )

    facts.prices = sorted(
        {_WHITESPACE.sub("", m.group(0)).upper() for m in _PRICE.finditer(body_text)}
    )
    facts.price_wall_phrases = [phrase for phrase in _PRICE_WALL if phrase in lowered_text]

    # De-duplicate while keeping order, so a repeated CTA counts once in the
    # list but its repetition is still visible in the raw count.
    facts.cta_texts = list(dict.fromkeys(facts.cta_texts))[:12]
    facts.first_screen_ctas = list(dict.fromkeys(facts.first_screen_ctas))[:6]
    facts.vague_ctas = list(dict.fromkeys(facts.vague_ctas))[:6]
    facts.json_ld_types = sorted({str(kind) for kind in facts.json_ld_types})[:12]

    return facts


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class Check:
    """One thing that was looked at, and what was found.

    ``fix`` is populated only on a failure and is the whole point of the
    audit: "SEO 62/100" tells a visitor nothing, "no meta description, so
    search engines write their own" tells them what to do this afternoon.
    """

    id: str
    dimension: str
    passed: bool
    weight: int
    detail: str
    fix: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "dimension": self.dimension,
            "passed": self.passed,
            "weight": self.weight,
            "detail": self.detail,
            "fix": "" if self.passed else self.fix,
        }


def _check(id: str, dimension: str, passed: bool, weight: int, detail: str, fix: str = "") -> Check:
    return Check(id=id, dimension=dimension, passed=passed, weight=weight, detail=detail, fix=fix)


def seo_checks(facts: PageFacts) -> list[Check]:
    title_length = len(facts.title)
    return [
        _check(
            "title",
            SEO,
            15 <= title_length <= 65,
            3,
            f"Title is {title_length} characters: {facts.title!r}"
            if facts.title
            else "No <title>.",
            "Write a 15-65 character title naming what you do, not just the brand.",
        ),
        _check(
            "meta_description",
            SEO,
            50 <= len(facts.description) <= 165,
            3,
            f"Meta description is {len(facts.description)} characters."
            if facts.description
            else "No meta description.",
            "Add a 50-165 character description; without one the search engine writes its own.",
        ),
        _check(
            "single_h1",
            SEO,
            len(facts.h1s) == 1,
            2,
            f"{len(facts.h1s)} h1 heading(s): {facts.h1s[:2]}",
            "Use exactly one h1 that states the page's subject.",
        ),
        _check(
            "canonical",
            SEO,
            bool(facts.canonical),
            1,
            facts.canonical or "No canonical link.",
            "Add a canonical link so duplicate URLs do not split your ranking.",
        ),
        _check(
            "language",
            SEO,
            bool(facts.language),
            1,
            facts.language or "No lang attribute on <html>.",
            'Set <html lang="..."> so search engines and screen readers know the language.',
        ),
        _check(
            "viewport",
            SEO,
            facts.has_viewport,
            2,
            "Mobile viewport declared." if facts.has_viewport else "No viewport meta tag.",
            "Add a viewport meta tag; without it the page renders desktop-width on phones.",
        ),
        _check(
            "image_alt",
            SEO,
            facts.alt_coverage >= 0.8,
            2,
            f"{facts.images_with_alt} of {facts.images} images have alt text."
            if facts.images
            else "No images.",
            "Describe images in alt text: it is both accessibility and indexable content.",
        ),
        _check(
            "indexable",
            SEO,
            "noindex" not in facts.robots,
            3,
            f"robots: {facts.robots}" if facts.robots else "No robots restriction.",
            "This page tells search engines not to index it. Remove noindex if that is unintended.",
        ),
        _check(
            "open_graph",
            SEO,
            len(facts.open_graph) >= 2,
            1,
            f"Open Graph tags: {', '.join(facts.open_graph) or 'none'}",
            "Add og:title and og:description so shared links show a preview.",
        ),
        _check(
            "internal_links",
            SEO,
            facts.internal_links >= 3,
            1,
            f"{facts.internal_links} internal links.",
            "Link to your other pages so crawlers and readers can go deeper.",
        ),
    ]


def aeo_checks(facts: PageFacts) -> list[Check]:
    """Readiness for answer engines (PRD sections 20 and 49).

    A different question from SEO: not "can this be found" but "can a machine
    quote this as the answer to somebody's question".
    """
    types = {kind.lower() for kind in facts.json_ld_types}
    return [
        _check(
            "structured_data",
            AEO,
            bool(facts.json_ld_types),
            3,
            f"Structured data: {', '.join(facts.json_ld_types) or 'none'}",
            "Add JSON-LD structured data; answer engines read it in preference to prose.",
        ),
        _check(
            "organization_schema",
            AEO,
            bool(types & {"organization", "website", "localbusiness", "corporation"}),
            2,
            "Organization or WebSite schema present."
            if types & {"organization", "website", "localbusiness", "corporation"}
            else "No Organization or WebSite schema.",
            "Describe the business itself in Organization schema so it can be cited by name.",
        ),
        _check(
            "faq_schema",
            AEO,
            bool(types & {"faqpage", "qapage", "howto"}),
            2,
            "FAQ or HowTo schema present."
            if types & {"faqpage", "qapage", "howto"}
            else "No FAQ or HowTo schema.",
            "Mark your FAQ up as FAQPage; it is the format answer engines quote most readily.",
        ),
        _check(
            "question_headings",
            AEO,
            bool(facts.question_headings),
            2,
            f"Question-shaped headings: {len(facts.question_headings)}",
            "Phrase some headings as the questions buyers actually ask, and answer them below.",
        ),
        _check(
            "direct_answer",
            AEO,
            80 <= len(facts.first_screen_text) and bool(facts.h1s),
            1,
            f"First screen carries {len(facts.first_screen_text)} characters of text.",
            "Say what this is in a sentence near the top; a machine cannot quote a slogan.",
        ),
    ]


def cta_checks(facts: PageFacts) -> list[Check]:
    return [
        _check(
            "cta_present",
            CTA,
            bool(facts.cta_texts),
            4,
            f"Calls to action found: {', '.join(facts.cta_texts[:3]) or 'none'}",
            "Add one clear action you want a visitor to take.",
        ),
        _check(
            "cta_above_fold",
            CTA,
            bool(facts.first_screen_ctas),
            3,
            f"In the first screen: {', '.join(facts.first_screen_ctas[:2]) or 'none'}",
            "Put the main action where it is visible without scrolling.",
        ),
        _check(
            "cta_repeated",
            CTA,
            len(facts.cta_texts) >= 2,
            1,
            f"{len(facts.cta_texts)} distinct calls to action.",
            "Repeat the action further down. A reader convinced at the end should not "
            "have to scroll back to act on it.",
        ),
        _check(
            "cta_specific",
            CTA,
            not facts.vague_ctas or bool(facts.cta_texts),
            2,
            f"Vague labels: {', '.join(facts.vague_ctas[:3])}"
            if facts.vague_ctas
            else "No vague call-to-action labels.",
            'Replace "Learn more" and "Submit" with what happens next: "Book a 20-minute demo".',
        ),
        _check(
            "capture_path",
            CTA,
            facts.forms > 0 or facts.has_contact_details,
            2,
            f"{facts.forms} form(s); contact details "
            f"{'present' if facts.has_contact_details else 'absent'}.",
            "Give visitors a way to respond: a form, an email address or a booking link.",
        ),
    ]


def trust_checks(facts: PageFacts) -> list[Check]:
    markers = set(facts.trust_markers)
    return [
        _check(
            "social_proof",
            TRUST,
            bool(markers & {"testimonial", "case study", "review", "numbers"}),
            4,
            f"Trust markers: {', '.join(facts.trust_markers) or 'none found'}",
            "Show evidence other people use this: a named testimonial, a case study, a number.",
        ),
        _check(
            "contact_details",
            TRUST,
            facts.has_contact_details,
            3,
            "Contact details present." if facts.has_contact_details else "No email, phone or form.",
            "Publish a way to reach a human. Anonymity reads as risk to a first-time buyer.",
        ),
        _check(
            "privacy_policy",
            TRUST,
            facts.has_privacy_link,
            2,
            "Privacy policy linked." if facts.has_privacy_link else "No privacy policy link.",
            "Link a privacy policy: it is both a trust marker and a legal requirement "
            "in most markets.",
        ),
        _check(
            "about",
            TRUST,
            facts.has_about_link,
            1,
            "About page linked." if facts.has_about_link else "No about page link.",
            "Say who is behind this. Buyers check.",
        ),
        _check(
            "security_claims",
            TRUST,
            "security" in markers,
            1,
            "Security or compliance mentioned."
            if "security" in markers
            else "No security or compliance mention.",
            "If you handle customer data, say how you protect it.",
        ),
    ]


def pricing_checks(facts: PageFacts) -> list[Check]:
    has_prices = bool(facts.prices)
    return [
        _check(
            "pricing_published",
            PRICING_CLARITY,
            has_prices,
            5,
            f"Prices on this page: {', '.join(facts.prices[:4])}"
            if has_prices
            else "No prices on this page.",
            "Publish a price, or a starting price. Buyers who cannot find one assume "
            "it is too much.",
        ),
        _check(
            "pricing_page",
            PRICING_CLARITY,
            bool(facts.pricing_link) or has_prices,
            3,
            facts.pricing_link
            or ("Prices shown inline." if has_prices else "No pricing page linked."),
            "Give pricing its own page and link it from the navigation.",
        ),
        _check(
            "no_price_wall",
            PRICING_CLARITY,
            not (facts.price_wall_phrases and not has_prices),
            2,
            f"Found: {', '.join(facts.price_wall_phrases)}"
            if facts.price_wall_phrases
            else "No pricing gate.",
            '"Contact us for pricing" costs you the visitors who will not ask. Publish a range.',
        ),
    ]


def run_checks(facts: PageFacts) -> list[Check]:
    """Every measured check, in dimension order."""
    return [
        *cta_checks(facts),
        *trust_checks(facts),
        *pricing_checks(facts),
        *seo_checks(facts),
        *aeo_checks(facts),
    ]


def score_dimension(checks: list[Check], dimension: str) -> int:
    """Weighted share of the checks that passed, 0-100."""
    relevant = [check for check in checks if check.dimension == dimension]
    total = sum(check.weight for check in relevant)
    if not total:
        return 0
    earned = sum(check.weight for check in relevant if check.passed)
    return round(100 * earned / total)


def performance_observations(facts: PageFacts) -> list[dict[str, Any]]:
    """Section 49's "performance observations" -- measurements, not a score.

    Deliberately not scored. Real performance needs a rendering engine and a
    network trace; what can be seen from the HTML is suggestive, and dressing
    it up as a number would be the kind of false precision this audit exists
    to avoid.
    """
    observations = [
        {
            "label": "Page weight",
            "value": f"{facts.bytes / 1024:.0f} KB of HTML",
            "note": "Over 150 KB of HTML alone is heavy before images and scripts."
            if facts.bytes > 150 * 1024
            else "",
        },
        {
            "label": "Scripts",
            "value": f"{facts.scripts} external, {facts.inline_scripts} inline",
            "note": "Each external script is a round trip before the page can finish."
            if facts.scripts > 10
            else "",
        },
        {
            "label": "Stylesheets",
            "value": str(facts.stylesheets),
            "note": "Several stylesheets block the first paint." if facts.stylesheets > 3 else "",
        },
        {
            "label": "Images",
            "value": f"{facts.images} ({facts.images_with_alt} with alt text)",
            "note": "",
        },
        {
            "label": "Server response",
            "value": f"{facts.elapsed_ms:.0f} ms to fetch the HTML",
            "note": "Slow enough that visitors on mobile data will feel it."
            if facts.elapsed_ms > 1_500
            else "",
        },
        {
            "label": "Words on the page",
            "value": str(facts.word_count),
            "note": "Very little copy for a search engine or a buyer to work with."
            if facts.word_count < 150
            else "",
        },
    ]
    return observations


def describe_for_prompt(facts: PageFacts, checks: list[Check]) -> str:
    """What the model is shown: the page's own words, plus what was measured.

    The findings go in deliberately. A model that cannot see them recommends
    adding testimonials to a page that has three, and the whole audit stops
    being credible on the one line the reader checks first.
    """
    failed = [check for check in checks if not check.passed]
    parts = [
        f"URL: {facts.url}",
        f"Title: {facts.title}",
        f"Meta description: {facts.description}" if facts.description else "Meta description: none",
        f"H1: {' | '.join(facts.h1s) or 'none'}",
        f"H2s: {' | '.join(facts.h2s[:12]) or 'none'}",
        f"Calls to action: {', '.join(facts.cta_texts) or 'none found'}",
        f"Prices shown: {', '.join(facts.prices) or 'none'}",
        f"Trust markers found: {', '.join(facts.trust_markers) or 'none'}",
        "",
        "FIRST SCREEN TEXT:",
        facts.first_screen_text,
        "",
        "ALREADY MEASURED -- do not contradict these, and do not recommend "
        "anything they show is already done:",
    ]
    parts += [f"- [{check.dimension}] {check.detail}" for check in checks[:40]]
    if failed:
        parts += ["", "MEASURED PROBLEMS:"]
        parts += [f"- [{check.dimension}] {check.detail}" for check in failed[:20]]
    return "\n".join(parts)


__all__ = [
    "AEO",
    "ALL_DIMENSIONS",
    "CONVERSION",
    "CTA",
    "DIMENSION_LABELS",
    "DIMENSION_WEIGHTS",
    "ICP_CLARITY",
    "JUDGED_DIMENSIONS",
    "MEASURED_DIMENSIONS",
    "PRICING_CLARITY",
    "SEO",
    "TRUST",
    "VALUE_PROPOSITION",
    "Check",
    "PageFacts",
    "describe_for_prompt",
    "measure",
    "performance_observations",
    "run_checks",
    "score_dimension",
]
