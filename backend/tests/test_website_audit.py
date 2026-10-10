"""The website sales audit (PRD sections 49 and 17).

This is the only thing in the product a stranger can run without an account,
so it is tested from two directions at once: does it produce an honest
result, and can it be abused.

The honesty half is mostly about the split. Section 49 asks for eight scores,
and five of them are facts about the HTML -- a meta description either exists
or it does not. Those are counted, never asked of a model, because a score
nobody can reproduce is a score nobody can act on. Only "is the value
proposition clear", "is it obvious who this is for" and "does the page lead
anywhere" go to a model, and it is shown the measurements so its
recommendations cannot contradict them.

The abuse half is about what replaces authentication: an SSRF-hardened
fetcher, an IP throttle, a cache window, and a ledger entry so the cost of
the free tool is a query rather than a surprise.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.ai.providers.base import AIProviderError
from apps.ai.providers.stub import StubProvider
from apps.ai.schemas import (
    AuditDimension,
    AuditRecommendation,
    Confidence,
    Effort,
    WebsiteAuditJudgement,
)
from apps.intelligence import audit_agents
from apps.intelligence.audit_checks import (
    AEO,
    CTA,
    PRICING_CLARITY,
    SEO,
    TRUST,
    measure,
    performance_observations,
    run_checks,
    score_dimension,
)
from apps.intelligence.audit_models import AuditStatus, WebsiteAudit
from apps.intelligence.fetcher import FetchError, FetchResult, UnsafeUrlError

pytestmark = pytest.mark.django_db

AUDIT_URL = "/api/v1/tools/website-audit"
SITE = "https://harmattanfleet.example"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

GOOD_PAGE = """<!doctype html>
<html lang="en">
<head>
  <title>Harmattan Fleet — telematics for African haulage</title>
  <meta name="description" content="Cut fuel loss and hit delivery SLAs with real-time
        vehicle tracking built for haulage operators in Nigeria and Ghana.">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta property="og:title" content="Harmattan Fleet">
  <meta property="og:description" content="Telematics for African haulage">
  <link rel="canonical" href="https://harmattanfleet.example/">
  <script type="application/ld+json">
    {"@type": "Organization", "name": "Harmattan Fleet"}
  </script>
  <script type="application/ld+json">
    {"@type": "FAQPage", "name": "Questions"}
  </script>
</head>
<body>
  <h1>Stop losing fuel you already paid for</h1>
  <p>Harmattan Fleet tracks every vehicle in real time and reconciles fuel spend
     against route data, so a depot manager sees the loss the same day.</p>
  <a href="/signup">Start free trial</a>
  <h2>What does it cost?</h2>
  <p>Plans start at $49 per vehicle per month.</p>
  <h2>Trusted by 40 haulage operators</h2>
  <p>"We cut idle time in the first month." — Tunde A., fleet manager. Read the case study.</p>
  <img src="/truck.png" alt="A truck on the Lagos-Ibadan expressway">
  <a href="/pricing">Pricing</a>
  <a href="/about">About</a>
  <a href="/privacy">Privacy policy</a>
  <a href="mailto:hello@harmattanfleet.example">hello@harmattanfleet.example</a>
  <a href="https://linkedin.com/company/harmattanfleet">LinkedIn</a>
  <a href="/book-a-demo">Book a demo</a>
  <form><input type="email" name="email"></form>
</body>
</html>
"""

BARE_PAGE = """<!doctype html>
<html>
<head><title>Home</title></head>
<body>
  <h1>Welcome</h1>
  <h1>Also welcome</h1>
  <p>We provide solutions for business. Contact us for pricing.</p>
  <a href="/x">Learn more</a>
  <img src="/a.png">
</body>
</html>
"""


def fetch_returning(html: str, *, elapsed_ms: float = 120.0) -> Callable[..., FetchResult]:
    def _fetch(url: str, **kwargs: Any) -> FetchResult:
        return FetchResult(
            requested_url=url,
            final_url=url,
            status_code=200,
            content_type="text/html",
            body=html,
            elapsed_ms=elapsed_ms,
            resolved_ips=["93.184.216.34"],
        )

    return _fetch


def judgement(**overrides: Any) -> WebsiteAuditJudgement:
    defaults: dict[str, Any] = {
        "what_they_sell": "Telematics and fuel reconciliation for haulage fleets.",
        "who_its_for": "Haulage operators in Nigeria and Ghana.",
        "value_proposition_score": 80,
        "value_proposition_note": "The headline names the loss and the remedy.",
        "icp_clarity_score": 70,
        "icp_clarity_note": "Says West Africa, does not say fleet size.",
        "conversion_score": 65,
        "conversion_note": "Two actions, both above the fold.",
        "recommendations": [
            AuditRecommendation(
                title="Name the fleet size you serve",
                detail="The page says haulage operators but not whether 5 trucks or 500.",
                dimension=AuditDimension.ICP_CLARITY,
                impact=Confidence.HIGH,
                effort=Effort.LOW,
            )
        ],
        "confidence": Confidence.HIGH,
    }
    return WebsiteAuditJudgement(**(defaults | overrides))


@pytest.fixture
def stub_fetch(monkeypatch: Any) -> Callable[[str], None]:
    def _install(html: str, elapsed_ms: float = 120.0) -> None:
        monkeypatch.setattr(audit_agents, "fetch_url", fetch_returning(html, elapsed_ms=elapsed_ms))

    return _install


# --------------------------------------------------------------------------- #
# Measurement: pure, free, and the bulk of the audit
# --------------------------------------------------------------------------- #


def test_a_well_built_page_measures_well() -> None:
    facts = measure(GOOD_PAGE, url=SITE, elapsed_ms=120)
    checks = run_checks(facts)

    assert score_dimension(checks, SEO) >= 90
    assert score_dimension(checks, AEO) >= 80
    assert score_dimension(checks, CTA) >= 80
    assert score_dimension(checks, TRUST) >= 80
    assert score_dimension(checks, PRICING_CLARITY) >= 80


def test_a_bare_page_measures_badly_and_says_why() -> None:
    """Every failure carries the fix. That is the deliverable, not the score."""
    facts = measure(BARE_PAGE, url=SITE)
    checks = run_checks(facts)

    assert score_dimension(checks, SEO) < 50
    assert score_dimension(checks, AEO) < 20
    assert score_dimension(checks, PRICING_CLARITY) < 50

    failed = {check.id: check for check in checks if not check.passed}
    assert "meta_description" in failed
    assert "single_h1" in failed
    assert "structured_data" in failed
    # Not a list of complaints: a list of instructions.
    assert all(check.fix for check in failed.values())
    assert "50-165" in failed["meta_description"].fix


@pytest.mark.parametrize(
    ("html", "check_id", "passes"),
    [
        ('<html lang="en"><title>A clear and specific page title</title>', "title", True),
        ("<html><title>Hi</title>", "title", False),
        ('<html lang="en">', "language", True),
        ("<html>", "language", False),
        ('<html><meta name="robots" content="noindex, follow">', "indexable", False),
        ('<html><meta name="robots" content="index, follow">', "indexable", True),
        ('<html><meta name="viewport" content="width=device-width">', "viewport", True),
        ("<html><body>no viewport</body>", "viewport", False),
    ],
)
def test_individual_seo_checks(html: str, check_id: str, passes: bool) -> None:
    checks = {check.id: check for check in run_checks(measure(html, url=SITE))}

    assert checks[check_id].passed is passes


def test_a_price_on_the_page_satisfies_pricing_clarity() -> None:
    facts = measure("<html><body>Plans start at ₦45,000 per month.</body></html>", url=SITE)
    checks = {check.id: check for check in run_checks(facts)}

    assert facts.prices == ["₦45,000"]
    assert checks["pricing_published"].passed is True


def test_contact_us_for_pricing_is_reported_as_a_gate() -> None:
    """A real finding with a cost attached, not a style preference."""
    facts = measure("<html><body>Contact us for pricing and we will help.</body></html>", url=SITE)
    checks = {check.id: check for check in run_checks(facts)}

    assert checks["no_price_wall"].passed is False
    assert "will not ask" in checks["no_price_wall"].fix


def test_a_vague_call_to_action_is_distinguished_from_a_missing_one() -> None:
    facts = measure('<html><body><a href="/x">Learn more</a></body></html>', url=SITE)

    assert facts.cta_texts == []
    assert facts.vague_ctas == ["Learn more"]


def test_script_contents_are_never_read_as_page_copy() -> None:
    """The same rule the extractor follows, for the same reason.

    A page whose only "testimonial" is a string inside an analytics snippet
    has no testimonial, and scoring it as one would be a finding the owner
    cannot find on their own page.
    """
    html = """<html><body>
      <script>var t = "Trusted by 400 companies, read the case study";</script>
      <p>Nothing else here.</p>
    </body></html>"""

    facts = measure(html, url=SITE)

    assert facts.trust_markers == []


def test_performance_is_observed_and_never_scored() -> None:
    """Section 49 asks for observations. A number here would be false precision.

    Real performance needs a rendering engine and a network trace. What the
    HTML can show is suggestive, and dressing it up as a score would be the
    kind of confident wrongness this audit exists to avoid.
    """
    facts = measure(GOOD_PAGE, url=SITE, elapsed_ms=2_400)
    observations = performance_observations(facts)

    labels = {item["label"] for item in observations}
    assert {"Page weight", "Scripts", "Server response"} <= labels
    assert all(isinstance(item["value"], str) for item in observations)
    assert any("mobile data" in item["note"] for item in observations)
    # No score, no band, no grade.
    assert not any("score" in key for item in observations for key in item)


# --------------------------------------------------------------------------- #
# The model's half
# --------------------------------------------------------------------------- #


def test_the_model_is_shown_what_was_already_measured(stub_fetch: Any) -> None:
    """The guard against the most embarrassing possible output.

    A model that cannot see the findings recommends adding testimonials to a
    page that has three, and the audit loses its reader on the one line they
    check first.
    """
    stub_fetch(GOOD_PAGE)
    provider = StubProvider(responses=[judgement()])

    audit_agents.run_website_audit(url=SITE, provider=provider)

    sent = provider.calls[0].user_content
    assert "ALREADY MEASURED" in sent
    assert "Start free trial" in sent
    assert "$49" in sent
    # And the page's own words, which is what the judgement is about.
    assert "Stop losing fuel you already paid for" in sent


def test_the_page_reaches_the_model_fenced_as_untrusted(stub_fetch: Any) -> None:
    """Anyone can submit any URL. The content is a stranger's by definition."""
    stub_fetch(GOOD_PAGE)
    provider = StubProvider(responses=[judgement()])

    audit_agents.run_website_audit(url=SITE, provider=provider)

    assert "UNTRUSTED CONTENT" in provider.calls[0].user_content


def test_an_audit_survives_the_model_failing(stub_fetch: Any) -> None:
    """Section 17 promised a useful free result, not an error page.

    The measured half has already run by the time the model is called. Five
    dimensions of checkable findings are worth far more to the visitor who
    pasted their URL than an apology.
    """
    stub_fetch(GOOD_PAGE)
    provider = StubProvider(responses=[AIProviderError("upstream exploded")] * 2)

    audit = audit_agents.run_website_audit(url=SITE, provider=provider)

    assert audit.status == AuditStatus.READY
    assert audit.judged is False
    assert audit.overall_score > 0
    assert set(audit.scores) == {CTA, TRUST, PRICING_CLARITY, SEO, AEO}
    assert audit.checks
    # And the score is out of what was measured, not capped by what was not.
    assert audit.overall_score >= 70


def test_an_unjudged_audit_is_not_scored_out_of_everything(stub_fetch: Any) -> None:
    """ADR 0009's rule again: drop the weight, do not zero the dimension.

    Scoring the three judged dimensions as 0 would cap every measured-only
    audit at 60, and the visitor would never know why.
    """
    stub_fetch(GOOD_PAGE)

    judged = audit_agents.run_website_audit(
        url=SITE, provider=StubProvider(responses=[judgement()]), use_cache=False
    )
    unjudged = audit_agents.run_website_audit(
        url=SITE, provider=StubProvider(responses=[AIProviderError("no")] * 2), use_cache=False
    )

    assert judged.judged is True
    assert len(judged.scores) == 8
    assert unjudged.overall_score > 60


def test_the_judgement_fills_the_three_dimensions_it_owns(stub_fetch: Any) -> None:
    stub_fetch(GOOD_PAGE)

    audit = audit_agents.run_website_audit(url=SITE, provider=StubProvider(responses=[judgement()]))

    assert audit.scores["value_proposition"] == 80
    assert audit.scores["icp_clarity"] == 70
    assert audit.scores["conversion"] == 65
    assert audit.notes["icp_clarity"].startswith("Says West Africa")
    assert audit.what_they_sell.startswith("Telematics")
    assert audit.recommendations[0]["impact"] == "high"
    assert audit.recommendations[0]["effort"] == "low"


# --------------------------------------------------------------------------- #
# Cost and abuse: what stands in for authentication
# --------------------------------------------------------------------------- #


def test_the_same_url_is_not_crawled_twice_in_an_hour(stub_fetch: Any) -> None:
    """A public endpoint that crawls a site and calls a paid model.

    Without a window it is a way to spend our money and somebody else's
    bandwidth, one refresh at a time.
    """
    stub_fetch(GOOD_PAGE)
    first = audit_agents.run_website_audit(url=SITE, provider=StubProvider(responses=[judgement()]))

    second_provider = StubProvider(responses=[judgement()])
    second = audit_agents.run_website_audit(url=SITE, provider=second_provider)

    assert second.pk == first.pk
    assert second_provider.calls == [], "the cached result should cost nothing"


@override_settings(WEBSITE_AUDIT_CACHE_MINUTES=0)
def test_the_cache_window_is_configurable(stub_fetch: Any) -> None:
    """Somebody fixing their page should be able to re-check it."""
    stub_fetch(GOOD_PAGE)
    first = audit_agents.run_website_audit(url=SITE, provider=StubProvider(responses=[judgement()]))
    second = audit_agents.run_website_audit(
        url=SITE, provider=StubProvider(responses=[judgement()])
    )

    assert second.pk != first.pk


def test_anonymous_spend_is_billed_to_a_named_tenant(stub_fetch: Any) -> None:
    """The free tool's cost must be a query, not a surprise on an invoice.

    An AI job belongs to an organization and an anonymous visitor has none.
    Skipping the ledger would leave the one feature most likely to be abused
    as the only one whose cost nobody could see.
    """
    from apps.ai.models import AIJob
    from apps.common.tenancy import unscoped

    stub_fetch(GOOD_PAGE)
    audit_agents.run_website_audit(url=SITE, provider=StubProvider(responses=[judgement()]))

    public = audit_agents.public_tools_organization()
    with unscoped():
        job = AIJob.all_objects.filter(feature="website_audit").first()
        assert job is not None
        assert job.organization_id == public.pk
        assert job.cost_micro_usd > 0

    # Nobody can reach it: it exists as a billing bucket, not a workspace.
    assert public.organizations_membership_set.count() == 0


def test_an_audit_requested_in_a_workspace_is_attributed_to_it(
    organization: Any, owner: Any, stub_fetch: Any
) -> None:
    """The same endpoint serves the in-product feature."""
    stub_fetch(GOOD_PAGE)

    audit = audit_agents.run_website_audit(
        url=SITE,
        organization=organization,
        requested_by=owner,
        provider=StubProvider(responses=[judgement()]),
    )

    assert audit.organization_id == organization.pk
    assert audit.requested_by_id == owner.pk


@pytest.mark.security
def test_an_unsafe_url_is_refused_in_words(monkeypatch: Any) -> None:
    """The fetcher is what makes "give us any URL" safe to offer at all.

    Its own suite covers the SSRF rules; what matters here is that a refusal
    reaches the visitor as an explanation rather than a traceback.
    """

    def refuse(url: str, **kwargs: Any) -> Any:
        raise UnsafeUrlError("resolves to a private address", url=url)

    monkeypatch.setattr(audit_agents, "fetch_url", refuse)

    audit = audit_agents.run_website_audit(url="http://169.254.169.254/latest/meta-data")

    assert audit.status == AuditStatus.FAILED
    assert "private address" in audit.error_reason


def test_an_unreachable_site_is_reported_not_raised(monkeypatch: Any) -> None:
    def fail(url: str, **kwargs: Any) -> Any:
        raise FetchError("Connection refused")

    monkeypatch.setattr(audit_agents, "fetch_url", fail)

    audit = audit_agents.run_website_audit(url="https://nothing-here.example")

    assert audit.status == AuditStatus.FAILED
    assert "Connection refused" in audit.error_reason


def test_something_that_is_not_a_url_is_refused_before_any_work(monkeypatch: Any) -> None:
    called: list[str] = []
    monkeypatch.setattr(audit_agents, "fetch_url", lambda url, **kw: called.append(url))

    audit = audit_agents.run_website_audit(url="   ")

    assert audit.status == AuditStatus.FAILED
    assert called == []


def test_a_page_with_no_content_is_not_sent_to_a_model(stub_fetch: Any) -> None:
    """Paying to judge an empty page is paying for nothing."""
    stub_fetch("<html><body></body></html>")
    provider = StubProvider(responses=[judgement()])

    audit = audit_agents.run_website_audit(url=SITE, provider=provider)

    assert audit.status == AuditStatus.FAILED
    assert provider.calls == []


# --------------------------------------------------------------------------- #
# The API
# --------------------------------------------------------------------------- #


def test_a_stranger_can_run_an_audit(api_client: Any, stub_fetch: Any, monkeypatch: Any) -> None:
    """The defining requirement of section 17: no account, useful result."""
    stub_fetch(GOOD_PAGE)
    monkeypatch.setattr(
        audit_agents, "judge", lambda *args, **kwargs: None
    )  # no spend in the API test

    response = api_client.post(AUDIT_URL, {"url": "harmattanfleet.example"}, format="json")

    assert response.status_code == 200
    assert response.data["status"] == "ready"
    assert response.data["overall_score"] > 0
    assert response.data["band"] in {"high", "medium", "low"}
    assert response.data["checks"]
    assert response.data["failed_checks"] is not None
    assert response.data["performance"]


def test_a_result_is_readable_by_whoever_has_the_link(
    api_client: Any, stub_fetch: Any, monkeypatch: Any
) -> None:
    """The share token is the public id, which is the access rule the tool needs."""
    stub_fetch(GOOD_PAGE)
    monkeypatch.setattr(audit_agents, "judge", lambda *args, **kwargs: None)

    created = api_client.post(AUDIT_URL, {"url": SITE}, format="json")
    audit_id = created.data["id"]

    fetched = api_client.get(f"{AUDIT_URL}/{audit_id}")

    assert fetched.status_code == 200
    assert fetched.data["id"] == audit_id


def test_an_unknown_audit_id_is_a_404(api_client: Any) -> None:
    import uuid

    assert api_client.get(f"{AUDIT_URL}/{uuid.uuid4()}").status_code == 404


def test_a_submitted_email_is_never_echoed_back(
    api_client: Any, stub_fetch: Any, monkeypatch: Any
) -> None:
    """It arrived from an anonymous form and the result is shared by link.

    Returning it would publish an address to whoever the link reaches, which
    is the opposite of what somebody giving it to us expects.
    """
    stub_fetch(GOOD_PAGE)
    monkeypatch.setattr(audit_agents, "judge", lambda *args, **kwargs: None)

    response = api_client.post(
        AUDIT_URL, {"url": SITE, "email": "ada@harmattanfleet.example"}, format="json"
    )

    assert "ada@harmattanfleet.example" not in str(response.data)
    stored = WebsiteAudit.objects.get(public_id=response.data["id"])
    assert stored.email == "ada@harmattanfleet.example"


def test_a_bad_submission_is_rejected_by_the_serializer(api_client: Any) -> None:
    assert api_client.post(AUDIT_URL, {}, format="json").status_code == 400
    assert (
        api_client.post(
            AUDIT_URL, {"url": SITE, "email": "not-an-email"}, format="json"
        ).status_code
        == 400
    )


def test_the_endpoint_is_throttled_by_address(
    api_client: Any, stub_fetch: Any, monkeypatch: Any
) -> None:
    """There is no organization to key a limit on, so it keys on the caller.

    The rate is forced here rather than configured: what is under test is
    that the throttle is attached to this view at all, not DRF's parsing of
    "20/min".
    """
    from django.core.cache import cache

    from apps.common.throttling import AnonBurstThrottle

    monkeypatch.setattr(AnonBurstThrottle, "get_rate", lambda self: "2/min")
    cache.clear()
    stub_fetch(GOOD_PAGE)
    monkeypatch.setattr(audit_agents, "judge", lambda *args, **kwargs: None)

    statuses = [
        api_client.post(
            AUDIT_URL, {"url": f"https://site{index}.example"}, format="json"
        ).status_code
        for index in range(4)
    ]
    cache.clear()

    assert statuses[:2] == [200, 200]
    assert 429 in statuses, f"the free tool is not rate limited: {statuses}"


def test_the_audit_is_deliberately_not_tenant_owned() -> None:
    """A model that opts out of the generic isolation test earns it with this.

    The audit is public by design: its visibility rule is "whoever has the
    link". It is not tenant data and must not claim to be, or the isolation
    test would be asserting something false about it.
    """
    from apps.common.managers import tenant_model_classes
    from apps.common.models import TenantOwnedModel

    assert not issubclass(WebsiteAudit, TenantOwnedModel)
    assert WebsiteAudit not in tenant_model_classes()
    # The link to a workspace is attribution, not access control.
    assert WebsiteAudit._meta.get_field("organization").null is True


def test_an_audit_of_the_customers_own_site_can_feed_the_profile(
    organization: Any, stub_fetch: Any
) -> None:
    """Why this ships in Phase 2 rather than with the marketing site.

    The same crawl that answers a stranger's question is the one onboarding
    runs, so the audit is a feature of the product and a free tool with one
    implementation rather than two that drift.
    """
    stub_fetch(GOOD_PAGE)

    audit = audit_agents.run_website_audit(
        url=SITE, organization=organization, provider=StubProvider(responses=[judgement()])
    )

    assert audit.domain == "harmattanfleet.example"
    assert audit.page_title.startswith("Harmattan Fleet")
    assert audit.content_hash
    assert audit.fetched_at <= timezone.now()
