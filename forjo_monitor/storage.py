"""Persist audit runs to MongoDB Atlas and read back the previous run.

The free M0 tier is more than enough: each run stores one summary document plus
one document per audited page.
"""

from __future__ import annotations

import logging
from typing import Any

from forjo_monitor.config import Settings
from forjo_monitor.models import AuditRun

LOGGER = logging.getLogger(__name__)

RUNS_COLLECTION = "runs"
PAGES_COLLECTION = "pages"


class AuditStore:
    """Thin wrapper over two collections, with degraded mode when unconfigured."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Any = None
        self._database: Any = None

    @property
    def available(self) -> bool:
        return self._client is not None

    def connect(self) -> "AuditStore":
        """Open the connection and make sure the indexes exist."""
        if not self._settings.has_storage:
            LOGGER.warning("MONGODB_URI is not set: running without persistence")
            return self

        from pymongo import ASCENDING, DESCENDING, MongoClient

        uri = self._settings.require_storage()
        self._client = MongoClient(uri, serverSelectionTimeoutMS=15_000, appname="forjo-monitor")
        self._database = self._client[self._settings.mongodb_database]
        self._database[RUNS_COLLECTION].create_index(
            [("site_base_url", ASCENDING), ("started_at", DESCENDING)]
        )
        self._database[PAGES_COLLECTION].create_index(
            [("run_id", ASCENDING), ("page.url", ASCENDING)]
        )
        LOGGER.info("Connected to MongoDB database %r", self._settings.mongodb_database)
        return self

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
            self._database = None

    def save_run(self, run: AuditRun) -> None:
        """Write the run summary and every page document."""
        if self._database is None:
            return
        self._database[RUNS_COLLECTION].replace_one(
            {"run_id": run.run_id}, run.to_dict(), upsert=True
        )
        pages = self._database[PAGES_COLLECTION]
        for page in run.pages:
            document = page.to_dict()
            document["run_id"] = run.run_id
            document["site_base_url"] = run.site_base_url
            pages.replace_one(
                {"run_id": run.run_id, "page.url": page.page.url}, document, upsert=True
            )
        LOGGER.info("Stored run %s (%d pages)", run.run_id, run.page_count)

    def previous_run(self, site_base_url: str, exclude_run_id: str = "") -> dict[str, Any] | None:
        """Return the most recent stored run summary for this site."""
        if self._database is None:
            return None
        query: dict[str, Any] = {"site_base_url": site_base_url}
        if exclude_run_id:
            query["run_id"] = {"$ne": exclude_run_id}
        return self._database[RUNS_COLLECTION].find_one(query, sort=[("started_at", -1)])

    def recent_runs(self, site_base_url: str, limit: int = 10) -> list[dict[str, Any]]:
        """Return the newest run summaries, for trend reporting."""
        if self._database is None:
            return []
        cursor = (
            self._database[RUNS_COLLECTION]
            .find({"site_base_url": site_base_url})
            .sort("started_at", -1)
            .limit(limit)
        )
        return list(cursor)

    def worst_pages(self, run_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Return the pages with the most failing checks in a run."""
        if self._database is None:
            return []
        cursor = self._database[PAGES_COLLECTION].aggregate(
            [
                {"$match": {"run_id": run_id}},
                {"$addFields": {"fail_count": {"$ifNull": ["$counts.fail", 0]}}},
                {"$sort": {"fail_count": -1, "page.url": 1}},
                {"$limit": limit},
                {
                    "$project": {
                        "_id": 0,
                        "url": "$page.url",
                        "fail_count": 1,
                        "counts": 1,
                    }
                },
            ]
        )
        return list(cursor)
