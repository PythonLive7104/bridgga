"""Website analysis service layer."""

from __future__ import annotations

from typing import Any

import structlog
from django.db import transaction
from django.utils import timezone

from apps.common.tenancy import tenant_context
from apps.intelligence.extract import extract_page
from apps.intelligence.fetcher import FetchError, UnsafeUrlError, fetch_url
from apps.intelligence.models import SnapshotStatus, WebsiteSnapshot

logger = structlog.get_logger(__name__)


def normalise_website_url(raw: str) -> str:
    """Make a human-typed website usable.

    People type "acme.com", not "https://acme.com". Defaulting the scheme here
    rather than in the fetcher keeps the fetcher strict: it should refuse
    anything malformed rather than quietly repair it.
    """
    candidate = (raw or "").strip()
    if not candidate:
        return ""
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    return candidate


@transaction.atomic
def capture_snapshot(*, organization: Any, url: str, company: Any = None) -> WebsiteSnapshot:
    """Fetch a URL and store the result, successes and failures alike.

    A refusal or a failure is recorded rather than raised, because the
    onboarding UI needs to show the user *why* their site could not be read,
    and because a repeated failure against the same domain is a signal worth
    keeping.

    ``company`` attributes the fetch to a prospect, which is what lets the
    signal detectors pair consecutive crawls of the same page. Left unset for
    the customer's own website.
    """
    normalised = normalise_website_url(url)

    with tenant_context(organization=organization):
        snapshot = WebsiteSnapshot.objects.create(
            organization=organization,
            company=company,
            requested_url=normalised[:2048],
            status=SnapshotStatus.PENDING,
        )

        try:
            result = fetch_url(normalised)
        except UnsafeUrlError as exc:
            snapshot.status = SnapshotStatus.REFUSED
            snapshot.error_reason = exc.reason[:255]
            snapshot.fetched_at = timezone.now()
            snapshot.save()
            logger.warning(
                "website_fetch_refused",
                organization_id=str(organization.public_id),
                reason=exc.reason,
            )
            return snapshot
        except FetchError as exc:
            snapshot.status = SnapshotStatus.FAILED
            snapshot.error_reason = str(exc)[:255]
            snapshot.fetched_at = timezone.now()
            snapshot.save()
            logger.info("website_fetch_failed", reason=str(exc))
            return snapshot

        page = extract_page(result.body, base_url=result.final_url)

        snapshot.status = SnapshotStatus.OK
        snapshot.final_url = result.final_url[:2048]
        snapshot.status_code = result.status_code
        snapshot.content_type = result.content_type
        snapshot.title = page.title
        snapshot.description = page.description
        snapshot.language = page.language
        snapshot.canonical_url = page.canonical_url[:2048]
        snapshot.headings = page.headings
        snapshot.text = page.text
        snapshot.internal_links = page.internal_links
        snapshot.social_links = page.social_links
        snapshot.emails = page.emails
        snapshot.content_hash = result.content_hash
        snapshot.resolved_ips = result.resolved_ips
        snapshot.truncated = result.truncated or page.truncated
        snapshot.elapsed_ms = result.elapsed_ms
        snapshot.fetched_at = timezone.now()
        snapshot.save()

        logger.info(
            "website_fetch_ok",
            organization_id=str(organization.public_id),
            final_url=snapshot.final_url,
            status_code=snapshot.status_code,
            text_chars=len(snapshot.text),
            links=len(snapshot.internal_links),
        )
        return snapshot
