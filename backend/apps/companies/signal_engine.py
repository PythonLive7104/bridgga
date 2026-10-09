"""Running the detectors and reconciling what they find (PRD section 33).

The detectors in ``apps.companies.detectors`` are pure. This module is where
their output meets stored state, and that reconciliation is the whole job:

* **Re-detection must be idempotent.** Detection runs on a schedule, so the
  same careers page is read again and again. Matching on
  ``(company, signal_type, fingerprint)`` turns the second reading into an
  update rather than a duplicate row.
* **Re-detection must not refresh what is not still true.** Only a signal the
  detector marked ``renewable`` has its expiry extended when it is seen
  again. See ``DetectedSignal.renewable``.
* **A human's judgement outranks a detector's.** Once somebody dismisses a
  signal, re-detecting the same observation does not bring it back.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog
from django.db import transaction
from django.utils import timezone

from apps.common.tenancy import tenant_context
from apps.companies.detectors import DETECTORS, DetectedSignal, DetectionContext, SnapshotPair
from apps.companies.signal_models import LeadSignal, expiry_for

logger = structlog.get_logger(__name__)

#: How many of a company's pages to diff in one run. A site with hundreds of
#: crawled URLs would otherwise make detection cost grow with the crawl.
MAX_PAGES = 12


def build_context(company: Any, *, now: datetime | None = None) -> DetectionContext:
    """Gather one company's evidence into the shape detectors read.

    Two snapshots per URL, newest first, because every diffing detector needs
    a before and an after and nothing needs a third.
    """
    from apps.companies.models import CompanyEvent, CompanyTechnology
    from apps.intelligence.models import SnapshotStatus, WebsiteSnapshot

    moment = now or timezone.now()

    snapshots = (
        WebsiteSnapshot.all_objects.filter(
            organization_id=company.organization_id,
            company_id=company.pk,
            status=SnapshotStatus.OK,
        )
        .order_by("requested_url", "-fetched_at", "-id")
        .only(
            "id",
            "requested_url",
            "final_url",
            "title",
            "text",
            "headings",
            "internal_links",
            "content_hash",
            "fetched_at",
        )
    )

    pages: list[SnapshotPair] = []
    by_url: dict[str, list[Any]] = {}
    for snapshot in snapshots:
        by_url.setdefault(snapshot.requested_url, []).append(snapshot)

    for versions in by_url.values():
        pages.append(
            SnapshotPair(current=versions[0], previous=versions[1] if len(versions) > 1 else None)
        )
        if len(pages) >= MAX_PAGES:
            break

    technologies = list(
        CompanyTechnology.all_objects.filter(company_id=company.pk).order_by("-last_seen", "name")[
            :50
        ]
    )
    events = list(
        CompanyEvent.all_objects.filter(company_id=company.pk).order_by("-occurred_at", "-id")[:50]
    )

    return DetectionContext(
        company=company,
        pages=pages,
        technologies=technologies,
        events=events,
        now=moment,
    )


#: Pages worth re-crawling on a prospect, in priority order. Three fetches per
#: company per cycle: the homepage carries announcements, the careers page
#: carries the hiring signal, and the pricing page carries the strongest and
#: most checkable one of the set.
WATCHED_PAGE_HINTS = (("career", "job", "vacanc"), ("pricing", "plans", "price"))


def crawl_company_pages(*, company: Any, max_pages: int = 3) -> list[Any]:
    """Re-fetch the pages the detectors diff, and attribute them to the company.

    Detection is only ever as good as having two crawls to compare, so this is
    the half of the engine that makes the other half possible. It deliberately
    fetches few pages: the signal value is in watching the same handful over
    time, not in crawling a site exhaustively once.
    """
    from apps.intelligence.services import capture_snapshot, normalise_website_url

    target = normalise_website_url(company.website or company.domain or "")
    if not target:
        return []

    home = capture_snapshot(organization=company.organization, url=target, company=company)
    captured = [home]
    if not home.succeeded:
        return captured

    for hints in WATCHED_PAGE_HINTS:
        if len(captured) >= max_pages:
            break
        for link in home.internal_links or []:
            if any(hint in str(link).lower() for hint in hints):
                captured.append(
                    capture_snapshot(
                        organization=company.organization, url=str(link), company=company
                    )
                )
                break

    logger.info(
        "company_pages_crawled",
        company_id=str(company.public_id),
        pages=len(captured),
        ok=sum(1 for page in captured if page.succeeded),
    )
    return captured


@transaction.atomic
def record_signal(
    *, company: Any, detected: DetectedSignal, now: datetime | None = None
) -> tuple[LeadSignal, bool]:
    """Store one detection, or refresh the row that already represents it.

    Returns the signal and whether it was newly created.
    """
    moment = now or timezone.now()

    existing = LeadSignal.all_objects.filter(
        company_id=company.pk,
        signal_type=detected.signal_type,
        fingerprint=detected.fingerprint,
    ).first()

    if existing is None:
        start = detected.occurred_at or moment
        signal = LeadSignal(
            organization_id=company.organization_id,
            company_id=company.pk,
            signal_type=detected.signal_type,
            title=detected.title,
            description=detected.description,
            detector=detected.detector,
            fingerprint=detected.fingerprint,
            occurred_at=detected.occurred_at,
            detected_at=moment,
            last_seen_at=moment,
            expires_at=expiry_for(detected.signal_type, start=start),
            strength=max(0, min(detected.strength, 100)),
            evidence=detected.evidence,
            source=detected.source,
            source_url=detected.source_url[:2048],
            confidence=detected.confidence,
            collected_at=moment,
            last_verified_at=moment,
            source_event_id=detected.source_event_id,
            source_snapshot_id=detected.source_snapshot_id,
            metadata={"renewable": detected.renewable},
        )
        signal.save()
        return signal, True

    # Seen before. Record that it is still there either way -- a dismissed
    # signal that keeps reappearing is useful feedback about the detector.
    existing.last_seen_at = moment
    existing.last_verified_at = moment
    fields = ["last_seen_at", "last_verified_at", "updated_at"]

    if not existing.is_dismissed:
        existing.title = detected.title
        existing.description = detected.description
        existing.strength = max(0, min(detected.strength, 100))
        existing.evidence = detected.evidence
        existing.confidence = detected.confidence
        fields += ["title", "description", "strength", "evidence", "confidence"]

        if detected.renewable:
            existing.expires_at = expiry_for(detected.signal_type, start=moment)
            fields.append("expires_at")

    existing.save(update_fields=fields)
    return existing, False


def run_detectors(
    *,
    company: Any,
    detectors: tuple[Any, ...] | None = None,
    now: datetime | None = None,
) -> list[LeadSignal]:
    """Detect everything detectable about one company, and store it.

    A detector that raises is logged and skipped rather than failing the run:
    one brittle regex should not cost a company every other signal it has.
    """
    moment = now or timezone.now()
    context = build_context(company, now=moment)
    produced: list[LeadSignal] = []
    created_count = 0

    with tenant_context(organization=company.organization):
        for detector in detectors or DETECTORS:
            try:
                found = detector.detect(context)
            except Exception as exc:
                logger.warning(
                    "signal_detector_failed",
                    detector=getattr(detector, "name", type(detector).__name__),
                    company_id=str(company.public_id),
                    error=str(exc)[:200],
                )
                continue

            for detected in found:
                signal, created = record_signal(company=company, detected=detected, now=moment)
                produced.append(signal)
                created_count += int(created)

    logger.info(
        "signals_detected",
        company_id=str(company.public_id),
        organization_id=str(company.organization.public_id),
        total=len(produced),
        created=created_count,
        pages=len(context.pages),
    )
    return produced


def dismiss_signal(*, signal: LeadSignal, user: Any = None, reason: str = "") -> LeadSignal:
    """Mark a signal as not relevant, without deleting the evidence."""
    signal.dismissed_at = timezone.now()
    signal.dismissed_by = user if getattr(user, "pk", None) else None
    signal.dismiss_reason = reason[:255]
    signal.save(update_fields=["dismissed_at", "dismissed_by", "dismiss_reason", "updated_at"])
    return signal


def active_signals_for(company: Any, *, limit: int = 10) -> list[LeadSignal]:
    """The live signals for one company, strongest first."""
    return list(
        LeadSignal.all_objects.filter(company_id=company.pk).active().strongest_first()[:limit]
    )


def prune_signals(*, organization: Any = None, older_than_days: int = 365) -> int:
    """Delete long-expired signals, keeping dismissed ones.

    Expired rows are history nobody reads: the evidence lives in the snapshot
    and the event they were derived from. A *dismissed* row is different --
    that is a human's verdict on a detector, and it is the only record of it.
    """
    cutoff = timezone.now() - timezone.timedelta(days=older_than_days)
    queryset = LeadSignal.all_objects.filter(expires_at__lt=cutoff, dismissed_at__isnull=True)
    if organization is not None:
        queryset = queryset.filter(organization_id=organization.pk)

    deleted, _ = queryset.delete()
    if deleted:
        logger.info("signals_pruned", deleted=deleted, older_than_days=older_than_days)
    return deleted


__all__ = [
    "MAX_PAGES",
    "WATCHED_PAGE_HINTS",
    "active_signals_for",
    "build_context",
    "crawl_company_pages",
    "dismiss_signal",
    "prune_signals",
    "record_signal",
    "run_detectors",
]
