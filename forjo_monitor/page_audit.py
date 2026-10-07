"""Audit exactly one page: fetch it, measure it, grade it.

Internal links are only *counted* (for crawl-depth scoring). Only outbound
links are probed, which keeps the load on the origin site minimal.
"""

from __future__ import annotations

import logging

import requests

from forjo_monitor.analyzers.ad_detector import detect_static_ad_resources, merge_observations
from forjo_monitor.analyzers.aggregate import build_page_checks
from forjo_monitor.analyzers.html_facts import extract_seo_facts
from forjo_monitor.analyzers.link_checker import collect_links, probe_all
from forjo_monitor.browser_auditor import BrowserAuditor
from forjo_monitor.checks import Check, CheckId, CheckStatus, Severity
from forjo_monitor.config import Settings
from forjo_monitor.models import (
    AdObservation,
    HttpSnapshot,
    PageAudit,
    PageRef,
    PerformanceMetrics,
    SeoFacts,
    utc_now,
)

LOGGER = logging.getLogger(__name__)

FETCH_TIMEOUT = 30
HTML_CONTENT_TYPE = "text/html"


def _failed_fetch(page_ref: PageRef, run_id: str, reason: str) -> PageAudit:
    """Represent a page we could not even download."""
    return PageAudit(
        page=page_ref,
        audit_id=run_id,
        started_at=utc_now(),
        snapshot=HttpSnapshot(
            final_url=page_ref.url,
            status_code=0,
            content_type="",
            html_bytes=0,
            redirects=0,
        ),
        seo=SeoFacts(),
        checks=[
            Check(
                CheckId.HTTP_OK,
                "الصفحة تُرجع 200",
                CheckStatus.FAIL,
                Severity.CRITICAL,
                reason,
            )
        ],
        ads=[],
        performance=PerformanceMetrics(),
        error=reason,
    )


def fetch_page(session: requests.Session, url: str) -> requests.Response | None:
    """Download a page once, letting redirects settle."""
    try:
        return session.get(url, timeout=FETCH_TIMEOUT, allow_redirects=True)
    except requests.RequestException as exc:
        LOGGER.warning("Fetch failed for %s: %s", url, exc)
        return None


def count_broken_links(
    settings: Settings, session: requests.Session, html: str, page_url: str, enabled: bool
) -> int:
    """Probe the page's outbound links and count the ones that do not resolve."""
    if not enabled:
        return 0
    targets = collect_links(html, page_url, settings.owned_hosts, external_only=True)
    if not targets:
        return 0
    return sum(1 for result in probe_all(session, targets) if not result.ok)


def audit_single_page(
    *,
    settings: Settings,
    session: requests.Session,
    page_ref: PageRef,
    run_id: str,
    browser: BrowserAuditor | None = None,
    check_links: bool = True,
) -> PageAudit:
    """Produce the complete :class:`PageAudit` for one URL."""
    response = fetch_page(session, page_ref.url)
    if response is None:
        return _failed_fetch(page_ref, run_id, "فشل طلب الصفحة (شبكة أو مهلة)")

    content_type = response.headers.get("Content-Type", "")
    html = response.text if HTML_CONTENT_TYPE in content_type else ""
    snapshot = HttpSnapshot(
        final_url=response.url,
        status_code=response.status_code,
        content_type=content_type,
        html_bytes=len(response.content),
        redirects=len(response.history),
    )

    facts = extract_seo_facts(html, response.url, settings.owned_hosts) if html else SeoFacts()
    static_ads: list[AdObservation] = (
        detect_static_ad_resources(html, settings.ad_network_domains) if html else []
    )

    performance = PerformanceMetrics()
    live_ads: list[AdObservation] = []
    screenshot_path = ""
    page_error = ""

    if browser is not None:
        outcome = browser.audit(page_ref.url)
        performance = outcome.performance
        live_ads = outcome.ads
        screenshot_path = outcome.screenshot_path
        page_error = outcome.error

    ads = merge_observations(static_ads, live_ads)
    broken_links = (
        count_broken_links(settings, session, html, response.url, check_links) if html else 0
    )

    checks = build_page_checks(
        snapshot=snapshot,
        facts=facts,
        owned_hosts=settings.owned_hosts,
        ads=ads,
        performance=performance,
        broken_links=broken_links,
        browser_data_available=browser is not None and not page_error,
    )

    return PageAudit(
        page=page_ref,
        audit_id=run_id,
        started_at=utc_now(),
        snapshot=snapshot,
        seo=facts,
        checks=checks,
        ads=ads,
        performance=performance,
        screenshot_path=screenshot_path,
        error=page_error,
    )
