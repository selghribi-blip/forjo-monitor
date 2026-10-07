"""Extract SEO and content facts from a page's static HTML."""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from bs4.element import Tag

from forjo_monitor.models import SeoFacts

_WORD_RE = re.compile(r"[\w\u0600-\u06FF]+", re.UNICODE)
_NON_WEB_SCHEMES = ("mailto:", "tel:", "javascript:", "data:", "sms:", "whatsapp:", "viber:")


def normalize_host(url: str) -> str:
    """Return the comparable hostname of ``url`` (``www.`` stripped, lower-cased)."""
    host = urlparse(url).hostname or ""
    return host.lower().removeprefix("www.")


def meta_value(soup: BeautifulSoup, *, name: str = "", prop: str = "") -> str:
    """Read a ``<meta>`` content value by ``name`` or ``property``."""
    if name:
        node = soup.find("meta", attrs={"name": re.compile(f"^{re.escape(name)}$", re.I)})
    elif prop:
        node = soup.find("meta", attrs={"property": re.compile(f"^{re.escape(prop)}$", re.I)})
    else:
        return ""
    if isinstance(node, Tag):
        return str(node.get("content", "")).strip()
    return ""


def rel_tokens(node: Tag) -> list[str]:
    """Return the lower-cased ``rel`` tokens of a link element."""
    raw = node.get("rel")
    if not raw:
        return []
    values = raw if isinstance(raw, list) else [raw]
    return [str(value).lower() for value in values]


def find_canonical(soup: BeautifulSoup) -> str:
    """Return the ``<link rel="canonical">`` target, if declared."""
    for node in soup.find_all("link", href=True):
        if isinstance(node, Tag) and "canonical" in rel_tokens(node):
            return str(node.get("href", "")).strip()
    return ""


def count_words(soup: BeautifulSoup) -> int:
    """Approximate the readable word count of the page body."""
    for removable in soup.find_all(["script", "style", "noscript", "template"]):
        removable.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return len(_WORD_RE.findall(text))


def classify_links(
    soup: BeautifulSoup, page_url: str, owned_hosts: frozenset[str]
) -> tuple[int, int]:
    """Count internal and external anchors on the page."""
    internal = 0
    external = 0

    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        raw = str(anchor.get("href", "")).strip()
        if not raw or raw.startswith("#") or raw.lower().startswith(_NON_WEB_SCHEMES):
            continue
        host = normalize_host(urljoin(page_url, raw))
        if not host:
            continue
        if host in owned_hosts:
            internal += 1
        else:
            external += 1

    return internal, external


def extract_json_ld_types(soup: BeautifulSoup) -> tuple[str, ...]:
    """Return the ``@type`` values declared in JSON-LD blocks."""
    types: list[str] = []
    for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
        payload = node.string or node.get_text()
        if not payload:
            continue
        try:
            parsed = json.loads(payload)
        except ValueError:
            continue
        for item in parsed if isinstance(parsed, list) else [parsed]:
            if not isinstance(item, dict):
                continue
            declared = item.get("@type", "")
            values = declared if isinstance(declared, list) else [declared]
            types.extend(str(value) for value in values if value)
    return tuple(dict.fromkeys(types))


def extract_seo_facts(html: str, page_url: str, owned_hosts: frozenset[str]) -> SeoFacts:
    """Build the :class:`SeoFacts` record for one page."""
    soup = BeautifulSoup(html, "lxml")

    title = soup.title.get_text(strip=True) if soup.title else ""
    h1_texts = tuple(node.get_text(strip=True) for node in soup.find_all("h1"))

    images = soup.find_all("img")
    images_without_alt = sum(1 for image in images if not str(image.get("alt", "") or "").strip())
    internal, external = classify_links(soup, page_url, owned_hosts)

    return SeoFacts(
        title=title,
        meta_description=meta_value(soup, name="description"),
        canonical=find_canonical(soup),
        robots_meta=meta_value(soup, name="robots"),
        html_lang=str(soup.html.get("lang", "")).strip() if soup.html else "",
        h1_texts=h1_texts,
        h2_count=len(soup.find_all("h2")),
        image_count=len(images),
        images_without_alt=images_without_alt,
        internal_links=internal,
        external_links=external,
        word_count=count_words(soup),
        has_open_graph=bool(meta_value(soup, prop="og:title")),
        has_og_image=bool(meta_value(soup, prop="og:image")),
        has_json_ld=bool(soup.find("script", attrs={"type": "application/ld+json"})),
        json_ld_types=extract_json_ld_types(soup),
    )
