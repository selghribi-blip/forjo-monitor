"""Sitemap-driven content inventory spider.

It reads the site's own sitemap, visits each declared URL exactly once and
records what the page says. It never logs in, never submits a form and never
follows anything outside the audited host.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

import scrapy
from bs4 import BeautifulSoup

from forjo_monitor.analyzers.html_facts import extract_seo_facts
from forjo_monitor.analyzers.keywords import bigrams, tokenize, top_keywords
from forjo_monitor.crawler.items import ContentItem
from forjo_monitor.discovery import parse_child_sitemaps, parse_urlset

LOGGER = logging.getLogger(__name__)

KEYWORD_LIMIT = 15
BIGRAM_LIMIT = 10


class ContentInventorySpider(scrapy.Spider):
    """Records content facts for every URL in the site's sitemap."""

    name = "content_inventory"

    def __init__(
        self,
        site_base_url: str = "",
        owned_hosts: Iterable[str] | None = None,
        max_pages: int = 0,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.site_base_url = site_base_url.rstrip("/")
        self.owned_hosts = frozenset(owned_hosts or [])
        self.max_pages = max_pages

    def start_requests(self) -> Iterable[scrapy.Request]:
        yield scrapy.Request(
            url=f"{self.site_base_url}/sitemap.xml",
            callback=self.parse_sitemap,
            errback=self.parse_error,
            dont_filter=True,
        )

    def parse_sitemap(self, response: scrapy.http.Response) -> Iterable[scrapy.Request]:
        """Expand a sitemap index (or a single urlset) into page requests."""
        children = parse_child_sitemaps(response.text)
        if children:
            for child in children:
                yield scrapy.Request(
                    url=child, callback=self.parse_sitemap, errback=self.parse_error,
                    dont_filter=True,
                )
            return

        pages = parse_urlset(response.text)
        urls = sorted({page.url for page in pages})
        if self.max_pages:
            urls = urls[: self.max_pages]
        LOGGER.info("Content inventory queued %d URLs", len(urls))
        for url in urls:
            yield scrapy.Request(url=url, callback=self.parse_page, errback=self.parse_error)

    def parse_error(self, failure: Any) -> None:
        LOGGER.warning("Inventory request failed: %s", failure.request.url)

    def parse_page(self, response: scrapy.http.Response) -> Iterable[ContentItem]:
        """Extract the content facts for one page."""
        facts = extract_seo_facts(response.text, response.url, self.owned_hosts)
        text = self._visible_text(response.text)

        yield ContentItem(
            url=response.url,
            status=response.status,
            title=facts.title,
            h1=facts.h1_texts[0] if facts.h1_texts else "",
            word_count=facts.word_count,
            h2_count=facts.h2_count,
            image_count=facts.image_count,
            images_without_alt=facts.images_without_alt,
            internal_links=facts.internal_links,
            external_links=facts.external_links,
            lang=facts.html_lang,
            published=self._published_date(response),
            top_keywords=top_keywords(text, KEYWORD_LIMIT),
            top_bigrams=bigrams(tokenize(text), BIGRAM_LIMIT),
        )

    @staticmethod
    def _visible_text(html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        for removable in soup.find_all(["script", "style", "noscript", "template", "header", "nav"]):
            removable.decompose()
        return soup.get_text(separator=" ", strip=True)

    @staticmethod
    def _published_date(response: scrapy.http.Response) -> str:
        for selector in (
            'meta[itemprop="datePublished"]::attr(content)',
            'meta[property="article:published_time"]::attr(content)',
        ):
            value = response.css(selector).get()
            if value:
                return value.strip()
        return ""
