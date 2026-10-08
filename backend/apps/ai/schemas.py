"""Output schemas (PRD sections 58 and 119).

Every agent returns a Pydantic model, and the API constrains the model to it.
Two rules are enforced by the shape of these types rather than by convention:

* **A claim carries its evidence.** ``Evidence`` has a required source and a
  retrieval time. An agent that wants to assert something has to say where it
  came from, because PRD section 58 requires the platform to still produce the
  source URL and timestamp later.
* **Uncertainty is representable.** Every judgement has a ``confidence`` and
  fields are optional where the honest answer is "not stated". Without that,
  a model with nothing to go on will invent something to fill a required
  string, which is exactly the failure PRD section 57 forbids.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Base for all agent output.

    ``extra="forbid"`` maps to ``additionalProperties: false`` in the generated
    JSON schema, which is what lets the API constrain the response exactly.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Evidence(StrictModel):
    """Where a claim came from."""

    claim: str = Field(description="The specific thing being asserted, in one sentence.")
    source_type: str = Field(
        description="What kind of source this is, e.g. website_page, careers_page, news."
    )
    source_url: str = Field(default="", description="URL the claim was read from, if any.")
    quote: str = Field(
        default="",
        max_length=500,
        description="Short verbatim excerpt supporting the claim. Empty if not quotable.",
    )
    retrieved_at: datetime | None = Field(default=None, description="When the source was fetched.")
    confidence: Confidence = Confidence.MEDIUM


class CompanyProfile(StrictModel):
    """AI understanding of a company from its website (PRD section 26).

    Every field is optional or defaulted because a thin website genuinely does
    not state most of this, and a required field is an invitation to fabricate.
    """

    company_name: str = ""
    one_line_summary: str = Field(default="", max_length=300)
    products: list[str] = Field(default_factory=list, max_length=20)
    industry: str = ""
    business_model: str = Field(
        default="", description="e.g. B2B SaaS subscription, marketplace, services retainer."
    )
    target_customers: list[str] = Field(default_factory=list, max_length=20)
    value_proposition: str = ""
    use_cases: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Concrete jobs customers use this for, as the source describes them.",
    )
    pain_points_solved: list[str] = Field(default_factory=list, max_length=20)
    pricing_summary: str = Field(default="", description="Empty if pricing is not published.")
    geographies: list[str] = Field(default_factory=list, max_length=30)
    buyer_personas: list[str] = Field(default_factory=list, max_length=15)
    competitors: list[str] = Field(default_factory=list, max_length=20)

    confidence: Confidence = Confidence.MEDIUM
    evidence: list[Evidence] = Field(default_factory=list, max_length=20)
    unknowns: list[str] = Field(
        default_factory=list,
        max_length=15,
        description="What the site did not say. Prefer listing a gap over guessing.",
    )


class BuyerProfile(StrictModel):
    job_titles: list[str] = Field(default_factory=list, max_length=15)
    departments: list[str] = Field(default_factory=list, max_length=10)
    seniority: list[str] = Field(default_factory=list, max_length=10)
    responsibilities: list[str] = Field(default_factory=list, max_length=15)


class SignalType(StrEnum):
    """The observable events the platform can actually detect (PRD section 33).

    A closed vocabulary, not free text, and that is the whole point. An ICP
    whose pain signals read "they seem to be growing" can never be matched
    against anything; one that names ``hiring`` is matched by the hiring
    detector the moment that detector exists. This enum is the join between
    what a customer says they are looking for and what the signal engine
    watches for.
    """

    # Corporate
    FUNDING = "funding"
    HIRING = "hiring"
    EXPANSION = "expansion"
    ACQUISITION = "acquisition"
    NEW_OFFICE = "new_office"
    LEADERSHIP_CHANGE = "leadership_change"
    # Website
    NEW_PAGES = "new_pages"
    PRODUCT_LAUNCH = "product_launch"
    PRICING_CHANGE = "pricing_change"
    TECHNOLOGY_CHANGE = "technology_change"
    WEBSITE_CHANGE = "website_change"
    # Marketing
    ADVERTISING = "advertising"
    CONTENT_GROWTH = "content_growth"
    SOCIAL_ACTIVITY = "social_activity"
    # Sales
    PROCUREMENT = "procurement"

    OTHER = "other"


class PainSignal(StrictModel):
    """One observable event that suggests a company needs this product."""

    type: SignalType
    description: str = Field(
        max_length=300,
        description="What specifically to look for, e.g. 'hiring fleet or logistics managers'.",
    )
    why_it_matters: str = Field(
        default="",
        max_length=300,
        description="Why this event implies a need for what the customer sells.",
    )


class ICPDraft(StrictModel):
    """Generated ideal customer profile (PRD section 27)."""

    name: str = Field(default="", max_length=120)
    industries: list[str] = Field(default_factory=list, max_length=20)
    countries: list[str] = Field(default_factory=list, max_length=20)
    employee_range: str = Field(default="", description="e.g. 25-250")
    business_size: str = Field(
        default="", description="Estimated size band, e.g. SMB, mid-market, enterprise."
    )
    business_models: list[str] = Field(default_factory=list, max_length=10)
    technologies: list[str] = Field(default_factory=list, max_length=20)
    growth_stage: str = ""

    buyer: BuyerProfile = Field(default_factory=BuyerProfile)
    pain_signals: list[PainSignal] = Field(
        default_factory=list,
        max_length=20,
        description="Observable events suggesting a company needs this.",
    )

    rationale: str = Field(default="", description="Why this profile follows from the company.")
    confidence: Confidence = Confidence.MEDIUM
    evidence: list[Evidence] = Field(default_factory=list, max_length=20)


class ReplyCategory(StrEnum):
    """The twelve labels in PRD section 42."""

    INTERESTED = "interested"
    MEETING_REQUEST = "meeting_request"
    QUESTION = "question"
    OBJECTION = "objection"
    NOT_INTERESTED = "not_interested"
    UNSUBSCRIBE = "unsubscribe"
    WRONG_PERSON = "wrong_person"
    OUT_OF_OFFICE = "out_of_office"
    REFERRAL = "referral"
    SPAM = "spam"
    ANGRY = "angry"
    UNCLEAR = "unclear"


class ReplyClassification(StrictModel):
    category: ReplyCategory
    confidence: Confidence
    reasoning: str = Field(default="", max_length=500)
    # Surfaced separately because an opt-out must be honoured regardless of how
    # the rest of the reply is categorised (PRD section 63).
    contains_opt_out: bool = False
    suggested_next_step: str = ""
