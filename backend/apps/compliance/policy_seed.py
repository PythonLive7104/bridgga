"""Regional policy seed data (PRD section 62).

Section 62 asks for configurable policies for Nigeria, Kenya, South Africa,
the EU, the UK, the US and other markets. These are the starting values.

**They are a starting point for a legal review, not the review.** The PRD says
so in its own words -- "legal review is required before production use" -- and
the notes on each row name what a reviewer should look at. The value of
writing them down is that the product behaves conservatively by default and
that the assumptions are visible and arguable rather than buried in whoever
wrote the send path.

The pattern throughout: where a regime is unclear or contested, the stricter
reading is recorded. A customer who is told they need consent they do not
legally need loses a little reach. One told the opposite loses a lot more.
"""

from __future__ import annotations

from typing import Any

#: Written as plain data so a lawyer can read the table without reading code.
POLICIES: list[dict[str, Any]] = [
    {
        "code": "NG",
        "name": "Nigeria",
        "law": "Nigeria Data Protection Act 2023 (NDPA), NDPR",
        "b2b_requires_prior_consent": False,
        "opt_out_required": True,
        "sender_identity_required": True,
        "postal_address_required": False,
        "opt_out_honoured_within_days": 7,
        "max_retention_days": 0,
        "notes": (
            "The NDPA recognises legitimate interest as a lawful basis, which is "
            "the usual basis for B2B outbound. Published business contact details "
            "are generally usable; personal addresses are not. Review before any "
            "large-scale enrichment."
        ),
    },
    {
        "code": "KE",
        "name": "Kenya",
        "law": "Data Protection Act 2019",
        "b2b_requires_prior_consent": False,
        "opt_out_required": True,
        "sender_identity_required": True,
        "postal_address_required": False,
        "opt_out_honoured_within_days": 7,
        "max_retention_days": 0,
        "notes": (
            "Direct marketing requires an opt-out in every message and the data "
            "subject may object at any time. Registration as a data controller "
            "may be required depending on volume."
        ),
    },
    {
        "code": "ZA",
        "name": "South Africa",
        "law": "POPIA, and the ECT Act for electronic marketing",
        # POPIA section 69 is the strict one: direct electronic marketing to a
        # person who is not an existing customer generally needs prior
        # consent, and consent may be requested only once.
        "b2b_requires_prior_consent": True,
        "opt_out_required": True,
        "sender_identity_required": True,
        "postal_address_required": False,
        "opt_out_honoured_within_days": 0,
        "max_retention_days": 0,
        "notes": (
            "POPIA s69 restricts unsolicited electronic direct marketing to "
            "non-customers, and permits a single consent request. Treat cold "
            "outbound to South African individuals as consent-required. "
            "Juristic persons are treated differently; confirm with counsel."
        ),
    },
    {
        "code": "GH",
        "name": "Ghana",
        "law": "Data Protection Act 2012 (Act 843)",
        "b2b_requires_prior_consent": False,
        "opt_out_required": True,
        "sender_identity_required": True,
        "postal_address_required": False,
        "opt_out_honoured_within_days": 7,
        "max_retention_days": 0,
        "notes": "Registration with the Data Protection Commission may be required.",
    },
    {
        "code": "EG",
        "name": "Egypt",
        "law": "Personal Data Protection Law No. 151 of 2020",
        "b2b_requires_prior_consent": True,
        "opt_out_required": True,
        "sender_identity_required": True,
        "postal_address_required": False,
        "opt_out_honoured_within_days": 0,
        "max_retention_days": 0,
        "notes": (
            "Electronic direct marketing requires prior consent and a licence "
            "regime applies to processing. Treat as consent-required."
        ),
    },
    {
        "code": "EU",
        "name": "European Union",
        "law": "GDPR and the ePrivacy Directive",
        # ePrivacy allows a B2B carve-out in some member states and not in
        # others. The stricter reading is recorded deliberately.
        "b2b_requires_prior_consent": True,
        "opt_out_required": True,
        "sender_identity_required": True,
        "postal_address_required": False,
        "opt_out_honoured_within_days": 0,
        "max_retention_days": 1_095,
        "notes": (
            "ePrivacy is implemented per member state: several permit B2B email "
            "on legitimate interest, others require consent. The strict setting "
            "is recorded until a per-country review says otherwise. GDPR "
            "transparency and access rights apply regardless of basis."
        ),
    },
    {
        "code": "GB",
        "name": "United Kingdom",
        "law": "UK GDPR and PECR",
        # PECR permits unsolicited B2B email to corporate subscribers, with an
        # opt-out. Sole traders and partnerships are treated as individuals.
        "b2b_requires_prior_consent": False,
        "opt_out_required": True,
        "sender_identity_required": True,
        "postal_address_required": False,
        "opt_out_honoured_within_days": 0,
        "max_retention_days": 1_095,
        "notes": (
            "PECR allows B2B email to corporate subscribers without prior "
            "consent, with identification and an opt-out. Sole traders and "
            "unincorporated partnerships count as individuals and do need "
            "consent."
        ),
    },
    {
        "code": "US",
        "name": "United States",
        "law": "CAN-SPAM, plus state privacy laws",
        "b2b_requires_prior_consent": False,
        "opt_out_required": True,
        "sender_identity_required": True,
        # The one regime that requires it explicitly, which is why the field
        # exists at all.
        "postal_address_required": True,
        "opt_out_honoured_within_days": 10,
        "max_retention_days": 0,
        "notes": (
            "CAN-SPAM is opt-out: a valid physical postal address, honest "
            "headers and subject, and opt-outs honoured within 10 business "
            "days. State laws (CCPA and successors) add access and deletion "
            "rights for residents."
        ),
    },
    {
        "code": "CA",
        "name": "Canada",
        "law": "CASL",
        # The strictest of the common markets, and the one most often missed.
        "b2b_requires_prior_consent": True,
        "opt_out_required": True,
        "sender_identity_required": True,
        "postal_address_required": True,
        "opt_out_honoured_within_days": 10,
        "max_retention_days": 0,
        "notes": (
            "CASL requires express or implied consent before a commercial "
            "electronic message, with significant penalties. Do not send cold "
            "outbound to Canadian recipients without a reviewed basis."
        ),
    },
]


def seed_policies() -> dict[str, int]:
    """Write the table. Idempotent, so it can run on every deploy."""
    from apps.compliance.models import RegionalPolicy

    created = updated = 0
    for entry in POLICIES:
        _, was_created = RegionalPolicy.objects.update_or_create(
            code=entry["code"],
            defaults={key: value for key, value in entry.items() if key != "code"},
        )
        created += int(was_created)
        updated += int(not was_created)
    return {"created": created, "updated": updated}


__all__ = ["POLICIES", "seed_policies"]
