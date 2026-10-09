"""Seed data for the ten launch markets (PRD sections 30, 70, 71, 72).

These are facts, so they are written down rather than generated. A currency
code, a timezone or the name of a data-protection statute is something to look
up; asking a model for it buys a plausible answer with no source.

Two deliberate limits on what is claimed here:

* **Channel preferences** are stated by the PRD itself for Nigeria, Kenya and
  South Africa (section 70). The rest follow the same pattern for countries
  with comparable WhatsApp-for-business usage, and are marked as a starting
  point in ``communication_notes`` rather than presented as researched fact.
  They are editable, and the channel engine in Phase 5 is where they get
  properly grounded.
* **Regulatory references** are the name of the governing statute and nothing
  more. They are a pointer for the legal review that PRD section 62 requires
  before production, not a substitute for it, and no field here says whether
  any particular outreach is lawful.
"""

from __future__ import annotations

from typing import Any

# Phrasing reused where the PRD does not state a preference, so the hedge is
# visible in the data rather than buried in this module's docstring.
_UNVERIFIED = (
    "Starting point, not researched preference. Confirm against local practice "
    "before relying on the ordering."
)

_PRD_STATED = "Stated in PRD section 70."

LAUNCH_MARKETS: list[dict[str, Any]] = [
    {
        "code": "NG",
        "name": "Nigeria",
        "region": "West Africa",
        "currency": "NGN",
        "languages": ["English"],
        "timezones": ["Africa/Lagos"],
        "major_industries": [
            "fintech",
            "logistics",
            "oil and gas",
            "agriculture",
            "telecommunications",
            "entertainment",
        ],
        "business_hubs": ["Lagos", "Abuja", "Port Harcourt", "Ibadan", "Kano"],
        "channels": ["email", "whatsapp"],
        "communication_notes": _PRD_STATED,
        "data_protection_law": "Nigeria Data Protection Act 2023 (NDPA)",
    },
    {
        "code": "KE",
        "name": "Kenya",
        "region": "East Africa",
        "currency": "KES",
        "languages": ["English", "Swahili"],
        "timezones": ["Africa/Nairobi"],
        "major_industries": [
            "fintech",
            "agriculture",
            "logistics",
            "tourism",
            "manufacturing",
            "technology services",
        ],
        "business_hubs": ["Nairobi", "Mombasa", "Kisumu", "Nakuru"],
        "channels": ["email", "whatsapp"],
        "communication_notes": _PRD_STATED,
        "data_protection_law": "Data Protection Act 2019",
    },
    {
        "code": "GH",
        "name": "Ghana",
        "region": "West Africa",
        "currency": "GHS",
        "languages": ["English"],
        "timezones": ["Africa/Accra"],
        "major_industries": [
            "mining",
            "agriculture",
            "fintech",
            "logistics",
            "energy",
        ],
        "business_hubs": ["Accra", "Kumasi", "Takoradi", "Tema"],
        "channels": ["email", "whatsapp"],
        "communication_notes": _UNVERIFIED,
        "data_protection_law": "Data Protection Act 2012 (Act 843)",
    },
    {
        "code": "ZA",
        "name": "South Africa",
        "region": "Southern Africa",
        "currency": "ZAR",
        "languages": ["English", "Afrikaans", "Zulu", "Xhosa"],
        "timezones": ["Africa/Johannesburg"],
        "major_industries": [
            "financial services",
            "mining",
            "manufacturing",
            "retail",
            "technology services",
            "logistics",
        ],
        "business_hubs": ["Johannesburg", "Cape Town", "Durban", "Pretoria"],
        "channels": ["email", "linkedin"],
        "communication_notes": _PRD_STATED,
        "data_protection_law": "Protection of Personal Information Act 2013 (POPIA)",
    },
    {
        "code": "EG",
        "name": "Egypt",
        "region": "North Africa",
        "currency": "EGP",
        "languages": ["Arabic", "English"],
        "timezones": ["Africa/Cairo"],
        "major_industries": [
            "manufacturing",
            "tourism",
            "construction",
            "agriculture",
            "technology services",
            "logistics",
        ],
        "business_hubs": ["Cairo", "Alexandria", "Giza", "Port Said"],
        "channels": ["email", "whatsapp"],
        "communication_notes": _UNVERIFIED,
        "data_protection_law": "Personal Data Protection Law No. 151 of 2020",
    },
    {
        "code": "RW",
        "name": "Rwanda",
        "region": "East Africa",
        "currency": "RWF",
        "languages": ["Kinyarwanda", "English", "French"],
        "timezones": ["Africa/Kigali"],
        "major_industries": [
            "technology services",
            "agriculture",
            "tourism",
            "construction",
            "financial services",
        ],
        "business_hubs": ["Kigali"],
        "channels": ["email", "whatsapp"],
        "communication_notes": _UNVERIFIED,
        "data_protection_law": "Law No. 058/2021 on the protection of personal data and privacy",
    },
    {
        "code": "UG",
        "name": "Uganda",
        "region": "East Africa",
        "currency": "UGX",
        "languages": ["English", "Swahili"],
        "timezones": ["Africa/Kampala"],
        "major_industries": [
            "agriculture",
            "logistics",
            "construction",
            "financial services",
            "telecommunications",
        ],
        "business_hubs": ["Kampala", "Entebbe", "Jinja"],
        "channels": ["email", "whatsapp"],
        "communication_notes": _UNVERIFIED,
        "data_protection_law": "Data Protection and Privacy Act 2019",
    },
    {
        "code": "TZ",
        "name": "Tanzania",
        "region": "East Africa",
        "currency": "TZS",
        "languages": ["Swahili", "English"],
        "timezones": ["Africa/Dar_es_Salaam"],
        "major_industries": [
            "agriculture",
            "mining",
            "tourism",
            "logistics",
            "manufacturing",
        ],
        "business_hubs": ["Dar es Salaam", "Dodoma", "Arusha", "Mwanza"],
        "channels": ["email", "whatsapp"],
        "communication_notes": _UNVERIFIED,
        "data_protection_law": "Personal Data Protection Act 2022",
    },
    {
        "code": "SN",
        "name": "Senegal",
        "region": "West Africa",
        "currency": "XOF",
        "languages": ["French", "Wolof"],
        "timezones": ["Africa/Dakar"],
        "major_industries": [
            "agriculture",
            "fishing",
            "mining",
            "telecommunications",
            "logistics",
        ],
        "business_hubs": ["Dakar", "Thiès", "Saint-Louis"],
        "channels": ["email", "whatsapp"],
        "communication_notes": (
            f"{_UNVERIFIED} French-language outreach: see PRD section 113 for locale-aware "
            "generation."
        ),
        "data_protection_law": "Loi n° 2008-12 sur la protection des données à caractère personnel",
    },
    {
        "code": "CI",
        "name": "Côte d'Ivoire",
        "region": "West Africa",
        "currency": "XOF",
        "languages": ["French"],
        "timezones": ["Africa/Abidjan"],
        "major_industries": [
            "agriculture",
            "logistics",
            "energy",
            "financial services",
            "manufacturing",
        ],
        "business_hubs": ["Abidjan", "Yamoussoukro", "Bouaké"],
        "channels": ["email", "whatsapp"],
        "communication_notes": (
            f"{_UNVERIFIED} French-language outreach: see PRD section 113 for locale-aware "
            "generation."
        ),
        "data_protection_law": (
            "Loi n° 2013-450 relative à la protection des données à caractère personnel"
        ),
    },
]

#: Markets the product sells *into* from Africa (PRD section 6.2). Seeded so a
#: recommendation can name them, with no claim about local practice.
INTERNATIONAL_MARKETS: list[dict[str, Any]] = [
    {
        "code": "US",
        "name": "United States",
        "region": "North America",
        "currency": "USD",
        "languages": ["English"],
        "timezones": ["America/New_York", "America/Chicago", "America/Los_Angeles"],
        "channels": ["email", "linkedin"],
        "data_protection_law": "State-level (CCPA/CPRA in California); CAN-SPAM for email",
    },
    {
        "code": "GB",
        "name": "United Kingdom",
        "region": "Europe",
        "currency": "GBP",
        "languages": ["English"],
        "timezones": ["Europe/London"],
        "channels": ["email", "linkedin"],
        "data_protection_law": "UK GDPR and the Data Protection Act 2018; PECR for marketing",
    },
    {
        "code": "FR",
        "name": "France",
        "region": "Europe",
        "currency": "EUR",
        "languages": ["French"],
        "timezones": ["Europe/Paris"],
        "channels": ["email"],
        "communication_notes": _PRD_STATED,
        "data_protection_law": "GDPR, enforced by the CNIL",
    },
]


def all_seed_countries() -> list[dict[str, Any]]:
    launch = [{**entry, "is_launch_market": True} for entry in LAUNCH_MARKETS]
    international = [{**entry, "is_launch_market": False} for entry in INTERNATIONAL_MARKETS]
    return launch + international
