"""Discover the site's own pages.

Two sources are merged so nothing is missed:

* ``/sitemap.xml`` (Blogger publishes a sitemap index with per-type children)
* the Blogger JSON feed ``/feeds/posts/default?alt=json``

Both are public endpoints of the site owner's own property.
"""

from __future__ import annotations

import logging
from xml.etree import ElementTree

import requests

from forjo_monitor.config import Settings
from forjo_monitor.models import PageRef

LOGGER = logging.getLogger(__name__)

_USER_AGENT = "forjo-monitor/1.0 (self-audit; owner-owned site)"
_REQUEST_TIMEOUT = 20
_MAX_FEED_RESULTS = 500


def build_session() -> requests.Session:
    """A session that identifies itself honestly."""
    session = requests.Session()
    session.headers.update({"User-Agent": _USER_AGENT, "Accept-Language": "ar,en;q=0.8"})
    return session


def _get(session: requests.Session, url: str) -> requests.Response | None:
    try:
        response = session.get(url, timeout=_REQUEST_TIMEOUT, allow_redirects=True)
    except requests.RequestException as exc:
        LOGGER.warning("Discovery request failed for %s: %s", url, exc)
        return None
    if response.status_code != 200:
        LOGGER.info("Discovery skipped %s (HTTP %s)", url, response.status_code)
        return None
    return response


def _local_name(tag: str) -> str:
    """Strip the XML namespace from an element tag."""
    return tag.rsplit("}", 1)[-1]


def parse_child_sitemaps(xml_text: str) -> list[str]:
    """Return the sitemap URLs listed inside a sitemap index."""
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        LOGGER.warning("Unparsable sitemap index: %s", exc)
        return []
    if _local_name(root.tag) != "sitemapindex":
        return []
    locations: list[str] = []
    for node in root:
        if _local_name(node.tag) != "sitemap":
            continue
        for child in node:
            if _local_name(child.tag) == "loc" and child.text:
                locations.append(child.text.strip())
    return locations


def parse_urlset(xml_text: str) -> list[PageRef]:
    """Return the pages listed inside one ``<urlset>`` sitemap."""
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        LOGGER.warning("Unparsable urlset: %s", exc)
        return []
    if _local_name(root.tag) != "urlset":
        return []

    pages: list[PageRef] = []
    for node in root:
        if _local_name(node.tag) != "url":
            continue
        loc = ""
        last_modified = ""
        for child in node:
            name = _local_name(child.tag)
            if name == "loc" and child.text:
                loc = child.text.strip()
            elif name == "lastmod" and child.text:
                last_modified = child.text.strip()
        if loc:
            pages.append(PageRef(url=loc, source="sitemap", last_modified=last_modified))
    return pages


def discover_from_sitemap(session: requests.Session, base_url: str) -> list[PageRef]:
    """Walk the sitemap index and collect every declared page."""
    root_response = _get(session, f"{base_url}/sitemap.xml")
    if root_response is None:
        return []

    children = parse_child_sitemaps(root_response.text)
    if not children:
        return parse_urlset(root_response.text)

    pages: list[PageRef] = []
    for child_url in children:
        child = _get(session, child_url)
        if child is not None:
            pages.extend(parse_urlset(child.text))
    return pages


def parse_blogger_feed(payload: dict) -> list[PageRef]:
    """Return the posts contained in a Blogger JSON feed document."""
    entries = payload.get("feed", {}).get("entry", [])
    if not isinstance(entries, list):
        return []

    pages: list[PageRef] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        links = entry.get("link", [])
        if not isinstance(links, list):
            continue
        url = ""
        for link in links:
            if isinstance(link, dict) and link.get("rel") == "alternate" and link.get("href"):
                url = str(link["href"]).strip()
                break
        if not url:
            continue
        published_node = entry.get("published")
        published = str(published_node.get("$t", "")) if isinstance(published_node, dict) else ""
        pages.append(PageRef(url=url, source="blogger-feed", last_modified=published))
    return pages


def discover_from_blogger_feed(session: requests.Session, base_url: str) -> list[PageRef]:
    """Read the posts feed, which also covers pages Blogger hides from sitemaps."""
    feed_url = f"{base_url}/feeds/posts/default?alt=json&max-results={_MAX_FEED_RESULTS}"
    response = _get(session, feed_url)
    if response is None:
        return []
    try:
        payload = response.json()
    except ValueError as exc:
        LOGGER.warning("Blogger feed is not valid JSON: %s", exc)
        return []
    return parse_blogger_feed(payload)


def deduplicate(pages: list[PageRef], limit: int) -> list[PageRef]:
    """Keep the first occurrence of each URL and cap the result."""
    seen: set[str] = set()
    unique: list[PageRef] = []
    for page in pages:
        if page.url in seen:
            continue
        seen.add(page.url)
        unique.append(page)
        if len(unique) >= limit:
            break
    return unique


def discover_pages(settings: Settings, session: requests.Session | None = None) -> list[PageRef]:
    """Merge every discovery source into one ordered, deduplicated page list."""
    http = session or build_session()
    base = settings.site_base_url

    from_sitemap = discover_from_sitemap(http, base)
    from_feed = discover_from_blogger_feed(http, base)
    LOGGER.info(
        "Discovery found %d sitemap URLs and %d feed posts", len(from_sitemap), len(from_feed)
    )
    return deduplicate([*from_sitemap, *from_feed], settings.crawl_max_pages)
