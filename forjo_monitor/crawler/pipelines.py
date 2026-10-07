"""Item pipelines: one writes JSON Lines, one writes to MongoDB Atlas."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from forjo_monitor.crawler.items import ContentItem

LOGGER = logging.getLogger(__name__)

CONTENT_COLLECTION = "content"
DEFAULT_INVENTORY_OUTPUT = "reports/content-inventory.jsonl"


class JsonLinesContentPipeline:
    """Write every item to a ``.jsonl`` file under the reports directory."""

    def __init__(self, output_path: Path) -> None:
        self._output_path = output_path
        self._handle: Any = None

    @classmethod
    def from_crawler(cls, crawler: Any) -> "JsonLinesContentPipeline":
        raw = crawler.settings.get("INVENTORY_OUTPUT") or DEFAULT_INVENTORY_OUTPUT
        return cls(Path(raw))

    def open_spider(self, spider: Any) -> None:
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self._output_path.open("w", encoding="utf-8")
        LOGGER.info("Writing content inventory to %s", self._output_path)

    def close_spider(self, spider: Any) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def process_item(self, item: ContentItem, spider: Any) -> ContentItem:
        if self._handle is not None:
            payload = json.dumps(item.to_dict(), ensure_ascii=False, default=str)
            self._handle.write(payload + "\n")
        return item


class MongoContentPipeline:
    """Upsert every item into the ``content`` collection."""

    def __init__(self, uri: str, database_name: str) -> None:
        self._uri = uri
        self._database_name = database_name
        self._client: Any = None
        self._collection: Any = None

    @classmethod
    def from_crawler(cls, crawler: Any) -> "MongoContentPipeline":
        return cls(
            uri=crawler.settings.get("MONGODB_URI") or "",
            database_name=crawler.settings.get("MONGODB_DATABASE") or "forjo_monitor",
        )

    def open_spider(self, spider: Any) -> None:
        if not self._uri:
            LOGGER.warning("MONGODB_URI not set: content inventory will not be persisted")
            return
        from pymongo import MongoClient

        self._client = MongoClient(self._uri, serverSelectionTimeoutMS=15_000)
        self._collection = self._client[self._database_name][CONTENT_COLLECTION]
        self._collection.create_index("url", unique=True)

    def close_spider(self, spider: Any) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
            self._collection = None

    def process_item(self, item: ContentItem, spider: Any) -> ContentItem:
        if self._collection is not None:
            self._collection.replace_one({"url": item.url}, item.to_dict(), upsert=True)
        return item
