"""Run the content inventory spider with sane, polite settings."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from forjo_monitor.config import Settings
from forjo_monitor.crawler.spider import ContentInventorySpider

LOGGER = logging.getLogger(__name__)

INVENTORY_FILE_NAME = "content-inventory.jsonl"
HTTP_ERROR_CODES = (500, 502, 503, 504, 522, 524)
_REACTOR_ALREADY_USED = False


@dataclass(frozen=True)
class InventoryResult:
    """Outcome of one content inventory run."""

    item_count: int
    output_path: Path
    stored: bool


def build_scrapy_settings(settings: Settings) -> dict[str, Any]:
    """Translate the project configuration into Scrapy settings."""
    reports_dir: Path = settings.reports_dir
    return {
        "ROBOTSTXT_OBEY": settings.crawl_respect_robots,
        "DOWNLOAD_DELAY": settings.crawl_delay_seconds,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "CONCURRENT_REQUESTS": settings.crawl_concurrency,
        "CONCURRENT_REQUESTS_PER_DOMAIN": settings.crawl_concurrency,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": settings.crawl_delay_seconds,
        "AUTOTHROTTLE_MAX_DELAY": 30.0,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": float(settings.crawl_concurrency),
        "RETRY_TIMES": 2,
        "RETRY_HTTP_CODES": list(HTTP_ERROR_CODES),
        "COOKIES_ENABLED": False,
        "HTTPCACHE_ENABLED": False,
        "TELNETCONSOLE_ENABLED": False,
        "ROBOTSTXT_OBEY_ONLY_FOR_BOTS": True,
        "USER_AGENT": "forjo-monitor/1.0 (+content inventory; owner-owned site)",
        "ITEM_PIPELINES": {
            "forjo_monitor.crawler.pipelines.MongoContentPipeline": 100,
            "forjo_monitor.crawler.pipelines.JsonLinesContentPipeline": 200,
        },
        "MONGODB_URI": settings.mongodb_uri,
        "MONGODB_DATABASE": settings.mongodb_database,
        "INVENTORY_OUTPUT": str(reports_dir / INVENTORY_FILE_NAME),
    }


def run_inventory(settings: Settings, max_pages: int = 0) -> InventoryResult:
    """Execute the inventory spider and report what it collected."""
    global _REACTOR_ALREADY_USED
    if _REACTOR_ALREADY_USED:
        raise RuntimeError(
            "Scrapy's reactor can only be started once per process. "
            "Run the inventory in its own process (e.g. `python -m forjo_monitor inventory`)."
        )

    from scrapy.crawler import CrawlerProcess

    scrapy_settings = build_scrapy_settings(settings)
    output_path = Path(scrapy_settings["INVENTORY_OUTPUT"])

    process = CrawlerProcess(settings=scrapy_settings)
    crawler = process.crawl(
        ContentInventorySpider,
        site_base_url=settings.site_base_url,
        owned_hosts=sorted(settings.owned_hosts),
        max_pages=max_pages or settings.crawl_max_pages,
    )
    LOGGER.info("Starting content inventory crawl")
    process.start()
    _REACTOR_ALREADY_USED = True

    item_count = int(crawler.stats.get_value("item_scraped_count", 0) or 0)
    stored = bool(settings.mongodb_uri)
    LOGGER.info("Content inventory finished: %d pages", item_count)
    return InventoryResult(item_count=item_count, output_path=output_path, stored=stored)
