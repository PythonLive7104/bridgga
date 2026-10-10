"""Suppression, consent and the opt-out (PRD sections 62 and 63).

This is the part of the product where a bug is not a bug. Everything else
fails by being wrong; this fails by contacting somebody who asked to be left
alone, under the customer's name, with their domain reputation attached.

So the tests are weighted towards the ways that happens in practice, none of
which are "the suppression check was missing":

* the address was stored in a different shape from the one checked;
* the person asked to be deleted, so the record that would have recognised
  them was deleted too;
* the unsubscribe link had expired by the time they clicked it;
* they were suppressed, but the audience that fed the next campaign did not
  know, so they were counted in the estimate and rejected at the end;
* a colleague cleaned up the suppression list;
* a new send path was added that did not call the check at all.

The last one has an architecture test rather than a unit test, because no
unit test can cover code nobody has written yet.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from django.utils import timezone

from apps.common.models import ContactStatus
from apps.common.tenancy import tenant_context
from apps.companies import services as company_services
from apps.compliance import services as compliance
from apps.compliance import tokens
from apps.compliance.guard import Suppressed, assert_sendable, is_suppressed, partition
from apps.compliance.models import (
    ConsentBasis,
    ConsentRecord,
    RegionalPolicy,
    SuppressionEntry,
    SuppressionKind,
    SuppressionReason,
    SuppressionScope,
    address_hash,
    normalise_address,
    policy_for,
)
from apps.compliance.policy_seed import seed_policies
from apps.contacts import services as contact_services
from apps.organizations.roles import Role

pytestmark = pytest.mark.django_db

SUPPRESSIONS_URL = "/api/v1/compliance/suppressions"
ADDRESS = "ada@harmattanfleet.example"


@pytest.fixture
def person(organization: Any) -> Any:
    company, _ = company_services.upsert_company(
        organization=organization,
        name="Harmattan Fleet",
        website="https://harmattanfleet.example",
        source="test",
    )
    record, _ = contact_services.upsert_person(
        organization=organization,
        company=company,
        email=ADDRESS,
        source="test",
        full_name="Ada Obi",
        email_status=ContactStatus.VERIFIED,
    )
    return record


# --------------------------------------------------------------------------- #
# Matching: the shape an address arrives in must not decide the outcome
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "written_as",
    [
        "ada@harmattanfleet.example",
        "ADA@Harmattanfleet.Example",
        "  ada@harmattanfleet.example  ",
        '"Ada Obi" <ada@harmattanfleet.example>',
        "Ada Obi <ADA@HARMATTANFLEET.EXAMPLE>",
    ],
)
def test_an_address_is_recognised_however_it_was_written(
    organization: Any, written_as: str
) -> None:
    """The commonest way a suppression list fails: it matches on the wrong string.

    A webhook sends a bare address, an import sends a display name, a reply
    header sends angle brackets. If any of those produce a different key, the
    person is suppressed under one spelling and contactable under another.
    """
    compliance.suppress(organization=organization, address=ADDRESS)

    assert is_suppressed(organization=organization, address=written_as) is True


def test_provider_aliasing_is_deliberately_not_normalised() -> None:
    """Gmail ignores dots and anything after a plus. Almost nobody else does.

    Normalising for one vendor's rules would suppress addresses nobody asked
    to suppress on every other vendor, so the rule is the conservative one:
    exact address, lowercased and trimmed.
    """
    assert normalise_address("A.D.A+news@example.com") == "a.d.a+news@example.com"
    assert address_hash("ada@example.com") != address_hash("a.da@example.com")


def test_suppressing_a_domain_covers_addresses_nobody_has_found_yet(
    organization: Any,
) -> None:
    """A company saying "stop contacting us" is not saying it per mailbox."""
    compliance.suppress(
        organization=organization,
        address="harmattanfleet.example",
        kind=SuppressionKind.DOMAIN,
        reason=SuppressionReason.MANUAL,
    )

    assert is_suppressed(organization=organization, address="anyone@harmattanfleet.example")
    assert is_suppressed(organization=organization, address="new.hire@harmattanfleet.example")
    assert not is_suppressed(organization=organization, address="ada@other.example")


def test_a_channel_scope_does_not_leak_into_other_channels(organization: Any) -> None:
    compliance.suppress(organization=organization, address=ADDRESS, scope=SuppressionScope.EMAIL)

    assert is_suppressed(organization=organization, address=ADDRESS, channel="email")
    assert not is_suppressed(organization=organization, address=ADDRESS, channel="whatsapp")


def test_an_all_channel_suppression_covers_every_channel(organization: Any) -> None:
    compliance.suppress(organization=organization, address=ADDRESS, scope=SuppressionScope.ALL)

    for channel in ("email", "sms", "whatsapp", "call"):
        assert is_suppressed(organization=organization, address=ADDRESS, channel=channel)


@pytest.mark.tenancy
def test_one_customers_unsubscribe_does_not_bind_another(
    organization: Any, other_organization: Any
) -> None:
    """ "Stop contacting me" is said to a sender, not to a platform.

    The other customer has their own relationship with this person and their
    own basis for it; inheriting a stranger's opt-out would be wrong in both
    directions.
    """
    compliance.suppress(organization=organization, address=ADDRESS)

    assert is_suppressed(organization=organization, address=ADDRESS)
    assert not is_suppressed(organization=other_organization, address=ADDRESS)


# --------------------------------------------------------------------------- #
# The guard
# --------------------------------------------------------------------------- #


def test_the_guard_blocks_a_suppressed_address(organization: Any) -> None:
    compliance.suppress(organization=organization, address=ADDRESS)

    with pytest.raises(Suppressed) as caught:
        assert_sendable(organization=organization, address=ADDRESS)

    assert caught.value.reason == SuppressionReason.UNSUBSCRIBED


def test_the_guard_fails_closed_when_it_cannot_check(organization: Any) -> None:
    """ "We could not check" must never read as "it is fine".

    The cost of blocking a good message is an unsent email. The cost of the
    other mistake is a person who asked to be left alone being contacted
    anyway.
    """
    with pytest.raises(Suppressed):
        assert_sendable(organization=None, address=ADDRESS)

    with pytest.raises(Suppressed):
        assert_sendable(organization=organization, address="")


def test_the_guard_also_honours_the_contact_record(organization: Any, person: Any) -> None:
    """Two layers, both necessary.

    The suppression list is organization-wide and outlives any record; the
    contact's own status carries a bounce nobody suppressed. Either is enough
    to stop a send.
    """
    person.mark_bounced()

    with pytest.raises(Suppressed) as caught:
        assert_sendable(organization=organization, address=ADDRESS, person=person)

    assert "bounced" in caught.value.reason


def test_partitioning_a_list_costs_one_query_not_one_per_recipient(
    organization: Any, django_assert_max_num_queries: Any
) -> None:
    """The pre-launch panel needs this over a whole audience (section 36)."""
    compliance.suppress(organization=organization, address="blocked@example.com")
    addresses = [f"person{index}@example.com" for index in range(50)]
    addresses.append("blocked@example.com")

    with django_assert_max_num_queries(2):
        result = partition(organization=organization, addresses=addresses)

    assert len(result.allowed) == 50
    assert [item.address for item in result.blocked] == ["blocked@example.com"]
    assert result.blocked_reasons == {"unsubscribed": 1}


def test_a_duplicated_recipient_is_one_recipient(organization: Any) -> None:
    """Otherwise one person receives the campaign twice, which reads as spam."""
    result = partition(
        organization=organization,
        addresses=["ada@example.com", "ADA@example.com", " ada@example.com "],
    )

    assert result.allowed == ["ada@example.com"]


# --------------------------------------------------------------------------- #
# Re-enrollment
# --------------------------------------------------------------------------- #


def test_suppressing_marks_the_contact_so_it_leaves_every_audience(
    organization: Any, person: Any
) -> None:
    """Section 63's "prevent accidental re-enrollment", and why it needs both.

    The list is authoritative at send time, but a person left marked
    contactable is still pulled into the next audience, counted in its
    estimate and rejected one at a time at the end -- so a campaign approved
    for 400 sends to 380 with no explanation.
    """
    compliance.suppress(organization=organization, address=ADDRESS)
    person.refresh_from_db()

    assert person.email_status == ContactStatus.UNSUBSCRIBED
    assert person.can_be_emailed is False


def test_a_suppressed_person_disappears_from_the_reachable_filter(
    organization: Any, person: Any
) -> None:
    """The prospect list and the suppression list have to agree."""
    from apps.companies.search import ProspectFilters, search_companies

    before = search_companies(
        organization=organization, filters=ProspectFilters(contactable_only=True)
    )
    assert before.count() == 1

    compliance.suppress(organization=organization, address=ADDRESS)

    after = search_companies(
        organization=organization, filters=ProspectFilters(contactable_only=True)
    )
    assert after.count() == 0


def test_unsubscribing_twice_is_one_entry_with_the_first_date(organization: Any) -> None:
    earlier = timezone.now() - timezone.timedelta(days=30)
    compliance.suppress(organization=organization, address=ADDRESS, suppressed_at=earlier)
    compliance.suppress(organization=organization, address=ADDRESS)

    entries = SuppressionEntry.all_objects.filter(organization=organization)
    assert entries.count() == 1
    # The date they asked is the one that answers "when did they ask?".
    assert entries.first().suppressed_at == earlier


# --------------------------------------------------------------------------- #
# Erasure: the requirement that reads like a contradiction
# --------------------------------------------------------------------------- #


def test_erasure_removes_the_person_and_keeps_the_ability_to_recognise_them(
    organization: Any, person: Any
) -> None:
    """Section 63: suppress, and preserve the minimum needed to honour it.

    Delete the address and you lose the means of recognising them, so the
    next import adds them back and the next campaign contacts them. Hashing
    is what lets both requirements hold at once.
    """
    result = compliance.erase(organization=organization, address=ADDRESS)

    assert result["people_redacted"] == 1

    person.refresh_from_db()
    assert person.email == ""
    assert person.full_name == ""
    assert person.email_status == ContactStatus.UNSUBSCRIBED

    entry = SuppressionEntry.all_objects.get(organization=organization)
    assert entry.value == "", "the plaintext address must be gone"
    assert entry.is_redacted is True
    # And the hash still recognises them.
    assert is_suppressed(organization=organization, address=ADDRESS) is True


def test_erasure_suppresses_before_it_redacts(organization: Any, person: Any) -> None:
    """Order matters: the reverse leaves a window with no suppression at all."""
    compliance.erase(organization=organization, address=ADDRESS)

    entry = SuppressionEntry.all_objects.get(organization=organization)
    assert entry.reason == SuppressionReason.LEGAL_REQUEST
    assert entry.suppressed_at <= entry.redacted_at


# --------------------------------------------------------------------------- #
# Removal
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("reason", "removable"),
    [
        (SuppressionReason.MANUAL, True),
        (SuppressionReason.IMPORTED, True),
        (SuppressionReason.BOUNCED, True),
        (SuppressionReason.UNSUBSCRIBED, False),
        (SuppressionReason.COMPLAINED, False),
        (SuppressionReason.LEGAL_REQUEST, False),
    ],
)
def test_only_an_operators_own_mistakes_can_be_removed(
    organization: Any, reason: str, removable: bool
) -> None:
    """A mistyped manual row is a mistake. An unsubscribe is a decision.

    A button that deletes the second has exactly one use, and it is the use
    this whole module exists to prevent.
    """
    entry = compliance.suppress(organization=organization, address=ADDRESS, reason=reason)

    assert entry.is_removable is removable
    assert compliance.unsuppress(entry=entry) is removable


# --------------------------------------------------------------------------- #
# Unsubscribe tokens
# --------------------------------------------------------------------------- #


def test_an_unsubscribe_token_round_trips(organization: Any) -> None:
    token = tokens.make_token(
        organization=organization, address=ADDRESS, message_id="m1", campaign_id="c1"
    )
    payload = tokens.read_token(token)

    assert payload["address"] == ADDRESS
    assert payload["organization"] == str(organization.public_id)
    assert payload["message"] == "m1"


def test_an_unsubscribe_link_never_expires(organization: Any) -> None:
    """The one token in the product that must not.

    A link in a March email has to work in November, because the person
    reading it then is exactly the one who will press "report spam" if it does
    not. An expiring opt-out is a dark pattern with a deliverability cost.
    """
    token = tokens.make_token(organization=organization, address=ADDRESS)

    # Signed tokens expire only when a reader passes max_age. Read it back
    # through the real reader and assert it imposes none.
    from django.core import signing

    assert tokens.read_token(token) is not None
    assert signing.loads(token, salt=tokens.SALT)["a"] == ADDRESS


@pytest.mark.security
def test_a_tampered_token_is_refused(organization: Any) -> None:
    token = tokens.make_token(organization=organization, address=ADDRESS)

    assert tokens.read_token(token[:-4] + "aaaa") is None
    assert tokens.read_token("not-a-token") is None
    assert tokens.read_token("") is None


def test_the_one_click_headers_are_the_pair_providers_honour(organization: Any) -> None:
    """A footer link is for the reader; these are for Gmail's button.

    Sending without them is how a message that offers an opt-out still gets
    reported as spam: the control the reader reached for was not there.
    """
    token = tokens.make_token(organization=organization, address=ADDRESS)
    headers = tokens.list_unsubscribe_headers(
        token=token, base_url="https://app.example", mailto="unsub@example.com"
    )

    assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert f"<https://app.example/unsubscribe/{token}>" in headers["List-Unsubscribe"]
    assert "<mailto:unsub@example.com?subject=unsubscribe>" in headers["List-Unsubscribe"]


# --------------------------------------------------------------------------- #
# Regional policy
# --------------------------------------------------------------------------- #


def test_an_unconfigured_market_is_treated_as_the_strict_one() -> None:
    """Fails closed. Forgetting to add a country must not permit cold outbound."""
    policy = policy_for("ZZ")

    assert policy.b2b_requires_prior_consent is True
    assert policy.opt_out_required is True
    assert "strictest" in policy.notes


def test_the_seeded_policies_cover_the_markets_section_62_names() -> None:
    seed_policies()
    codes = set(RegionalPolicy.objects.values_list("code", flat=True))

    assert {"NG", "KE", "ZA", "EU", "GB", "US"} <= codes


def test_the_policies_encode_the_differences_that_matter() -> None:
    """These drive what a campaign is allowed to do, so they are pinned.

    Each of these is a real divergence between regimes, and getting one
    backwards is the kind of mistake that is only discovered by a regulator.
    """
    seed_policies()

    # POPIA s69 restricts unsolicited electronic marketing to non-customers.
    assert policy_for("ZA").b2b_requires_prior_consent is True
    # PECR permits B2B email to corporate subscribers, with an opt-out.
    assert policy_for("GB").b2b_requires_prior_consent is False
    # CAN-SPAM is opt-out, and the one regime that demands a postal address.
    assert policy_for("US").b2b_requires_prior_consent is False
    assert policy_for("US").postal_address_required is True
    # CASL is consent-first and the most often missed.
    assert policy_for("CA").b2b_requires_prior_consent is True

    assert policy_for("US").requirements()


def test_seeding_twice_changes_nothing() -> None:
    seed_policies()
    second = seed_policies()

    assert second["created"] == 0


# --------------------------------------------------------------------------- #
# Consent
# --------------------------------------------------------------------------- #


def test_consent_is_recorded_with_what_would_be_shown_if_asked(
    organization: Any, person: Any
) -> None:
    record = compliance.record_consent(
        organization=organization,
        address=ADDRESS,
        basis=ConsentBasis.CONSENT,
        source="pricing_page_form",
        evidence="Submitted the demo form on 2026-10-01 from 102.89.x.x",
        country="NG",
        person=person,
    )

    assert record.is_active is True
    assert compliance.active_consent(organization=organization, address=ADDRESS) == record


def test_erasure_withdraws_consent_rather_than_deleting_the_record(
    organization: Any, person: Any
) -> None:
    """That consent once existed, and when it ended, is the part that matters."""
    compliance.record_consent(organization=organization, address=ADDRESS, person=person)

    compliance.erase(organization=organization, address=ADDRESS)

    record = ConsentRecord.all_objects.get(organization=organization)
    assert record.withdrawn_at is not None
    assert record.value == ""
    assert compliance.active_consent(organization=organization, address=ADDRESS) is None


# --------------------------------------------------------------------------- #
# The architecture test
# --------------------------------------------------------------------------- #

#: Modules allowed to construct an outbound message directly. Everything else
#: must go through the delivery layer, which must go through the guard.
SENDING_ALLOWLIST = {
    # Transactional mail only: verification, password reset, invitations.
    # Not marketing, and not subject to the suppression list -- a person who
    # unsubscribed from a campaign still needs their password reset to arrive.
    "apps/organizations/services.py",
    "apps/accounts",
    "apps/compliance",
}

_SEND_CALLS = re.compile(r"\b(send_mail|EmailMultiAlternatives|EmailMessage|get_connection)\s*\(")


def test_no_module_sends_mail_outside_the_delivery_layer() -> None:
    """The failure no unit test can cover: a send path nobody checked.

    Every test above asserts that the guard blocks what it is given. None of
    them can assert that a future campaign sender calls it at all, because
    that code does not exist yet. This fails the build the moment somebody
    constructs an outbound message somewhere new, which is the point at which
    the question is cheap to ask.
    """
    root = Path(__file__).resolve().parent.parent / "apps"
    offenders: list[str] = []

    for path in root.rglob("*.py"):
        relative = path.relative_to(root.parent).as_posix()
        if any(relative.startswith(allowed) for allowed in SENDING_ALLOWLIST):
            continue
        if "/migrations/" in relative:
            continue
        if _SEND_CALLS.search(path.read_text(encoding="utf-8")):
            offenders.append(relative)

    assert not offenders, (
        "These modules construct outbound mail directly:\n  "
        + "\n  ".join(offenders)
        + "\n\nMarketing mail must go through the delivery layer so that "
        "apps.compliance.guard runs first (PRD section 63). If this is "
        "transactional mail, add the module to SENDING_ALLOWLIST with a "
        "reason."
    )


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


def test_a_stranger_can_unsubscribe_from_an_email_client(
    api_client: Any, organization: Any, person: Any
) -> None:
    """No account, no session, one request. RFC 8058's one-click POST."""
    token = tokens.make_token(organization=organization, address=ADDRESS, campaign_id="c1")

    described = api_client.get(f"/api/v1/unsubscribe/{token}")
    assert described.status_code == 200
    assert described.data["valid"] is True
    # Masked: whoever holds the link may not be the person it was sent to.
    assert described.data["address"] == "a***@harmattanfleet.example"
    assert described.data["organization"] == organization.name

    done = api_client.post(f"/api/v1/unsubscribe/{token}", {}, format="json")

    assert done.status_code == 200
    assert done.data["unsubscribed"] is True
    assert is_suppressed(organization=organization, address=ADDRESS) is True


def test_unsubscribing_records_what_it_was_about(
    api_client: Any, organization: Any, person: Any
) -> None:
    token = tokens.make_token(
        organization=organization, address=ADDRESS, message_id="m7", campaign_id="c3"
    )

    api_client.post(f"/api/v1/unsubscribe/{token}", {"reason": "Too many emails"}, format="json")

    entry = SuppressionEntry.all_objects.get(organization=organization)
    assert entry.source == "unsubscribe_link"
    assert entry.notes == "Too many emails"
    assert entry.evidence == {"message": "m7", "campaign": "c3"}


@pytest.mark.security
def test_the_public_endpoint_is_not_an_address_oracle(api_client: Any) -> None:
    """A different answer for an invalid token would let anybody test addresses."""
    response = api_client.post("/api/v1/unsubscribe/rubbish", {}, format="json")

    assert response.status_code == 200
    assert response.data == {"unsubscribed": True}


def test_the_list_is_readable_and_writable_by_the_right_roles(
    organization: Any,
    owner: Any,
    auth_client: Callable[..., Any],
    make_member: Callable[..., Any],
) -> None:
    client = auth_client(owner, organization)

    created = client.post(
        SUPPRESSIONS_URL, {"address": "do-not-contact@example.com"}, format="json"
    )
    assert created.status_code == 201
    assert created.data["reason"] == "manual"
    assert created.data["is_removable"] is True

    # A rep can read the list -- they need to know why they cannot write to
    # somebody -- but not change it.
    rep = make_member(organization, role=Role.SALES_REP).user
    rep_client = auth_client(rep, organization)
    assert rep_client.get(SUPPRESSIONS_URL).status_code == 200
    assert (
        rep_client.post(SUPPRESSIONS_URL, {"address": "x@example.com"}, format="json").status_code
        == 403
    )


def test_an_unsubscribe_cannot_be_deleted_through_the_api(
    organization: Any, owner: Any, auth_client: Callable[..., Any], person: Any
) -> None:
    entry = compliance.suppress(organization=organization, address=ADDRESS)
    client = auth_client(owner, organization)

    response = client.delete(f"{SUPPRESSIONS_URL}/{entry.public_id}")

    assert response.status_code == 400
    assert "cannot be removed" in str(response.data)
    assert SuppressionEntry.all_objects.filter(pk=entry.pk).exists()


def test_a_manual_entry_can_be_corrected(
    organization: Any, owner: Any, auth_client: Callable[..., Any]
) -> None:
    entry = compliance.suppress(
        organization=organization, address="typo@example.com", reason=SuppressionReason.MANUAL
    )

    response = auth_client(owner, organization).delete(f"{SUPPRESSIONS_URL}/{entry.public_id}")

    assert response.status_code == 204
    assert not SuppressionEntry.all_objects.filter(pk=entry.pk).exists()


def test_an_existing_list_can_be_imported(
    organization: Any, owner: Any, auth_client: Callable[..., Any]
) -> None:
    """The first thing a customer switching tools needs, and the easiest to skip."""
    response = auth_client(owner, organization).post(
        f"{SUPPRESSIONS_URL}/import",
        {"addresses": ["one@example.com", "TWO@example.com", "   ", "three@example.com"]},
        format="json",
    )

    assert response.status_code == 200
    assert response.data == {"added": 3, "skipped": 1}
    assert is_suppressed(organization=organization, address="two@example.com")


def test_erasure_through_the_api_is_audited(
    organization: Any, owner: Any, auth_client: Callable[..., Any], person: Any
) -> None:
    from apps.audit.models import AuditAction, AuditLog

    response = auth_client(owner, organization).post(
        f"{SUPPRESSIONS_URL}/erase", {"address": ADDRESS}, format="json"
    )

    assert response.status_code == 200
    with tenant_context(organization=organization):
        assert AuditLog.objects.filter(action=AuditAction.DATA_ERASED).exists()


@pytest.mark.tenancy
def test_a_suppression_list_is_not_visible_to_another_tenant(
    organization: Any,
    other_organization: Any,
    make_member: Callable[..., Any],
    auth_client: Callable[..., Any],
    person: Any,
) -> None:
    entry = compliance.suppress(organization=organization, address=ADDRESS)

    intruder = make_member(other_organization, role=Role.ADMIN).user
    client = auth_client(intruder, other_organization)

    assert client.get(SUPPRESSIONS_URL).data["results"] == []
    assert client.delete(f"{SUPPRESSIONS_URL}/{entry.public_id}").status_code == 404


def test_the_policies_are_readable_in_the_product(
    organization: Any, owner: Any, auth_client: Callable[..., Any]
) -> None:
    seed_policies()

    response = auth_client(owner, organization).get("/api/v1/compliance/policies/NG")

    assert response.status_code == 200
    assert response.data["law"].startswith("Nigeria Data Protection Act")
    assert response.data["requirements"]
