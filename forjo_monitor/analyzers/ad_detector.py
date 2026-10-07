"""Locate ad-network resources on a page.

This only ever *observes* what the page already loads. It never triggers a
click, a view or any interaction with an ad unit.
"""

from __future__ import annotations

from urllib.parse import urlparse

from bs4 import BeautifulSoup
from bs4.element import Tag

from forjo_monitor.models import AdObservation

_RESOURCE_ATTRS = (
    ("script", "src"),
    ("iframe", "src"),
    ("link", "href"),
    ("img", "src"),
)


def match_network(resource_url: str, network_domains: tuple[str, ...]) -> str:
    """Return the matching network domain for ``resource_url``, or ``''``."""
    host = (urlparse(resource_url).hostname or "").lower()
    if not host:
        return ""
    for domain in network_domains:
        if host == domain or host.endswith(f".{domain}"):
            return domain
    return ""


def detect_static_ad_resources(
    html: str, network_domains: tuple[str, ...]
) -> list[AdObservation]:
    """Find ad-network resources declared in the served HTML."""
    soup = BeautifulSoup(html, "lxml")
    found: dict[str, AdObservation] = {}

    for tag_name, attr_name in _RESOURCE_ATTRS:
        for node in soup.find_all(tag_name):
            if not isinstance(node, Tag):
                continue
            resource_url = str(node.get(attr_name, "") or "").strip()
            if not resource_url:
                continue
            network = match_network(resource_url, network_domains)
            if not network or network in found:
                continue
            found[network] = AdObservation(
                network=network,
                kind=tag_name,
                resource_url=resource_url,
                detected_in_dom=False,
            )

    return list(found.values())


def networks_seen(observations: list[AdObservation]) -> dict[str, int]:
    """Count how many resources each network contributed."""
    counts: dict[str, int] = {}
    for observation in observations:
        counts[observation.network] = counts.get(observation.network, 0) + 1
    return counts


def merge_observations(
    static: list[AdObservation], live: list[AdObservation]
) -> list[AdObservation]:
    """Prefer the richer live-browser observation for each network."""
    merged: dict[str, AdObservation] = {item.network: item for item in static}
    for item in live:
        merged[item.network] = item
    return sorted(merged.values(), key=lambda item: item.network)
