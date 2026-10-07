"""Verify that the links a page publishes still resolve.

Only ``HEAD``/``GET`` requests are issued: nothing is submitted, nothing is
clicked, no session is forged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

from forjo_monitor.analyzers.html_facts import normalize_host

LOGGER = logging.getLogger(__name__)

_MAX_URLS_PER_PAGE = 25
_REQUEST_TIMEOUT = 15
_NON_WEB_SCHEMES = ("mailto:", "tel:", "javascript:", "data:", "sms:", "whatsapp:", "viber:")
_USER_AGENT = "forjo-monitor/1.0 (link check; owner-owned site)"


@dataclass(frozen=True)
class LinkResult:
    """Outcome of probing one URL."""

    url: str
    status_code: int
    ok: bool
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "status_code": self.status_code,
            "ok": self.ok,
            "error": self.error,
        }


def collect_links(
    html: str, page_url: str, owned_hosts: frozenset[str], *, external_only: bool
) -> list[str]:
    """Return the absolute link targets on a page, in document order."""
    soup = BeautifulSoup(html, "lxml")
    targets: list[str] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        raw = str(anchor.get("href", "")).strip()
        if not raw or raw.startswith("#") or raw.lower().startswith(_NON_WEB_SCHEMES):
            continue
        absolute = urljoin(page_url, raw)
        host = normalize_host(absolute)
        if not host:
            continue
        is_internal = host in owned_hosts
        if external_only is is_internal:
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        targets.append(absolute)
        if len(targets) >= _MAX_URLS_PER_PAGE:
            break

    return targets


def probe(session: requests.Session, url: str) -> LinkResult:
    """Issue the cheapest request that proves the URL resolves."""
    try:
        response = session.head(
            url, timeout=_REQUEST_TIMEOUT, allow_redirects=True, headers={"User-Agent": _USER_AGENT}
        )
        if response.status_code in (403, 405, 501):
            response = session.get(
                url,
                timeout=_REQUEST_TIMEOUT,
                allow_redirects=True,
                headers={"User-Agent": _USER_AGENT},
                stream=True,
            )
    except requests.RequestException as exc:
        return LinkResult(url=url, status_code=0, ok=False, error=str(exc))

    if response.status_code >= 400:
        return LinkResult(
            url=url, status_code=response.status_code, ok=False, error=f"HTTP {response.status_code}"
        )
    return LinkResult(url=url, status_code=response.status_code, ok=True)


def probe_all(session: requests.Session, urls: list[str]) -> list[LinkResult]:
    """Probe each URL, skipping ones that already failed a previous page."""
    results: list[LinkResult] = []
    for url in urls:
        outcome = probe(session, url)
        if not outcome.ok:
            LOGGER.info("Broken link on the site: %s (%s)", url, outcome.error)
        results.append(outcome)
    return results
