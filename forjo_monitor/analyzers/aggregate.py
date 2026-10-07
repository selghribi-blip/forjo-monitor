"""Assemble the complete check list for one page."""

from __future__ import annotations

from forjo_monitor.analyzers.ad_detector import match_network
from forjo_monitor.analyzers.rules import (
    accessibility_checks,
    http_checks,
    link_checks,
    seo_checks,
)
from forjo_monitor.analyzers.rules_monetization import (
    ad_presence_checks,
    ad_visibility_checks,
    page_weight_checks,
    performance_checks,
)
from forjo_monitor.checks import Check
from forjo_monitor.models import AdObservation, HttpSnapshot, PerformanceMetrics, SeoFacts


def build_page_checks(
    *,
    snapshot: HttpSnapshot,
    facts: SeoFacts,
    owned_hosts: frozenset[str],
    ads: list[AdObservation],
    performance: PerformanceMetrics,
    broken_links: int,
    browser_data_available: bool,
) -> list[Check]:
    """Run every rule group and return one ordered list of checks."""
    checks: list[Check] = []
    checks.extend(http_checks(snapshot))
    checks.extend(seo_checks(facts, owned_hosts))
    checks.extend(accessibility_checks(facts))
    checks.extend(link_checks(facts, broken_links))
    checks.extend(ad_presence_checks(ads))
    checks.extend(ad_visibility_checks(ads, browser_data_available=browser_data_available))
    checks.extend(page_weight_checks(snapshot.html_bytes))
    checks.extend(performance_checks(performance))
    return checks


def count_networks(ads: list[AdObservation], network_domains: tuple[str, ...]) -> int:
    """Count distinct configured networks actually present on the page."""
    present = {
        match_network(observation.resource_url, network_domains)
        for observation in ads
        if match_network(observation.resource_url, network_domains)
    }
    return len(present)
