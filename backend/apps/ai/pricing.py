"""Model catalogue, routing tiers and cost arithmetic (PRD section 59).

Model routing is a product requirement, not an optimisation: cheap models do
classification and extraction, strong models do research and strategy. Putting
the mapping in one table means a cost decision is a one-line change rather than
a hunt through agent code.

Both supported vendors are catalogued here, with their own tier defaults, so
switching ``AI_PROVIDER`` moves the whole product to the other vendor without
touching an agent.

Prices are USD per million tokens, stored as integer micro-dollars so cost
arithmetic never touches a float. Rates change; ``PRICING_AS_OF`` records when
this table was last checked against each vendor's published pricing.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

PRICING_AS_OF = "2026-10-08"


class Tier(StrEnum):
    """What a call is for, which decides which model answers it."""

    # Classification, extraction, formatting. High volume, low judgement.
    CHEAP = "cheap"
    # Summarising, drafting, personalisation. Needs judgement, runs often.
    STANDARD = "standard"
    # Research, strategy, scoring rationale. Low volume, high value.
    ADVANCED = "advanced"


@dataclass(frozen=True, slots=True)
class ModelSpec:
    model_id: str
    provider: str
    input_micro_usd_per_mtok: int
    output_micro_usd_per_mtok: int
    context_tokens: int
    max_output_tokens: int

    # Multipliers on the input rate. Cache reads are ~10% of input at both
    # vendors. Cache writes are charged by Anthropic and by OpenAI's largest
    # model, but not by most OpenAI models -- hence per-model rather than a
    # single global constant.
    cache_read_multiplier: Decimal = Decimal("0.1")
    cache_write_multiplier: Decimal = Decimal("0")

    #: Whether this model thinks before answering, and bills the thinking as
    #: output. It changes two things a caller must not have to know about: the
    #: output budget has to leave room for reasoning tokens, and the effort can
    #: be dialled down for work that needs no deliberation. False for a legacy
    #: model, so an override to one does not send it a parameter it rejects.
    supports_reasoning: bool = False

    def cost_micro_usd(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_write_tokens: int = 0,
        cache_read_tokens: int = 0,
    ) -> int:
        """Total cost in micro-dollars (1e-6 USD).

        ``input_tokens`` must be the *fresh* input only. Providers normalise
        this before it gets here: OpenAI reports `input_tokens` inclusive of
        cached tokens, so its provider subtracts them, while Anthropic reports
        the two separately. Getting that wrong bills a cache hit at ten times
        its real cost.
        """
        input_rate = Decimal(self.input_micro_usd_per_mtok)
        output_rate = Decimal(self.output_micro_usd_per_mtok)
        million = Decimal(1_000_000)

        total = (
            Decimal(input_tokens) * input_rate
            + Decimal(output_tokens) * output_rate
            + Decimal(cache_write_tokens) * input_rate * self.cache_write_multiplier
            + Decimal(cache_read_tokens) * input_rate * self.cache_read_multiplier
        ) / million

        return int(total.to_integral_value(rounding=ROUND_HALF_UP))


def _usd(amount: str) -> int:
    """Dollars per million tokens as integer micro-dollars."""
    return int(Decimal(amount) * 1_000_000)


# Anthropic. Model IDs are complete as written -- never append a date suffix.
_ANTHROPIC_MODELS = [
    ModelSpec(
        model_id="claude-opus-5-5",
        provider="anthropic",
        input_micro_usd_per_mtok=_usd("4.00"),
        output_micro_usd_per_mtok=_usd("20.00"),
        context_tokens=1_000_000,
        max_output_tokens=128_000,
        cache_write_multiplier=Decimal("1.25"),
        supports_reasoning=True,
    ),
    ModelSpec(
        model_id="claude-sonnet-5-5",
        provider="anthropic",
        input_micro_usd_per_mtok=_usd("2.00"),
        output_micro_usd_per_mtok=_usd("10.00"),
        context_tokens=1_000_000,
        max_output_tokens=128_000,
        cache_write_multiplier=Decimal("1.25"),
        supports_reasoning=True,
    ),
    ModelSpec(
        model_id="claude-haiku-4-5",
        provider="anthropic",
        input_micro_usd_per_mtok=_usd("1.00"),
        output_micro_usd_per_mtok=_usd("5.00"),
        context_tokens=200_000,
        max_output_tokens=64_000,
        cache_write_multiplier=Decimal("1.25"),
        supports_reasoning=True,
    ),
]

# OpenAI. Checked against developers.openai.com on PRICING_AS_OF.
_OPENAI_MODELS = [
    ModelSpec(
        model_id="gpt-5-nano",
        provider="openai",
        input_micro_usd_per_mtok=_usd("0.05"),
        output_micro_usd_per_mtok=_usd("0.40"),
        context_tokens=400_000,
        max_output_tokens=128_000,
        supports_reasoning=True,
    ),
    ModelSpec(
        model_id="gpt-5-mini",
        provider="openai",
        input_micro_usd_per_mtok=_usd("0.25"),
        output_micro_usd_per_mtok=_usd("2.00"),
        context_tokens=400_000,
        max_output_tokens=128_000,
        supports_reasoning=True,
    ),
    ModelSpec(
        model_id="gpt-5.4-nano",
        provider="openai",
        input_micro_usd_per_mtok=_usd("0.20"),
        output_micro_usd_per_mtok=_usd("1.25"),
        context_tokens=400_000,
        max_output_tokens=128_000,
        supports_reasoning=True,
    ),
    ModelSpec(
        model_id="gpt-5.4-mini",
        provider="openai",
        input_micro_usd_per_mtok=_usd("0.75"),
        output_micro_usd_per_mtok=_usd("4.50"),
        context_tokens=400_000,
        max_output_tokens=128_000,
        supports_reasoning=True,
    ),
    ModelSpec(
        model_id="gpt-5",
        provider="openai",
        input_micro_usd_per_mtok=_usd("1.25"),
        output_micro_usd_per_mtok=_usd("10.00"),
        context_tokens=400_000,
        max_output_tokens=128_000,
        supports_reasoning=True,
    ),
    ModelSpec(
        model_id="gpt-5.2",
        provider="openai",
        input_micro_usd_per_mtok=_usd("1.75"),
        output_micro_usd_per_mtok=_usd("14.00"),
        context_tokens=400_000,
        max_output_tokens=128_000,
        supports_reasoning=True,
    ),
    ModelSpec(
        model_id="gpt-6-astra",
        provider="openai",
        # Short-context rate. Requests above 272K tokens are billed at roughly
        # double; this table does not model that tier, so a long-context job
        # on Astra will be under-costed. Keep long jobs off it or extend here.
        input_micro_usd_per_mtok=_usd("10.00"),
        output_micro_usd_per_mtok=_usd("50.00"),
        context_tokens=1_050_000,
        max_output_tokens=128_000,
        cache_write_multiplier=Decimal("1.25"),
        supports_reasoning=True,
    ),
]

MODELS: dict[str, ModelSpec] = {
    spec.model_id: spec for spec in (*_ANTHROPIC_MODELS, *_OPENAI_MODELS)
}

# Per-provider routing. Overridable via AI_MODEL_* settings, so a cost ceiling
# can be imposed without a code change.
PROVIDER_TIER_DEFAULTS: dict[str, dict[Tier, str]] = {
    "anthropic": {
        Tier.CHEAP: "claude-haiku-4-5",
        Tier.STANDARD: "claude-sonnet-5-5",
        Tier.ADVANCED: "claude-opus-5-5",
    },
    "openai": {
        Tier.CHEAP: "gpt-5-nano",
        Tier.STANDARD: "gpt-5-mini",
        # The advanced tier is now reserved for calls that run *once per
        # customer*: reading their website, drafting their ICP, ranking their
        # markets. Three calls, a few cents, at the moment a stranger is
        # deciding whether this product understands their business -- which
        # is the worst possible place to save money.
        #
        # Measured, on the same eval set: gpt-5.2 scored 22/22, gpt-5-mini
        # 20/22. One of those two failures was a bad test. The other was real
        # and was the thing that matters most: shown a company whose entire
        # website said "Established 1998. Contact us", mini wrote a confident
        # reason to contact them. Every quote in it was verbatim and the whole
        # argument was invented.
        #
        # Volume is what separates this tier from the standard one below, not
        # importance. AI_MODEL_ADVANCED in backend/.env overrides it.
        Tier.ADVANCED: "gpt-5.2",
    },
}

# The stub has no models of its own; it borrows a catalogue so that cost
# arithmetic is still exercised in tests.
PROVIDER_TIER_DEFAULTS["stub"] = PROVIDER_TIER_DEFAULTS["anthropic"]


def configured_provider() -> str:
    """Which vendor is active, resolved the same way the registry resolves it."""
    import os

    from django.conf import settings

    name = (getattr(settings, "AI_PROVIDER", "") or "").strip().lower()
    if name:
        return name
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "stub"


#: How hard a model should think, by what the call is for.
#:
#: Measured, not guessed. A reply classification on gpt-5-nano spent 768 of
#: its 907 output tokens reasoning about a one-line email, which cost three
#: times what the answer did and intermittently truncated the JSON it was
#: supposed to produce. At low effort the same call uses 310 tokens and 128 of
#: them reasoning.
#:
#: Advanced stays at the vendor default: research and strategy are exactly
#: where deliberation earns its price.
REASONING_EFFORT: dict[Tier, str] = {
    Tier.CHEAP: "low",
    Tier.STANDARD: "low",
    Tier.ADVANCED: "medium",
}


def reasoning_effort_for(tier: Tier | str) -> str:
    return REASONING_EFFORT.get(Tier(tier), "")


def resolve_model(tier: Tier | str, *, provider: str | None = None) -> ModelSpec:
    """Model for a tier, honouring the active provider and any override."""
    from django.conf import settings

    tier = Tier(tier)
    provider = provider or configured_provider()

    defaults = PROVIDER_TIER_DEFAULTS.get(provider)
    if defaults is None:
        raise ValueError(
            f"No model routing defined for provider {provider!r}. "
            f"Known providers: {sorted(PROVIDER_TIER_DEFAULTS)}."
        )

    overrides: dict[str, str] = getattr(settings, "AI_MODEL_TIERS", {}) or {}
    model_id = overrides.get(str(tier)) or defaults[tier]

    spec = MODELS.get(model_id)
    if spec is None:
        raise ValueError(
            f"Unknown model {model_id!r} for tier {tier}. Add it to MODELS with its "
            "pricing before routing traffic to it, or usage will be costed as zero."
        )
    return spec


def models_for_provider(provider: str) -> list[ModelSpec]:
    return [spec for spec in MODELS.values() if spec.provider == provider]


def micro_usd_to_minor_units(micro_usd: int) -> int:
    """Micro-dollars to cents, for the billing ledger's integer minor units."""
    return int((Decimal(micro_usd) / Decimal(10_000)).to_integral_value(rounding=ROUND_HALF_UP))
