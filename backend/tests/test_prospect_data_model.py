"""Company, Person and Lead (PRD sections 30, 31, 60, 61, 80).

Three rules carry most of the weight here, and each has a cost attached when
it fails:

* **Deduplication.** Two rows for one company become two leads, two campaigns,
  and one person receiving the same message twice from the same sender.
* **Contact status is not enrichable.** A vendor asserting "verified" must
  never clear a bounce we observed or an opt-out somebody asked for.
* **Provenance is mandatory.** A row whose origin is unknown cannot be
  defended to the customer acting on it, nor dropped when a licence lapses.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.utils import timezone

from apps.common.models import ContactStatus
from apps.common.tenancy import tenant_context
from apps.companies import services as company_services
from apps.companies.models import Company, CompanyStatus, normalise_domain
from apps.contacts import services as contact_services
from apps.contacts.models import Person
from apps.leads import services as lead_services
from apps.leads.models import Lead, LeadStatus, SourceKind

pytestmark = pytest.mark.django_db


@pytest.fixture
def source(organization: Any) -> Any:
    return lead_services.get_or_create_source(
        organization=organization, name="Website crawl", kind=SourceKind.WEBSITE_CRAWL
    )


def make_company(organization: Any, **fields: Any) -> Company:
    company, _ = company_services.upsert_company(
        organization=organization,
        source="website_crawl",
        website=fields.pop("website", "https://harmattanfleet.example"),
        name=fields.pop("name", "Harmattan Fleet"),
        **fields,
    )
    return company


# --------------------------------------------------------------------------- #
# Domain normalisation and deduplication
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://www.Acme.com/about", "acme.com"),
        ("http://acme.com", "acme.com"),
        ("acme.com", "acme.com"),
        ("WWW.ACME.COM", "acme.com"),
        ("https://acme.com:8443/x?y=1", "acme.com"),
        ("https://sub.acme.com", "sub.acme.com"),
        ("", ""),
        ("not a url at all", "not a url at all"),
    ],
)
def test_domain_normalisation(raw: str, expected: str) -> None:
    assert normalise_domain(raw) == expected


def test_a_different_tld_is_a_different_company() -> None:
    """Deliberately not public-suffix aware: these are two businesses."""
    assert normalise_domain("acme.co.uk") != normalise_domain("acme.com")


def test_the_same_company_arriving_twice_is_one_row(organization: Any) -> None:
    first, created_first = company_services.upsert_company(
        organization=organization, source="csv_import", website="https://www.Acme.com/"
    )
    second, created_second = company_services.upsert_company(
        organization=organization, source="provider:x", website="http://acme.com/careers"
    )

    assert created_first and not created_second
    assert first.pk == second.pk
    assert Company.objects.filter(organization=organization).count() == 1


def test_two_tenants_may_each_hold_the_same_domain(
    organization: Any, other_organization: Any
) -> None:
    """The constraint is per organization; prospect lists are not shared."""
    company_services.upsert_company(
        organization=organization, source="import", website="https://acme.com"
    )
    theirs, created = company_services.upsert_company(
        organization=other_organization, source="import", website="https://acme.com"
    )

    assert created
    assert theirs.organization_id == other_organization.pk


def test_companies_without_a_domain_do_not_collide(organization: Any) -> None:
    """The unique constraint is partial, or every domain-less row would clash."""
    company_services.upsert_company(organization=organization, source="manual", name="One")
    company_services.upsert_company(organization=organization, source="manual", name="Two")

    assert Company.objects.filter(organization=organization, domain="").count() == 2


def test_a_second_source_fills_gaps_without_overwriting(organization: Any) -> None:
    """An importer sends blanks for every column it lacks; those must not erase."""
    company_services.upsert_company(
        organization=organization,
        source="crawl",
        website="https://acme.com",
        name="Acme",
        city="Lagos",
    )
    company, _ = company_services.upsert_company(
        organization=organization,
        source="provider",
        website="https://acme.com",
        name="Acme Logistics Ltd",
        city="",
        industry="logistics",
    )

    assert company.city == "Lagos"
    assert company.name == "Acme"
    assert company.industry == "logistics"


def test_re_seeing_a_company_refreshes_its_verification_date(organization: Any) -> None:
    """Still existing is itself information, even when nothing new is learned."""
    company = make_company(organization)
    with tenant_context(organization=organization):
        Company.objects.filter(pk=company.pk).update(
            last_verified_at=timezone.now() - timezone.timedelta(days=200)
        )
        assert Company.objects.get(pk=company.pk).is_stale

    make_company(organization)

    with tenant_context(organization=organization):
        assert not Company.objects.get(pk=company.pk).is_stale


# --------------------------------------------------------------------------- #
# Merging
# --------------------------------------------------------------------------- #


def test_merging_moves_the_history_and_keeps_the_duplicate(organization: Any, source: Any) -> None:
    """The row is not deleted: leads and conversations may already point at it."""
    primary = make_company(organization, website="https://acme.com", name="Acme")
    duplicate = make_company(organization, website="https://acme.io", name="Acme Inc", city="Lagos")
    person, _ = contact_services.upsert_person(
        organization=organization, company=duplicate, email="ada@acme.io", source="crawl"
    )
    lead_services.create_lead(organization=organization, company=duplicate, source=source)

    company_services.merge_companies(primary=primary, duplicate=duplicate)

    person.refresh_from_db()
    duplicate.refresh_from_db()
    primary.refresh_from_db()
    assert person.company_id == primary.pk
    assert duplicate.status == CompanyStatus.DUPLICATE
    assert duplicate.merged_into_id == primary.pk
    # Gaps in the survivor are filled from the record being folded in.
    assert primary.city == "Lagos"


def test_a_merged_duplicate_keeps_its_domain_but_frees_the_key(
    organization: Any,
) -> None:
    """The domain is evidence of where the company was found.

    Blanking it to satisfy an index would destroy provenance, so the
    uniqueness rule excludes merged rows instead -- and the survivor is then
    free to take that domain.
    """
    primary = make_company(organization, website="https://acme.com", name="Acme")
    duplicate = make_company(organization, website="https://acme.io", name="Acme Inc")

    company_services.merge_companies(primary=primary, duplicate=duplicate)

    duplicate.refresh_from_db()
    assert duplicate.domain == "acme.io"

    # And re-importing that old domain lands on the survivor, rather than
    # resurrecting the record it was folded into.
    resolved, created = company_services.upsert_company(
        organization=organization, source="import", website="https://acme.io"
    )
    assert not created
    assert resolved.pk == primary.pk


def test_merging_across_tenants_is_refused(organization: Any, other_organization: Any) -> None:
    mine = make_company(organization, website="https://acme.com")
    theirs = make_company(other_organization, website="https://acme.com")

    with pytest.raises(ValueError, match="different organizations"):
        company_services.merge_companies(primary=mine, duplicate=theirs)


# --------------------------------------------------------------------------- #
# Contact quality (section 60)
# --------------------------------------------------------------------------- #


def test_every_status_the_prd_names_exists() -> None:
    assert set(ContactStatus.values) == {
        "verified",
        "risky",
        "unknown",
        "invalid",
        "bounced",
        "unsubscribed",
    }


def test_an_address_is_normalised_on_save(organization: Any) -> None:
    company = make_company(organization)
    person, _ = contact_services.upsert_person(
        organization=organization, company=company, email="  Ada@Acme.COM ", source="crawl"
    )

    assert person.email == "ada@acme.com"


def test_the_same_address_in_different_case_is_one_person(organization: Any) -> None:
    company = make_company(organization)
    contact_services.upsert_person(
        organization=organization, company=company, email="ada@acme.com", source="crawl"
    )
    _, created = contact_services.upsert_person(
        organization=organization, company=company, email="ADA@acme.com", source="import"
    )

    assert not created
    assert Person.objects.filter(organization=organization).count() == 1


def test_an_unrecognised_field_is_refused_rather_than_dropped(organization: Any) -> None:
    """Found by a test that set `is_decision_maker` and watched it vanish.

    The permissive version swallowed anything not on the enrichable list, so
    a caller passing a real model field by a slightly wrong name -- or one
    that had simply never been added to the list -- got no error and no
    effect. The gap surfaces much later, as data that is quietly missing.
    """
    company = make_company(organization)

    with pytest.raises(TypeError, match="unexpected field"):
        contact_services.upsert_person(
            organization=organization,
            company=company,
            email="ada@acme.com",
            source="crawl",
            job_tittle="Operations Director",
        )


def test_a_decision_maker_can_be_promoted_but_never_demoted(organization: Any) -> None:
    """A boolean cannot follow "first writer wins".

    False and "not stated" are the same value, so the enrichment rule used for
    text fields would let an unset flag block every later source. It is
    promoted to True and then held: a provider claiming somebody is *not* a
    decision maker is not grounds to discard a judgement made here, which is
    the same asymmetry email status uses.
    """
    company = make_company(organization)
    person, _ = contact_services.upsert_person(
        organization=organization, company=company, email="ada@acme.com", source="crawl"
    )
    assert person.is_decision_maker is False

    contact_services.upsert_person(
        organization=organization,
        company=company,
        email="ada@acme.com",
        source="provider:acme",
        is_decision_maker=True,
    )
    person.refresh_from_db()
    assert person.is_decision_maker is True

    contact_services.upsert_person(
        organization=organization,
        company=company,
        email="ada@acme.com",
        source="provider:other",
        is_decision_maker=False,
    )
    person.refresh_from_db()
    assert person.is_decision_maker is True


def test_a_decision_maker_flag_is_kept_on_creation(organization: Any) -> None:
    company = make_company(organization)
    person, created = contact_services.upsert_person(
        organization=organization,
        company=company,
        email="ceo@acme.com",
        source="crawl",
        job_title="Chief Executive",
        is_decision_maker=True,
    )

    assert created is True
    assert person.is_decision_maker is True


def test_a_vendor_cannot_clear_a_bounce(organization: Any) -> None:
    """The bounce is something we observed; the vendor's claim is not evidence."""
    company = make_company(organization)
    person, _ = contact_services.upsert_person(
        organization=organization, company=company, email="ada@acme.com", source="crawl"
    )
    person.mark_bounced()

    contact_services.upsert_person(
        organization=organization,
        company=company,
        email="ada@acme.com",
        source="provider:x",
        email_status=ContactStatus.VERIFIED,
    )

    person.refresh_from_db()
    assert person.email_status == ContactStatus.BOUNCED


def test_a_vendor_cannot_clear_an_unsubscribe(organization: Any) -> None:
    """Section 63 makes this a compliance obligation, not a data-quality field."""
    company = make_company(organization)
    person, _ = contact_services.upsert_person(
        organization=organization, company=company, email="ada@acme.com", source="crawl"
    )
    person.mark_unsubscribed()

    contact_services.upsert_person(
        organization=organization,
        company=company,
        email="ada@acme.com",
        source="provider:x",
        email_status=ContactStatus.VERIFIED,
    )

    person.refresh_from_db()
    assert person.email_status == ContactStatus.UNSUBSCRIBED
    assert not person.can_be_emailed


def test_a_worse_status_is_applied(organization: Any) -> None:
    """Downgrades travel; upgrades do not."""
    company = make_company(organization)
    person, _ = contact_services.upsert_person(
        organization=organization, company=company, email="ada@acme.com", source="crawl"
    )

    contact_services.upsert_person(
        organization=organization,
        company=company,
        email="ada@acme.com",
        source="verifier",
        email_status=ContactStatus.INVALID,
    )

    person.refresh_from_db()
    assert person.email_status == ContactStatus.INVALID


def test_verifying_a_bounced_address_is_refused(organization: Any) -> None:
    company = make_company(organization)
    person, _ = contact_services.upsert_person(
        organization=organization, company=company, email="ada@acme.com", source="crawl"
    )
    person.mark_bounced()

    with pytest.raises(ValueError, match="not reversible"):
        contact_services.mark_verified(person=person)


@pytest.mark.parametrize(
    ("status", "sendable"),
    [
        (ContactStatus.VERIFIED, True),
        (ContactStatus.UNKNOWN, True),
        (ContactStatus.RISKY, True),
        (ContactStatus.INVALID, False),
        (ContactStatus.BOUNCED, False),
        (ContactStatus.UNSUBSCRIBED, False),
    ],
)
def test_which_statuses_may_be_contacted(organization: Any, status: str, sendable: bool) -> None:
    """One place to ask, so no caller has to remember six values."""
    company = make_company(organization)
    person, _ = contact_services.upsert_person(
        organization=organization,
        company=company,
        email="ada@acme.com",
        source="crawl",
        email_status=status,
    )

    assert person.can_be_emailed is sendable


def test_a_person_with_no_address_cannot_be_emailed(organization: Any) -> None:
    company = make_company(organization)
    person, _ = contact_services.upsert_person(
        organization=organization, company=company, source="crawl", full_name="Ada"
    )

    assert not person.can_be_emailed


# --------------------------------------------------------------------------- #
# Provenance (section 61)
# --------------------------------------------------------------------------- #


def test_every_record_carries_where_it_came_from(organization: Any) -> None:
    company = make_company(organization)

    assert company.source == "website_crawl"
    assert company.collected_at is not None
    assert company.confidence


def test_a_record_with_no_dates_counts_as_stale(organization: Any) -> None:
    """Unknown freshness is not the same as fresh."""
    with tenant_context(organization=organization):
        company = Company.objects.create(organization=organization, name="Unsourced")

    assert company.is_stale


def test_a_provider_source_needs_legal_review(organization: Any) -> None:
    """Section 61: usage rights must be reviewable, not remembered."""
    provider = lead_services.get_or_create_source(
        organization=organization, name="Acme Data", kind=SourceKind.PROVIDER
    )

    assert provider.needs_legal_review


def test_a_reviewed_provider_does_not(organization: Any) -> None:
    provider = lead_services.get_or_create_source(
        organization=organization,
        name="Acme Data",
        kind=SourceKind.PROVIDER,
        legal_review_at=timezone.now(),
        usage_license="Per MSA 2026-04, B2B outreach only",
    )

    assert not provider.needs_legal_review


def test_an_expired_licence_needs_review_again(organization: Any) -> None:
    provider = lead_services.get_or_create_source(
        organization=organization,
        name="Acme Data",
        kind=SourceKind.PROVIDER,
        legal_review_at=timezone.now() - timezone.timedelta(days=400),
        license_expires_at=timezone.now() - timezone.timedelta(days=1),
    )

    assert provider.needs_legal_review


def test_a_crawl_is_not_a_licensed_provider(organization: Any, source: Any) -> None:
    """Flagging these too would make the flag meaningless through noise."""
    assert not source.needs_legal_review


# --------------------------------------------------------------------------- #
# Leads
# --------------------------------------------------------------------------- #


def test_one_lead_per_company_per_icp(organization: Any, source: Any) -> None:
    company = make_company(organization)

    _, first = lead_services.create_lead(organization=organization, company=company, source=source)
    _, second = lead_services.create_lead(organization=organization, company=company, source=source)

    assert first and not second
    assert Lead.objects.filter(organization=organization).count() == 1


def test_the_same_company_may_be_a_lead_under_two_icps(organization: Any, source: Any) -> None:
    """Different reasoning, different score; not a duplicate."""
    from apps.intelligence.models import ICP

    company = make_company(organization)
    with tenant_context(organization=organization):
        first_icp = ICP.objects.create(organization=organization, name="Fleets")
        second_icp = ICP.objects.create(organization=organization, name="Distributors")

    lead_services.create_lead(
        organization=organization, company=company, source=source, icp=first_icp
    )
    _, created = lead_services.create_lead(
        organization=organization, company=company, source=source, icp=second_icp
    )

    assert created
    assert Lead.objects.filter(organization=organization, company=company).count() == 2


def test_rediscovery_does_not_undo_a_qualification(organization: Any, source: Any) -> None:
    """Discovery is not entitled to reset work a human has done."""
    company = make_company(organization)
    lead, _ = lead_services.create_lead(organization=organization, company=company, source=source)
    with tenant_context(organization=organization):
        lead.status = LeadStatus.QUALIFIED
        lead.save(update_fields=["status"])

    lead_services.create_lead(organization=organization, company=company, source=source)

    lead.refresh_from_db()
    assert lead.status == LeadStatus.QUALIFIED


def test_disqualifying_keeps_the_record_and_the_reason(organization: Any, source: Any) -> None:
    """Without it the next run surfaces the company again, to the same conclusion."""
    company = make_company(organization)
    lead, _ = lead_services.create_lead(organization=organization, company=company, source=source)

    lead_services.disqualify(lead=lead, reason="Already a customer of ours")

    lead.refresh_from_db()
    assert lead.status == LeadStatus.DISQUALIFIED
    assert lead.disqualified_reason == "Already a customer of ours"
    assert not lead.is_contactable


def test_a_lead_is_contactable_only_with_a_sendable_contact(organization: Any, source: Any) -> None:
    company = make_company(organization)
    person, _ = contact_services.upsert_person(
        organization=organization,
        company=company,
        email="ada@acme.com",
        source="crawl",
        email_status=ContactStatus.VERIFIED,
    )
    lead, _ = lead_services.create_lead(
        organization=organization, company=company, source=source, person=person
    )

    assert lead.is_contactable

    person.mark_unsubscribed()
    lead.refresh_from_db()
    assert not lead.is_contactable


def test_a_source_cannot_be_deleted_while_leads_reference_it(
    organization: Any, source: Any
) -> None:
    """Section 61 again: the origin has to remain answerable."""
    from django.db.models import ProtectedError

    company = make_company(organization)
    lead_services.create_lead(organization=organization, company=company, source=source)

    with pytest.raises(ProtectedError):
        source.delete()
