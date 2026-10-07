"""Tests for sitemap and Blogger feed discovery."""

from __future__ import annotations

from forjo_monitor.discovery import (
    deduplicate,
    parse_blogger_feed,
    parse_child_sitemaps,
    parse_urlset,
)

SITEMAP_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://www.forjo.tech/sitemap-pages.xml</loc></sitemap>
  <sitemap><loc>https://www.forjo.tech/sitemap-posts.xml</loc></sitemap>
</sitemapindex>
"""

URLSET = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://www.forjo.tech/2026/08/blog-post_294.html</loc>
    <lastmod>2026-08-16T19:33:00-07:00</lastmod>
  </url>
  <url><loc>https://www.forjo.tech/2026/08/blog-post_502.html</loc></url>
</urlset>
"""

BLOGGER_FEED = {
    "feed": {
        "entry": [
            {
                "published": {"$t": "2026-08-16T19:33:00.000-07:00"},
                "link": [
                    {"rel": "self", "href": "https://www.forjo.tech/feeds/posts/default/1"},
                    {"rel": "alternate", "href": "https://www.forjo.tech/2026/08/blog-post_294.html"},
                ],
            },
            {
                "link": [
                    {"rel": "alternate", "href": "https://www.forjo.tech/2026/08/blog-post_613.html"}
                ],
            },
        ]
    }
}


def test_parse_child_sitemaps_extracts_locations() -> None:
    assert parse_child_sitemaps(SITEMAP_INDEX) == [
        "https://www.forjo.tech/sitemap-pages.xml",
        "https://www.forjo.tech/sitemap-posts.xml",
    ]


def test_parse_child_sitemaps_returns_empty_for_urlset() -> None:
    assert parse_child_sitemaps(URLSET) == []


def test_parse_urlset_keeps_loc_and_lastmod() -> None:
    pages = parse_urlset(URLSET)
    assert [page.url for page in pages] == [
        "https://www.forjo.tech/2026/08/blog-post_294.html",
        "https://www.forjo.tech/2026/08/blog-post_502.html",
    ]
    assert pages[0].last_modified == "2026-08-16T19:33:00-07:00"
    assert pages[0].source == "sitemap"
    assert pages[1].last_modified == ""


def test_parse_urlset_tolerates_broken_xml() -> None:
    assert parse_urlset("<urlset><url>") == []


def test_parse_blogger_feed_uses_alternate_link() -> None:
    pages = parse_blogger_feed(BLOGGER_FEED)
    assert [page.url for page in pages] == [
        "https://www.forjo.tech/2026/08/blog-post_294.html",
        "https://www.forjo.tech/2026/08/blog-post_613.html",
    ]
    assert pages[0].last_modified.startswith("2026-08-16")
    assert pages[0].source == "blogger-feed"


def test_parse_blogger_feed_tolerates_missing_entries() -> None:
    assert parse_blogger_feed({"feed": {}}) == []
    assert parse_blogger_feed({}) == []


def test_deduplicate_preserves_order_and_limit() -> None:
    pages = parse_urlset(URLSET)
    merged = deduplicate([*pages, *pages], limit=10)
    assert [page.url for page in merged] == [page.url for page in pages]
    assert len(deduplicate(pages, limit=1)) == 1
