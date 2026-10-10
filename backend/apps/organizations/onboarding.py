"""Where a customer has got to (PRD section 25).

Section 25 lists nine steps. The first five are buildable now; steps 6 to 9
need mailboxes and campaigns, which are Phase 3. This module answers one
question for the five that exist: what should this customer be looking at?

**The answer is derived, not stored.** The tempting design is an
``onboarding_step`` integer on the organization, incremented as each screen is
finished. It drifts the first time reality diverges from the counter: a
customer deletes their only ICP and the column still says step 5, so the
wizard sends them to markets with nothing to base a market on. Reading the
actual records instead means the state cannot be wrong, and the wizard
self-heals when somebody undoes something.

**One thing is stored, because it genuinely is a decision**:
``onboarding_completed_at``. Once a customer has been through the path, later
deleting an ICP should not drag them back through onboarding -- they are a
user of the product now, dealing with their own data. Derivation answers
"what is set up"; the timestamp answers "have we finished introducing
ourselves", and those are different questions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: The five steps of section 25 that exist today, in order.
WEBSITE = "website"
ANALYSIS = "analysis"
CONFIRM = "confirm"
ICP = "icp"
MARKETS = "markets"

STEP_ORDER = (WEBSITE, ANALYSIS, CONFIRM, ICP, MARKETS)

STEP_LABELS: dict[str, str] = {
    WEBSITE: "Your website",
    ANALYSIS: "Reading your site",
    CONFIRM: "Confirm your business",
    ICP: "Ideal customer",
    MARKETS: "Target markets",
}


@dataclass(slots=True)
class Step:
    key: str
    label: str
    #: ``done``, ``current``, ``todo``, ``running`` or ``failed``. ``running``
    #: and ``failed`` exist because step 2 is a background crawl and a model
    #: call: a wizard that showed only done/not-done would have nothing to say
    #: for the thirty seconds that matter most, or when the site cannot be
    #: read.
    state: str
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"key": self.key, "label": self.label, "state": self.state, "detail": self.detail}


@dataclass(slots=True)
class OnboardingState:
    steps: list[Step] = field(default_factory=list)
    current: str = WEBSITE
    complete: bool = False
    completed_at: Any = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "steps": [step.as_dict() for step in self.steps],
            "current": self.current,
            "complete": self.complete,
            "completed_at": self.completed_at,
            # What the five steps are, so a client does not hardcode an order
            # that this module owns.
            "order": list(STEP_ORDER),
        }


def onboarding_state(organization: Any) -> OnboardingState:
    """Read the records and say where this customer is."""
    from apps.common.tenancy import tenant_context
    from apps.intelligence.models import ICP as ICPModel
    from apps.intelligence.models import CompanyProfile, MarketRecommendation, ProfileStatus

    with tenant_context(organization=organization):
        profile = CompanyProfile.objects.filter(organization=organization).first()
        icp = ICPModel.objects.filter(organization=organization, is_active=True).first()
        any_icp = icp or ICPModel.objects.filter(organization=organization).first()
        selected = MarketRecommendation.objects.filter(
            organization=organization, is_selected=True
        ).count()
        recommended = MarketRecommendation.objects.filter(organization=organization).count()

    website = (profile.website if profile else "") or organization.website
    status = profile.status if profile else ""

    steps = [
        Step(
            key=WEBSITE,
            label=STEP_LABELS[WEBSITE],
            state="done" if website else "current",
            detail=website or "",
        ),
        _analysis_step(profile, website, status, ProfileStatus),
        Step(
            key=CONFIRM,
            label=STEP_LABELS[CONFIRM],
            state="done" if (profile and profile.is_confirmed) else "todo",
            detail=(profile.company_name or profile.one_line_summary or "") if profile else "",
        ),
        Step(
            key=ICP,
            label=STEP_LABELS[ICP],
            state="done" if icp else "todo",
            detail=(icp or any_icp).name if (icp or any_icp) else "",
        ),
        Step(
            key=MARKETS,
            label=STEP_LABELS[MARKETS],
            state="done" if selected else "todo",
            detail=(
                f"{selected} market(s) selected"
                if selected
                else (f"{recommended} ranked" if recommended else "")
            ),
        ),
    ]

    # The first step that is not finished is the one to show. A failed or
    # running analysis is the current step too: it is what the customer is
    # waiting on, and it is where the explanation lives when it goes wrong.
    current = next(
        (step.key for step in steps if step.state != "done"),
        MARKETS,
    )
    for step in steps:
        if step.key == current and step.state == "todo":
            step.state = "current"

    complete = all(step.state == "done" for step in steps)
    completed_at = organization.onboarding_completed_at

    return OnboardingState(
        steps=steps,
        current=current,
        # Either every step is done, or the customer has been through once and
        # we are no longer entitled to send them back.
        complete=complete or completed_at is not None,
        completed_at=completed_at,
    )


def _analysis_step(profile: Any, website: str, status: str, statuses: Any) -> Step:
    if profile is None or not website:
        return Step(key=ANALYSIS, label=STEP_LABELS[ANALYSIS], state="todo")

    if status == statuses.ANALYZING:
        return Step(
            key=ANALYSIS,
            label=STEP_LABELS[ANALYSIS],
            state="running",
            detail="Reading the site now.",
        )
    if status == statuses.FAILED:
        return Step(
            key=ANALYSIS,
            label=STEP_LABELS[ANALYSIS],
            state="failed",
            detail=profile.analysis_error,
        )
    if profile.last_analyzed_at:
        return Step(
            key=ANALYSIS,
            label=STEP_LABELS[ANALYSIS],
            state="done",
            detail=f"{profile.source_snapshots.count()} page(s) read.",
        )
    return Step(key=ANALYSIS, label=STEP_LABELS[ANALYSIS], state="todo")


def mark_complete(organization: Any) -> Any:
    """Record that this customer has been through onboarding.

    Idempotent, and never un-set: "we have introduced ourselves" does not stop
    being true.
    """
    from django.utils import timezone

    if organization.onboarding_completed_at is None:
        organization.onboarding_completed_at = timezone.now()
        organization.save(update_fields=["onboarding_completed_at", "updated_at"])
    return organization


__all__ = [
    "ANALYSIS",
    "CONFIRM",
    "ICP",
    "MARKETS",
    "STEP_LABELS",
    "STEP_ORDER",
    "WEBSITE",
    "OnboardingState",
    "Step",
    "mark_complete",
    "onboarding_state",
]
