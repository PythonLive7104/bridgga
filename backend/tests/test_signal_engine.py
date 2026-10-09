"""The buying-signal engine (PRD section 33).

What is worth testing here is not "does a detector fire". It is the three
things that make a signal feed usable rather than noise, and each of them is a
way the obvious implementation goes wrong:

* **Restraint.** A careers page with no roles, a homepage whose only change is
  a rotated testimonial, and a marketing line offering to "help you raise
  $1M" must all produce nothing. A detector that always finds something is a
  detector whose output means nothing, so the negative cases outnumber the
  positive ones on purpose.
* **Staleness.** Section 33 requires an expiry. The subtle half is which
  signals may have that expiry *extended* on re-detection: an open role still
  listed next week is still open, but "we raised $4M" sits on an About page
  forever and renewing it would make a round from three years ago
  permanently fresh.
* **Deference to people.** Once somebody dismisses a signal, re-running the
  detector that found it must not bring it back.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.ai.providers.stub import StubProvider
from apps.ai.schemas import (
    Confidence,
    Evidence,
    InterpretedSignal,
    SignalInterpretation,
    SignalType,
)
from apps.common.tenancy import tenant_context
from apps.companies import services as company_services
from apps.companies import signal_agents, signal_engine
from apps.companies.detectors import (
    DetectionContext,
    EventSignalDetector,
    FundingNewsDetector,
    HiringPageDetector,
    NewPagesDetector,
    PricingChangeDetector,
    SnapshotPair,
    TechnologyChangeDetector,
    WebsiteChangeDetector,
    prices_in,
)
from apps.companies.models import CompanyEvent, LeadSignal
from apps.companies.signal_models import (
    MIN_FRESHNESS,
    SIGNAL_TTL_DAYS,
    ttl_days_for,
)
from apps.intelligence.models import SnapshotStatus, WebsiteSnapshot
from apps.organizations.roles import Role

pytestmark = pytest.mark.django_db

SIGNALS_URL = "/api/v1/signals"
PROSPECTS_URL = "/api/v1/prospects"

HOME = "https://harmattanfleet.example/"
CAREERS = "https://harmattanfleet.example/careers"
PRICING = "https://harmattanfleet.example/pricing"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def company(organization: Any) -> Any:
    made, _ = company_services.upsert_company(
        organization=organization,
        name="Harmattan Fleet",
        website=HOME,
        industry="Logistics software",
        country="NG",
        source="test",
    )
    return made


def make_page(
    organization: Any,
    company: Any = None,
    *,
    url: str = HOME,
    text: str = "",
    headings: list[str] | None = None,
    links: list[str] | None = None,
    content_hash: str = "",
    fetched_at: Any = None,
) -> WebsiteSnapshot:
    """One stored crawl of one page.

    ``content_hash`` defaults to a hash of the content, as the fetcher would
    produce, so a test that changes the text gets a changed hash without
    having to remember to say so.
    """
    body = text or "Telematics for African haulage."
    with tenant_context(organization=organization):
        return WebsiteSnapshot.objects.create(
            organization=organization,
            company=company,
            requested_url=url,
            final_url=url,
            status=SnapshotStatus.OK,
            title="Harmattan Fleet",
            text=body,
            headings=headings or [],
            internal_links=links or [],
            content_hash=content_hash
            or hashlib.sha256(f"{body}{headings}{links}".encode()).hexdigest(),
            fetched_at=fetched_at or timezone.now(),
        )


def context_for(company: Any, *pairs: SnapshotPair, **extra: Any) -> DetectionContext:
    return DetectionContext(company=company, pages=list(pairs), **extra)


# --------------------------------------------------------------------------- #
# Hiring
# --------------------------------------------------------------------------- #


def test_open_roles_on_a_careers_page_are_a_hiring_signal(organization: Any, company: Any) -> None:
    page = make_page(
        organization,
        company,
        url=CAREERS,
        headings=["Open roles", "Senior Fleet Manager", "Logistics Analyst", "Why join us"],
    )

    found = HiringPageDetector().detect(context_for(company, SnapshotPair(current=page)))

    assert len(found) == 1
    signal = found[0]
    assert signal.signal_type == SignalType.HIRING
    assert "Senior Fleet Manager" in signal.title
    # Page furniture is not a job.
    assert "Why join us" not in signal.title
    # Section 58: the claim arrives with the quote that supports it.
    assert signal.evidence
    assert signal.evidence[0]["quote"] == "Senior Fleet Manager"
    assert signal.evidence[0]["source_url"] == CAREERS
    # An open role is a standing state, so seeing it again means it is still
    # open and the signal's life may be extended.
    assert signal.renewable is True


def test_a_careers_page_with_no_roles_is_not_a_signal(organization: Any, company: Any) -> None:
    """Every company has a careers page. Its existence is not news."""
    page = make_page(
        organization,
        company,
        url=CAREERS,
        headings=["Careers", "Why join us", "Benefits", "No open positions right now"],
    )

    assert HiringPageDetector().detect(context_for(company, SnapshotPair(current=page))) == []


def test_roles_are_read_from_job_links_as_well_as_headings(organization: Any, company: Any) -> None:
    """A careers page that renders its list client-side still links each post."""
    page = make_page(
        organization,
        company,
        url=CAREERS,
        headings=["Open roles"],
        links=[
            "https://harmattanfleet.example/careers/senior-fleet-manager",
            "https://harmattanfleet.example/careers/",
            "https://harmattanfleet.example/about",
        ],
    )

    found = HiringPageDetector().detect(context_for(company, SnapshotPair(current=page)))

    assert len(found) == 1
    assert "Senior Fleet Manager" in found[0].title


def test_more_roles_is_a_stronger_signal(organization: Any, company: Any) -> None:
    one = make_page(organization, company, url=CAREERS, headings=["Fleet Manager"])
    several = make_page(
        organization,
        company,
        url=CAREERS,
        headings=["Fleet Manager", "Logistics Analyst", "Depot Supervisor"],
    )

    weaker = HiringPageDetector().detect(context_for(company, SnapshotPair(current=one)))[0]
    stronger = HiringPageDetector().detect(context_for(company, SnapshotPair(current=several)))[0]

    assert stronger.strength > weaker.strength
    assert stronger.confidence == Confidence.HIGH


def test_the_same_roles_in_a_different_order_are_the_same_observation(
    organization: Any, company: Any
) -> None:
    """Otherwise a reshuffled careers page re-signals on every crawl."""
    first = make_page(
        organization, company, url=CAREERS, headings=["Fleet Manager", "Logistics Analyst"]
    )
    second = make_page(
        organization, company, url=CAREERS, headings=["Logistics Analyst", "Fleet Manager"]
    )

    detector = HiringPageDetector()
    a = detector.detect(context_for(company, SnapshotPair(current=first)))[0]
    b = detector.detect(context_for(company, SnapshotPair(current=second)))[0]

    assert a.fingerprint == b.fingerprint


def test_a_new_role_is_a_new_observation(organization: Any, company: Any) -> None:
    before = make_page(organization, company, url=CAREERS, headings=["Fleet Manager"])
    after = make_page(
        organization, company, url=CAREERS, headings=["Fleet Manager", "Depot Supervisor"]
    )

    detector = HiringPageDetector()
    a = detector.detect(context_for(company, SnapshotPair(current=before)))[0]
    b = detector.detect(context_for(company, SnapshotPair(current=after)))[0]

    assert a.fingerprint != b.fingerprint


# --------------------------------------------------------------------------- #
# Funding
# --------------------------------------------------------------------------- #


def test_a_stated_funding_round_is_a_signal(organization: Any, company: Any) -> None:
    page = make_page(
        organization,
        company,
        text="We raised $4M in Series A funding to expand across West Africa.",
    )

    found = FundingNewsDetector().detect(context_for(company, SnapshotPair(current=page)))

    assert len(found) == 1
    assert found[0].signal_type == SignalType.FUNDING
    assert "$4M" in found[0].evidence[0]["quote"]
    # The page states the round but not its date, so this cannot be renewed on
    # re-detection or a 2023 raise would stay fresh forever.
    assert found[0].renewable is False
    assert found[0].confidence == Confidence.MEDIUM


@pytest.mark.parametrize(
    "text",
    [
        # The infinitive, on a marketing page. The most likely false positive
        # in the whole detector set, because it reads exactly like the real one.
        "We help you raise $1M in revenue in your first year.",
        # Money, and a funding verb, but the wrong kind of money.
        "Our customers announced $5M in savings last quarter.",
        "We processed $20M in transactions this month.",
        # A funding noun with no amount.
        "Our seed customers love the product.",
        # An amount with no funding language at all.
        "Plans start at $49 per vehicle per month.",
    ],
)
def test_money_on_a_page_is_not_a_funding_round(organization: Any, company: Any, text: str) -> None:
    page = make_page(organization, company, text=text)

    assert FundingNewsDetector().detect(context_for(company, SnapshotPair(current=page))) == []


# --------------------------------------------------------------------------- #
# Website diffing
# --------------------------------------------------------------------------- #


def test_one_crawl_is_not_a_change(organization: Any, company: Any) -> None:
    """A site seen once has not changed anything."""
    page = make_page(organization, company, headings=["Anything"])

    assert WebsiteChangeDetector().detect(context_for(company, SnapshotPair(current=page))) == []
    assert NewPagesDetector().detect(context_for(company, SnapshotPair(current=page))) == []


def test_an_unchanged_page_is_not_a_change(organization: Any, company: Any) -> None:
    previous = make_page(organization, company, text="Same", content_hash="abc")
    current = make_page(organization, company, text="Same", content_hash="abc")

    found = WebsiteChangeDetector().detect(
        context_for(company, SnapshotPair(current=current, previous=previous))
    )

    assert found == []


def test_a_cosmetic_change_is_not_a_signal(organization: Any, company: Any) -> None:
    """The bytes differ; nothing a buyer would notice does."""
    previous = make_page(
        organization,
        company,
        text="Telematics for haulage operators. Trusted by depots across Lagos.",
        headings=["Fleet tracking"],
        content_hash="one",
    )
    current = make_page(
        organization,
        company,
        text="Telematics for haulage operators. Trusted by depots across Lagos!",
        headings=["Fleet tracking"],
        content_hash="two",
    )

    found = WebsiteChangeDetector().detect(
        context_for(company, SnapshotPair(current=current, previous=previous))
    )

    assert found == []


def test_a_new_homepage_section_is_a_website_change(organization: Any, company: Any) -> None:
    previous = make_page(organization, company, headings=["Fleet tracking"], content_hash="one")
    current = make_page(
        organization,
        company,
        headings=["Fleet tracking", "Predictive maintenance"],
        content_hash="two",
    )

    found = WebsiteChangeDetector().detect(
        context_for(company, SnapshotPair(current=current, previous=previous))
    )

    assert len(found) == 1
    assert found[0].signal_type == SignalType.WEBSITE_CHANGE
    assert "Predictive maintenance" in found[0].title
    assert found[0].evidence[0]["quote"] == "Predictive maintenance"


def test_new_pages_in_the_navigation_are_a_signal(organization: Any, company: Any) -> None:
    previous = make_page(organization, company, links=[f"{HOME}about"])
    current = make_page(
        organization, company, links=[f"{HOME}about", f"{HOME}integrations", f"{HOME}enterprise"]
    )

    found = NewPagesDetector().detect(
        context_for(company, SnapshotPair(current=current, previous=previous))
    )

    assert len(found) == 1
    assert found[0].signal_type == SignalType.NEW_PAGES
    assert "/integrations" in found[0].description
    assert "/enterprise" in found[0].description


def test_a_tracking_parameter_is_not_a_new_page(organization: Any, company: Any) -> None:
    """Or every campaign link in the footer becomes a product announcement."""
    previous = make_page(organization, company, links=[f"{HOME}about"])
    current = make_page(organization, company, links=[f"{HOME}about?utm_source=newsletter"])

    found = NewPagesDetector().detect(
        context_for(company, SnapshotPair(current=current, previous=previous))
    )

    assert found == []


# --------------------------------------------------------------------------- #
# Pricing
# --------------------------------------------------------------------------- #


def test_prices_are_read_in_the_launch_market_currencies() -> None:
    """A Nigerian pricing page states naira, and must not read as priceless."""
    assert prices_in("Starter is ₦45,000 per month") == ["₦45,000"]
    assert prices_in("From KSh 6,500 monthly") == ["KSH6,500"]
    assert prices_in("No prices here, call us") == []


def test_a_changed_price_is_a_strong_signal(organization: Any, company: Any) -> None:
    previous = make_page(
        organization, company, url=PRICING, text="Starter costs $59 per vehicle per month."
    )
    current = make_page(
        organization, company, url=PRICING, text="Starter costs $49 per vehicle per month."
    )

    found = PricingChangeDetector().detect(
        context_for(company, SnapshotPair(current=current, previous=previous))
    )

    assert len(found) == 1
    signal = found[0]
    assert signal.signal_type == SignalType.PRICING_CHANGE
    assert signal.confidence == Confidence.HIGH
    assert signal.strength >= 70
    assert "$49" in signal.description and "$59" in signal.description
    # Both sides quoted, so the claim can be checked rather than believed.
    assert any("$49" in entry["quote"] for entry in signal.evidence)
    assert any("$59" in entry["quote"] for entry in signal.evidence)


def test_an_unchanged_pricing_page_is_not_a_signal(organization: Any, company: Any) -> None:
    previous = make_page(organization, company, url=PRICING, text="Starter costs $49.")
    current = make_page(
        organization, company, url=PRICING, text="Starter costs $49. New copy above."
    )

    found = PricingChangeDetector().detect(
        context_for(company, SnapshotPair(current=current, previous=previous))
    )

    assert found == []


def test_prices_disappearing_is_not_reported_as_a_repricing(
    organization: Any, company: Any
) -> None:
    """ "Contact us" replacing a price list is a different thing entirely."""
    previous = make_page(organization, company, url=PRICING, text="Starter costs $49.")
    current = make_page(organization, company, url=PRICING, text="Contact us for pricing.")

    found = PricingChangeDetector().detect(
        context_for(company, SnapshotPair(current=current, previous=previous))
    )

    assert found == []


def test_publishing_pricing_for_the_first_time_is_its_own_signal(
    organization: Any, company: Any
) -> None:
    previous = make_page(organization, company, url=PRICING, text="Contact us for pricing.")
    current = make_page(organization, company, url=PRICING, text="Starter costs $49 per month.")

    found = PricingChangeDetector().detect(
        context_for(company, SnapshotPair(current=current, previous=previous))
    )

    assert len(found) == 1
    assert "Pricing published" in found[0].title


# --------------------------------------------------------------------------- #
# Technology and events
# --------------------------------------------------------------------------- #


def test_a_newly_adopted_technology_is_a_signal(organization: Any, company: Any) -> None:
    technology = company_services.record_technology(company=company, name="Shopify", source="test")

    found = TechnologyChangeDetector().detect(context_for(company, technologies=[technology]))

    assert len(found) == 1
    assert found[0].signal_type == SignalType.TECHNOLOGY_CHANGE
    assert "started using" in found[0].title
    assert found[0].occurred_at is not None


def test_a_long_standing_technology_is_not_news(organization: Any, company: Any) -> None:
    technology = company_services.record_technology(company=company, name="Shopify", source="test")
    with tenant_context(organization=organization):
        old = timezone.now() - timezone.timedelta(
            days=ttl_days_for(SignalType.TECHNOLOGY_CHANGE) + 1
        )
        technology.first_seen = old
        technology.last_seen = old
        technology.save(update_fields=["first_seen", "last_seen"])

    assert TechnologyChangeDetector().detect(context_for(company, technologies=[technology])) == []


def test_a_recent_event_becomes_a_signal(organization: Any, company: Any) -> None:
    """The bridge: anything that arrives as news becomes a reason to call."""
    with tenant_context(organization=organization):
        event = CompanyEvent.objects.create(
            organization=organization,
            company=company,
            event_type=SignalType.FUNDING,
            title="Closed a $4M Series A",
            description="Reported by a trade publication.",
            occurred_at=timezone.now() - timezone.timedelta(days=10),
            url="https://news.example/harmattan-series-a",
            source="news_feed",
            confidence=Confidence.HIGH,
        )

    found = EventSignalDetector().detect(context_for(company, events=[event]))

    assert len(found) == 1
    signal = found[0]
    assert signal.signal_type == SignalType.FUNDING
    assert signal.source_event_id == event.pk
    # A dated event keeps its date, which is what makes expiry meaningful.
    assert signal.occurred_at == event.occurred_at
    assert signal.confidence == Confidence.HIGH
    assert signal.strength == 80


def test_an_old_event_does_not_become_a_signal(organization: Any, company: Any) -> None:
    """It would be expired on arrival, which is just a slow way of nothing."""
    with tenant_context(organization=organization):
        event = CompanyEvent.objects.create(
            organization=organization,
            company=company,
            event_type=SignalType.FUNDING,
            title="Seed round",
            occurred_at=timezone.now() - timezone.timedelta(days=900),
        )

    assert EventSignalDetector().detect(context_for(company, events=[event])) == []


# --------------------------------------------------------------------------- #
# Staleness and decay (section 33)
# --------------------------------------------------------------------------- #


def test_every_signal_type_has_a_lifetime() -> None:
    """A new ``SignalType`` must not silently inherit a default window.

    The enum is the vocabulary shared with ICP pain signals, so it grows. When
    it does, somebody has to decide how long that kind of signal stays worth
    acting on, and this is what makes them.
    """
    missing = [member.value for member in SignalType if member.value not in SIGNAL_TTL_DAYS]

    assert not missing, f"no TTL decided for: {missing}"


def test_expiry_is_derived_from_the_type(organization: Any, company: Any) -> None:
    with tenant_context(organization=organization):
        signal = LeadSignal.objects.create(
            organization=organization,
            company=company,
            signal_type=SignalType.HIRING,
            title="Hiring",
            fingerprint="f",
        )

    expected = ttl_days_for(SignalType.HIRING)
    assert (signal.expires_at - signal.detected_at).days == expected
    # Funding is worth mentioning for far longer than a changed homepage.
    assert ttl_days_for(SignalType.FUNDING) > ttl_days_for(SignalType.WEBSITE_CHANGE)


@override_settings(SIGNAL_TTL_DAYS={SignalType.HIRING: 14})
def test_a_lifetime_can_be_tuned_per_deployment() -> None:
    """A staffing firm cares about a hiring post for a fortnight."""
    assert ttl_days_for(SignalType.HIRING) == 14
    # Unlisted types fall back to the shipped table rather than the default.
    assert ttl_days_for(SignalType.FUNDING) == SIGNAL_TTL_DAYS[SignalType.FUNDING]


def test_a_signal_decays_towards_its_expiry(organization: Any, company: Any) -> None:
    now = timezone.now()
    with tenant_context(organization=organization):
        signal = LeadSignal.objects.create(
            organization=organization,
            company=company,
            signal_type=SignalType.HIRING,
            title="Hiring",
            fingerprint="f",
            strength=100,
            detected_at=now,
        )

    assert signal.freshness(at=now) == pytest.approx(1.0, abs=0.01)
    assert signal.decayed_strength(at=now) == 100

    halfway = now + timezone.timedelta(days=ttl_days_for(SignalType.HIRING) // 2)
    assert 0.5 < signal.freshness(at=halfway) < 0.65
    assert 50 < signal.decayed_strength(at=halfway) < 65

    # Inside the window a signal is never worth nothing; past it, it is.
    almost = signal.expires_at - timezone.timedelta(hours=1)
    assert signal.freshness(at=almost) >= MIN_FRESHNESS
    assert signal.decayed_strength(at=signal.expires_at) == 0


def test_a_dismissed_signal_is_worth_nothing_however_fresh(organization: Any, company: Any) -> None:
    with tenant_context(organization=organization):
        signal = LeadSignal.objects.create(
            organization=organization,
            company=company,
            signal_type=SignalType.HIRING,
            title="Hiring",
            fingerprint="f",
            strength=90,
            dismissed_at=timezone.now(),
        )

    assert signal.is_active() is False
    assert signal.decayed_strength() == 0


def test_active_excludes_the_expired_and_the_dismissed(organization: Any, company: Any) -> None:
    with tenant_context(organization=organization):
        live = LeadSignal.objects.create(
            organization=organization,
            company=company,
            signal_type=SignalType.HIRING,
            title="Live",
            fingerprint="a",
        )
        LeadSignal.objects.create(
            organization=organization,
            company=company,
            signal_type=SignalType.HIRING,
            title="Expired",
            fingerprint="b",
            expires_at=timezone.now() - timezone.timedelta(days=1),
        )
        LeadSignal.objects.create(
            organization=organization,
            company=company,
            signal_type=SignalType.HIRING,
            title="Dismissed",
            fingerprint="c",
            dismissed_at=timezone.now(),
        )

        assert [s.pk for s in LeadSignal.objects.active()] == [live.pk]


# --------------------------------------------------------------------------- #
# The engine: idempotence, renewal, deference
# --------------------------------------------------------------------------- #


def careers_context(organization: Any, company: Any, roles: list[str]) -> DetectionContext:
    page = make_page(organization, company, url=CAREERS, headings=roles)
    return context_for(company, SnapshotPair(current=page))


def test_detection_is_idempotent(organization: Any, company: Any) -> None:
    """It runs on a schedule, so the second run must update, not duplicate.

    Without this, one open role becomes 168 signals a week and the prospect
    table is unreadable.
    """
    detector = HiringPageDetector()
    detected = detector.detect(careers_context(organization, company, ["Fleet Manager"]))[0]

    first, created_first = signal_engine.record_signal(company=company, detected=detected)
    second, created_second = signal_engine.record_signal(company=company, detected=detected)

    assert created_first is True
    assert created_second is False
    assert first.pk == second.pk
    assert LeadSignal.all_objects.filter(company=company).count() == 1
    assert second.last_seen_at > second.detected_at or second.last_seen_at is not None


def test_a_standing_observation_is_renewed_when_seen_again(organization: Any, company: Any) -> None:
    """The role is still on the page, so the signal is still live."""
    detector = HiringPageDetector()
    detected = detector.detect(careers_context(organization, company, ["Fleet Manager"]))[0]

    long_ago = timezone.now() - timezone.timedelta(days=40)
    signal, _ = signal_engine.record_signal(company=company, detected=detected, now=long_ago)
    first_expiry = signal.expires_at

    refreshed, _ = signal_engine.record_signal(company=company, detected=detected)

    assert refreshed.expires_at > first_expiry


def test_a_past_event_is_not_renewed_by_being_read_again(organization: Any, company: Any) -> None:
    """The decisive case for staleness.

    "We raised $4M" stays on an About page indefinitely. If every crawl
    extended its life, a round from three years ago would be permanently
    fresh -- which is exactly the failure an expiry exists to prevent.
    """
    page = make_page(organization, company, text="We raised $4M in Series A funding.")
    detected = FundingNewsDetector().detect(context_for(company, SnapshotPair(current=page)))[0]

    long_ago = timezone.now() - timezone.timedelta(days=150)
    signal, _ = signal_engine.record_signal(company=company, detected=detected, now=long_ago)
    first_expiry = signal.expires_at

    refreshed, _ = signal_engine.record_signal(company=company, detected=detected)

    assert refreshed.expires_at == first_expiry
    assert refreshed.last_seen_at > first_expiry - timezone.timedelta(days=200)


def test_re_detection_does_not_overrule_a_person(organization: Any, company: Any) -> None:
    detector = HiringPageDetector()
    detected = detector.detect(careers_context(organization, company, ["Fleet Manager"]))[0]
    signal, _ = signal_engine.record_signal(company=company, detected=detected)
    signal_engine.dismiss_signal(signal=signal, reason="We already sell to them")

    detected.title = "Hiring: a completely different pitch"
    refreshed, created = signal_engine.record_signal(company=company, detected=detected)

    assert created is False
    assert refreshed.is_dismissed is True
    assert refreshed.title != detected.title
    # Still recorded as present, because a dismissed signal that keeps
    # reappearing is useful feedback about the detector.
    assert refreshed.last_seen_at is not None


def test_run_detectors_stores_what_it_finds(organization: Any, company: Any) -> None:
    make_page(
        organization,
        company,
        url=CAREERS,
        headings=["Open roles", "Fleet Manager", "Depot Supervisor"],
    )

    produced = signal_engine.run_detectors(company=company)

    assert [signal.signal_type for signal in produced] == [SignalType.HIRING]
    assert LeadSignal.all_objects.filter(company=company).count() == 1


def test_running_everything_twice_creates_nothing_new(organization: Any, company: Any) -> None:
    make_page(organization, company, url=CAREERS, headings=["Fleet Manager"])
    make_page(organization, company, text="We raised $4M in seed funding.")

    signal_engine.run_detectors(company=company)
    before = LeadSignal.all_objects.filter(company=company).count()
    signal_engine.run_detectors(company=company)

    assert LeadSignal.all_objects.filter(company=company).count() == before == 2


def test_one_broken_detector_does_not_cost_the_others(organization: Any, company: Any) -> None:
    """One brittle regex should not take a company's whole signal set with it."""

    class Exploding:
        name = "exploding"

        def detect(self, context: DetectionContext) -> list:
            raise RuntimeError("regex went wrong")

    make_page(organization, company, url=CAREERS, headings=["Fleet Manager"])

    produced = signal_engine.run_detectors(
        company=company, detectors=(Exploding(), HiringPageDetector())
    )

    assert [signal.signal_type for signal in produced] == [SignalType.HIRING]


def test_pruning_keeps_what_a_person_decided(organization: Any, company: Any) -> None:
    """An expired signal is dead weight. A dismissed one is a human verdict."""
    old = timezone.now() - timezone.timedelta(days=800)
    with tenant_context(organization=organization):
        LeadSignal.objects.create(
            organization=organization,
            company=company,
            signal_type=SignalType.HIRING,
            title="Long expired",
            fingerprint="a",
            expires_at=old,
        )
        kept = LeadSignal.objects.create(
            organization=organization,
            company=company,
            signal_type=SignalType.HIRING,
            title="Expired but dismissed",
            fingerprint="b",
            expires_at=old,
            dismissed_at=old,
        )

    deleted = signal_engine.prune_signals(organization=organization, older_than_days=365)

    assert deleted == 1
    assert list(LeadSignal.all_objects.values_list("pk", flat=True)) == [kept.pk]


def test_crawling_attributes_pages_to_the_company(
    organization: Any, company: Any, monkeypatch: Any
) -> None:
    """Without the attribution, nothing can be diffed against anything."""
    from apps.intelligence import services as intelligence_services
    from apps.intelligence.fetcher import FetchResult

    def fake_fetch(url: str, **kwargs: Any) -> FetchResult:
        body = (
            "<html><head><title>Harmattan</title></head><body>"
            "<h1>Fleet tracking</h1><a href='/careers'>Careers</a>"
            "</body></html>"
        )
        return FetchResult(
            requested_url=url,
            final_url=url,
            status_code=200,
            content_type="text/html",
            body=body,
            resolved_ips=["93.184.216.34"],
            elapsed_ms=1.0,
        )

    monkeypatch.setattr(intelligence_services, "fetch_url", fake_fetch)

    captured = signal_engine.crawl_company_pages(company=company)

    assert captured
    assert all(page.company_id == company.pk for page in captured)
    assert {page.requested_url for page in captured} >= {HOME}


# --------------------------------------------------------------------------- #
# The AI interpreter
# --------------------------------------------------------------------------- #


def changed_homepage(organization: Any, company: Any) -> None:
    make_page(
        organization,
        company,
        headings=["Fleet tracking"],
        text="Telematics for haulage operators.",
        content_hash="before",
        fetched_at=timezone.now() - timezone.timedelta(days=7),
    )
    make_page(
        organization,
        company,
        headings=["Fleet tracking", "Introducing Fleet Pulse"],
        text=(
            "Telematics for haulage operators. "
            "Introducing Fleet Pulse, our new predictive maintenance module."
        ),
        content_hash="after",
    )


def interpretation(**overrides: Any) -> SignalInterpretation:
    defaults: dict[str, Any] = {
        "signals": [
            InterpretedSignal(
                type=SignalType.PRODUCT_LAUNCH,
                title="Launched Fleet Pulse, a predictive maintenance module",
                why_it_matters="A new module means a new budget line.",
                confidence=Confidence.HIGH,
                evidence=[
                    Evidence(
                        claim="The homepage announces Fleet Pulse.",
                        source_type="website_page",
                        quote="Introducing Fleet Pulse, our new predictive maintenance module.",
                    )
                ],
            )
        ],
        "reasoning": "A new product section appeared.",
    }
    return SignalInterpretation(**(defaults | overrides))


def test_the_diff_sent_to_the_model_is_only_what_changed(organization: Any, company: Any) -> None:
    """Sending the whole page would cost more and bury the change in it."""
    changed_homepage(organization, company)
    pair = signal_engine.build_context(company).homepage()

    diff = signal_agents.build_diff_text(pair)

    assert "Introducing Fleet Pulse" in diff
    assert "New headings: Introducing Fleet Pulse" in diff
    # The unchanged sentence is not re-sent.
    assert diff.count("Telematics for haulage operators") == 0


def test_a_grounded_interpretation_is_stored(organization: Any, company: Any) -> None:
    changed_homepage(organization, company)
    provider = StubProvider(responses=[interpretation()])

    stored = signal_agents.interpret_website_change(company=company, provider=provider)

    assert len(stored) == 1
    signal = stored[0]
    assert signal.signal_type == SignalType.PRODUCT_LAUNCH
    assert signal.detector == signal_agents.DETECTOR_NAME
    assert signal.source == "ai_interpretation"
    assert signal.evidence[0]["quote"].startswith("Introducing Fleet Pulse")


def test_an_ungrounded_interpretation_is_discarded(organization: Any, company: Any) -> None:
    """The check that matters most in the whole engine.

    Page content is attacker-controlled and a model can be wrong on its own
    account. A signal whose quote is nowhere in the material shown is not a
    weak signal, it is a fabricated one, so it is dropped rather than stored
    with a low confidence.
    """
    changed_homepage(organization, company)
    provider = StubProvider(
        responses=[
            interpretation(
                signals=[
                    InterpretedSignal(
                        type=SignalType.FUNDING,
                        title="Raised $50M in Series B",
                        confidence=Confidence.HIGH,
                        evidence=[
                            Evidence(
                                claim="They announced a raise.",
                                source_type="website_page",
                                quote="We have raised $50M in Series B funding.",
                            )
                        ],
                    )
                ]
            )
        ]
    )

    stored = signal_agents.interpret_website_change(company=company, provider=provider)

    assert stored == []
    assert not LeadSignal.all_objects.filter(signal_type=SignalType.FUNDING).exists()


def test_an_interpretation_with_no_quote_at_all_is_discarded(
    organization: Any, company: Any
) -> None:
    changed_homepage(organization, company)
    provider = StubProvider(
        responses=[
            interpretation(
                signals=[
                    InterpretedSignal(
                        type=SignalType.EXPANSION,
                        title="Expanding into Kenya",
                        confidence=Confidence.HIGH,
                        evidence=[],
                    )
                ]
            )
        ]
    )

    assert signal_agents.interpret_website_change(company=company, provider=provider) == []


def test_no_model_is_called_when_there_is_nothing_to_interpret(
    organization: Any, company: Any
) -> None:
    """The cost control. Without it this is a paid call per prospect per crawl."""
    make_page(organization, company, content_hash="only-one")
    provider = StubProvider(responses=[interpretation()])

    stored = signal_agents.interpret_website_change(company=company, provider=provider)

    assert stored == []
    assert provider.calls == []


def test_no_model_is_called_when_the_page_is_unchanged(organization: Any, company: Any) -> None:
    make_page(organization, company, content_hash="same", fetched_at=timezone.now())
    make_page(organization, company, content_hash="same", fetched_at=timezone.now())
    provider = StubProvider(responses=[interpretation()])

    assert signal_agents.interpret_website_change(company=company, provider=provider) == []
    assert provider.calls == []


def test_the_page_content_reaches_the_model_fenced_as_untrusted(
    organization: Any, company: Any
) -> None:
    """Anyone can write an instruction on a website and wait to be crawled."""
    changed_homepage(organization, company)
    provider = StubProvider(responses=[interpretation()])

    signal_agents.interpret_website_change(company=company, provider=provider)

    assert provider.calls
    assert "UNTRUSTED CONTENT" in provider.calls[0].user_content


def test_an_interpretation_is_billed_to_the_organization(organization: Any, company: Any) -> None:
    from apps.ai.models import AIJob, AIJobStatus

    changed_homepage(organization, company)
    signal_agents.interpret_website_change(
        company=company, provider=StubProvider(responses=[interpretation()])
    )

    with tenant_context(organization=organization):
        job = AIJob.objects.filter(feature="signal_interpretation").first()

    assert job is not None
    assert job.status == AIJobStatus.SUCCEEDED
    assert job.organization_id == organization.pk
    assert job.prompt_pin == "signal_interpretation@1"


def test_a_model_failure_leaves_no_signals_and_no_exception(
    organization: Any, company: Any
) -> None:
    """A detection run is a background job; a traceback tells the customer nothing."""
    from apps.ai.providers.base import AIProviderError

    changed_homepage(organization, company)
    provider = StubProvider(responses=[AIProviderError("upstream exploded")] * 2)

    assert signal_agents.interpret_website_change(company=company, provider=provider) == []


# --------------------------------------------------------------------------- #
# The API
# --------------------------------------------------------------------------- #


@pytest.fixture
def live_signal(organization: Any, company: Any) -> LeadSignal:
    with tenant_context(organization=organization):
        return LeadSignal.objects.create(
            organization=organization,
            company=company,
            signal_type=SignalType.HIRING,
            title="Hiring three fleet supervisors",
            fingerprint="live",
            strength=80,
            detector="hiring_page",
            evidence=[{"claim": "Careers page lists the role", "quote": "Fleet Supervisor"}],
        )


def test_the_feed_returns_live_signals_with_their_evidence(
    organization: Any, owner: Any, auth_client: Callable[..., Any], live_signal: LeadSignal
) -> None:
    response = auth_client(owner, organization).get(SIGNALS_URL)

    assert response.status_code == 200
    row = response.data["results"][0]
    assert row["signal_type"] == "hiring"
    assert row["company_name"] == "Harmattan Fleet"
    # Section 58: the evidence is the product, so it is on the row rather than
    # behind a second request per signal.
    assert row["evidence"][0]["quote"] == "Fleet Supervisor"
    assert row["strength"] == 80
    assert row["decayed_strength"] <= row["strength"]
    assert row["is_active"] is True


def test_the_feed_hides_expired_signals_unless_asked(
    organization: Any, owner: Any, auth_client: Callable[..., Any], company: Any
) -> None:
    with tenant_context(organization=organization):
        LeadSignal.objects.create(
            organization=organization,
            company=company,
            signal_type=SignalType.FUNDING,
            title="Old round",
            fingerprint="old",
            expires_at=timezone.now() - timezone.timedelta(days=1),
        )

    client = auth_client(owner, organization)

    assert client.get(SIGNALS_URL).data["count"] == 0
    assert client.get(f"{SIGNALS_URL}?include_expired=true").data["count"] == 1


def test_asking_for_dismissed_signals_does_not_require_asking_for_old_ones(
    organization: Any, owner: Any, auth_client: Callable[..., Any], live_signal: LeadSignal
) -> None:
    """Two independent questions, two independent flags.

    "What did my team reject?" is a question about the detectors and has
    nothing to do with age, so it must not be reachable only by also asking
    for expired signals.
    """
    signal_engine.dismiss_signal(signal=live_signal, user=owner, reason="Already a customer")
    client = auth_client(owner, organization)

    assert client.get(SIGNALS_URL).data["count"] == 0
    assert client.get(f"{SIGNALS_URL}?include_dismissed=true").data["count"] == 1


def test_the_feed_filters_by_type_and_company(
    organization: Any, owner: Any, auth_client: Callable[..., Any], company: Any, live_signal: Any
) -> None:
    other, _ = company_services.upsert_company(
        organization=organization,
        name="LedgerLite",
        website="https://ledgerlite.example",
        source="test",
    )
    with tenant_context(organization=organization):
        LeadSignal.objects.create(
            organization=organization,
            company=other,
            signal_type=SignalType.PRICING_CHANGE,
            title="Repriced",
            fingerprint="price",
        )

    client = auth_client(owner, organization)

    assert client.get(f"{SIGNALS_URL}?type=hiring").data["count"] == 1
    assert client.get(f"{SIGNALS_URL}?type=hiring,pricing_change").data["count"] == 2
    assert (
        client.get(f"{SIGNALS_URL}?company={company.public_id}").data["results"][0]["signal_type"]
        == "hiring"
    )


def test_the_summary_counts_only_what_is_present(
    organization: Any, owner: Any, auth_client: Callable[..., Any], live_signal: Any
) -> None:
    """Offering a filter for a signal type nobody has is a filter for nothing."""
    response = auth_client(owner, organization).get(f"{SIGNALS_URL}/summary")

    assert response.status_code == 200
    assert response.data["types"] == [{"value": "hiring", "count": 1}]
    assert response.data["total"] == 1


def test_dismissing_a_signal_hides_it_and_is_attributed(
    organization: Any, owner: Any, auth_client: Callable[..., Any], live_signal: LeadSignal
) -> None:
    from apps.audit.models import AuditAction, AuditLog

    client = auth_client(owner, organization)
    response = client.post(
        f"{SIGNALS_URL}/{live_signal.public_id}/dismiss",
        {"reason": "Already a customer"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["is_dismissed"] is True
    assert client.get(SIGNALS_URL).data["count"] == 0

    live_signal.refresh_from_db()
    assert live_signal.dismissed_by == owner
    assert live_signal.dismiss_reason == "Already a customer"

    with tenant_context(organization=organization):
        assert AuditLog.objects.filter(action=AuditAction.SIGNAL_DISMISSED).exists()


@pytest.mark.security
def test_a_viewer_cannot_dismiss_a_signal(
    organization: Any,
    auth_client: Callable[..., Any],
    make_member: Callable[..., Any],
    live_signal: LeadSignal,
) -> None:
    viewer = make_member(organization, role=Role.VIEWER).user

    response = auth_client(viewer, organization).post(
        f"{SIGNALS_URL}/{live_signal.public_id}/dismiss", {}, format="json"
    )

    assert response.status_code == 403
    assert auth_client(viewer, organization).get(SIGNALS_URL).status_code == 200


@pytest.mark.tenancy
def test_another_tenants_signal_is_invisible_and_untouchable(
    other_organization: Any,
    make_member: Callable[..., Any],
    auth_client: Callable[..., Any],
    live_signal: LeadSignal,
) -> None:
    intruder = make_member(other_organization, role=Role.ADMIN).user
    client = auth_client(intruder, other_organization)

    assert client.get(SIGNALS_URL).data["count"] == 0
    assert (
        client.post(f"{SIGNALS_URL}/{live_signal.public_id}/dismiss", {}, format="json").status_code
        == 404
    )

    live_signal.refresh_from_db()
    assert live_signal.is_dismissed is False


def test_a_prospects_signal_history_is_available_on_request(
    organization: Any,
    owner: Any,
    auth_client: Callable[..., Any],
    company: Any,
    live_signal: Any,
) -> None:
    """The list shows live signals; the detail view can show the archive."""
    with tenant_context(organization=organization):
        LeadSignal.objects.create(
            organization=organization,
            company=company,
            signal_type=SignalType.FUNDING,
            title="Round from last year",
            fingerprint="old",
            expires_at=timezone.now() - timezone.timedelta(days=5),
        )

    client = auth_client(owner, organization)
    base = f"{PROSPECTS_URL}/{company.public_id}/signals"

    assert len(client.get(base).data) == 1
    assert len(client.get(f"{base}?include_stale=true").data) == 2


def test_detecting_signals_for_a_prospect_requires_managing_prospects(
    organization: Any,
    auth_client: Callable[..., Any],
    make_member: Callable[..., Any],
    company: Any,
    monkeypatch: Any,
) -> None:
    """A viewer can read prospects without spending the crawl budget."""
    from apps.companies import tasks as company_tasks

    queued: list[int] = []
    monkeypatch.setattr(
        company_tasks.refresh_company_signals, "delay", lambda company_id: queued.append(company_id)
    )

    viewer = make_member(organization, role=Role.VIEWER).user
    url = f"{PROSPECTS_URL}/{company.public_id}/detect-signals"

    assert auth_client(viewer, organization).post(url).status_code == 403
    assert queued == []

    manager = make_member(organization, role=Role.SALES_REP).user
    assert auth_client(manager, organization).post(url).status_code == 202
    assert queued == [company.pk]


def test_the_feed_does_not_make_a_query_per_signal(
    organization: Any,
    owner: Any,
    auth_client: Callable[..., Any],
    company: Any,
    django_assert_max_num_queries: Any,
) -> None:
    """Section 103's budget: the page cost must not grow with the row count."""
    with tenant_context(organization=organization):
        for index in range(15):
            LeadSignal.objects.create(
                organization=organization,
                company=company,
                signal_type=SignalType.HIRING,
                title=f"Role {index}",
                fingerprint=f"f{index}",
            )

    client = auth_client(owner, organization)
    with django_assert_max_num_queries(10):
        response = client.get(SIGNALS_URL)

    assert response.data["count"] == 15
