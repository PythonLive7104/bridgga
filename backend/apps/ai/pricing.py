"""Model catalogue, routing tiers and cost arithmetic (PRD section 59).

Model routing is a product requirement, not an optimisation: cheap models do
classification and extraction, strong models do research and strategy. Putting
the mapping in one table means a cost decision is a one-line change rather than
a hunt through agent code.

Prices are USD per million tokens, stored as integer micro-dollars so cost
arithmetic never touches a float. Rates change, so ``as_of`` records when this
table was last checked.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

PRICING_AS_OF = "2026-09-25"

# Cache economics, applied as multipliers on the input rate.
CACHE_WRITE_MULTIPLIER = Decimal("1.25")
CACHE_READ_MULTIPLIER = Decimal("0.1")


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
    input_micro_usd_per_mtok: int
    output_micro_usd_per_mtok: int
    context_tokens: int
    max_output_tokens: int

    def cost_micro_usd(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_write_tokens: int = 0,
        cache_read_tokens: int = 0,
    ) -> int:
        """Total cost in micro-dollars (1e-6 USD).

        Cached reads and writes are priced off the input rate rather than
        counted as ordinary input, because a cache hit is roughly a tenth of
        the price and ignoring that overstates spend by an order of magnitude
        on a prompt-cached workload.
        """
        input_rate = Decimal(self.input_micro_usd_per_mtok)
        output_rate = Decimal(self.output_micro_usd_per_mtok)
        million = Decimal(1_000_000)

        total = (
            Decimal(input_tokens) * input_rate
            + Decimal(output_tokens) * output_rate
            + Decimal(cache_write_tokens) * input_rate * CACHE_WRITE_MULTIPLIER
            + Decimal(cache_read_tokens) * input_rate * CACHE_READ_MULTIPLIER
        ) / million

        return int(total.to_integral_value(rounding="ROUND_HALF_UP"))


# Claude model IDs are complete as written -- never append a date suffix.
MODELS: dict[str, ModelSpec] = {
    "claude-opus-5-5": ModelSpec(
        model_id="claude-opus-5-5",
        input_micro_usd_per_mtok=4_000_000,
        output_micro_usd_per_mtok=20_000_000,
        context_tokens=1_000_000,
        max_output_tokens=128_000,
    ),
    "claude-sonnet-5-5": ModelSpec(
        model_id="claude-sonnet-5-5",
        input_micro_usd_per_mtok=2_000_000,
        output_micro_usd_per_mtok=10_000_000,
        context_tokens=1_000_000,
        max_output_tokens=128_000,
    ),
    "claude-haiku-4-5": ModelSpec(
        model_id="claude-haiku-4-5",
        input_micro_usd_per_mtok=1_000_000,
        output_micro_usd_per_mtok=5_000_000,
        context_tokens=200_000,
        max_output_tokens=64_000,
    ),
}

# Routing table. Overridable per deployment via AI_MODEL_TIERS in settings, so
# a cost ceiling can be imposed without a code change.
DEFAULT_TIER_MODELS: dict[Tier, str] = {
    Tier.CHEAP: "claude-haiku-4-5",
    Tier.STANDARD: "claude-sonnet-5-5",
    Tier.ADVANCED: "claude-opus-5-5",
}


def resolve_model(tier: Tier | str) -> ModelSpec:
    """Model for a tier, honouring any settings override."""
    from django.conf import settings

    tier = Tier(tier)
    overrides: dict[str, str] = getattr(settings, "AI_MODEL_TIERS", {}) or {}
    model_id = overrides.get(str(tier)) or DEFAULT_TIER_MODELS[tier]

    spec = MODELS.get(model_id)
    if spec is None:
        raise ValueError(
            f"Unknown model {model_id!r} for tier {tier}. Add it to MODELS with its "
            "pricing before routing traffic to it, or usage will be costed as zero."
        )
    return spec


def micro_usd_to_minor_units(micro_usd: int) -> int:
    """Micro-dollars to cents, for the billing ledger's integer minor units."""
    return int(
        (Decimal(micro_usd) / Decimal(10_000)).to_integral_value(rounding="ROUND_HALF_UP")
    )
