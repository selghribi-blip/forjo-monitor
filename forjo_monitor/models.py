"""Typed records produced by an audit run.

Every record is JSON-serialisable so the same object can go straight to
MongoDB, to a Markdown report and to a Telegram message.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from forjo_monitor.checks import Check, CheckStatus


def utc_now() -> datetime:
    """Timezone-aware UTC timestamp (naive datetimes are deprecated in Mongo)."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class PageRef:
    """A page discovered on the site under audit."""

    url: str
    source: str
    last_modified: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"url": self.url, "source": self.source, "last_modified": self.last_modified}


@dataclass(frozen=True)
class HttpSnapshot:
    """What the initial HTTP exchange looked like."""

    final_url: str
    status_code: int
    content_type: str
    html_bytes: int
    redirects: int

    @property
    def is_ok(self) -> bool:
        return 200 <= self.status_code < 300

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_url": self.final_url,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "html_bytes": self.html_bytes,
            "redirects": self.redirects,
        }


@dataclass(frozen=True)
class SeoFacts:
    """Everything the static HTML says about how the page presents itself."""

    title: str = ""
    meta_description: str = ""
    canonical: str = ""
    robots_meta: str = ""
    html_lang: str = ""
    h1_texts: tuple[str, ...] = ()
    h2_count: int = 0
    image_count: int = 0
    images_without_alt: int = 0
    internal_links: int = 0
    external_links: int = 0
    word_count: int = 0
    has_open_graph: bool = False
    has_og_image: bool = False
    has_json_ld: bool = False
    json_ld_types: tuple[str, ...] = ()

    @property
    def title_length(self) -> int:
        return len(self.title)

    @property
    def meta_description_length(self) -> int:
        return len(self.meta_description)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "title_length": self.title_length,
            "meta_description": self.meta_description,
            "meta_description_length": self.meta_description_length,
            "canonical": self.canonical,
            "robots_meta": self.robots_meta,
            "html_lang": self.html_lang,
            "h1_texts": list(self.h1_texts),
            "h2_count": self.h2_count,
            "image_count": self.image_count,
            "images_without_alt": self.images_without_alt,
            "internal_links": self.internal_links,
            "external_links": self.external_links,
            "word_count": self.word_count,
            "has_open_graph": self.has_open_graph,
            "has_og_image": self.has_og_image,
            "has_json_ld": self.has_json_ld,
            "json_ld_types": list(self.json_ld_types),
        }


@dataclass(frozen=True)
class AdObservation:
    """Presence and placement of one ad-network resource on the page."""

    network: str
    kind: str
    resource_url: str
    detected_in_dom: bool = False
    visible: bool = False
    coverage_ratio: float = 0.0
    above_the_fold: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "network": self.network,
            "kind": self.kind,
            "resource_url": self.resource_url,
            "detected_in_dom": self.detected_in_dom,
            "visible": self.visible,
            "coverage_ratio": round(self.coverage_ratio, 4),
            "above_the_fold": self.above_the_fold,
        }


@dataclass(frozen=True)
class PerformanceMetrics:
    """Real-browser timings. All values are ``None`` in HTTP-only mode."""

    ttfb_ms: float | None = None
    dom_content_loaded_ms: float | None = None
    load_ms: float | None = None
    lcp_ms: float | None = None
    cumulative_layout_shift: float | None = None
    request_count: int | None = None
    transfer_bytes: int | None = None
    js_error_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ttfb_ms": self.ttfb_ms,
            "dom_content_loaded_ms": self.dom_content_loaded_ms,
            "load_ms": self.load_ms,
            "lcp_ms": self.lcp_ms,
            "cumulative_layout_shift": self.cumulative_layout_shift,
            "request_count": self.request_count,
            "transfer_bytes": self.transfer_bytes,
            "js_error_count": self.js_error_count,
        }


@dataclass
class PageAudit:
    """The full result for a single page."""

    page: PageRef
    audit_id: str
    started_at: datetime
    snapshot: HttpSnapshot
    seo: SeoFacts
    checks: list[Check] = field(default_factory=list)
    ads: list[AdObservation] = field(default_factory=list)
    performance: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    screenshot_path: str = ""
    error: str = ""

    @property
    def failed_checks(self) -> list[Check]:
        return [check for check in self.checks if check.status is CheckStatus.FAIL]

    @property
    def counts(self) -> dict[str, int]:
        counts = {status.value: 0 for status in CheckStatus}
        for check in self.checks:
            counts[check.status.value] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "page": self.page.to_dict(),
            "started_at": self.started_at,
            "snapshot": self.snapshot.to_dict(),
            "seo": self.seo.to_dict(),
            "ads": [ad.to_dict() for ad in self.ads],
            "performance": self.performance.to_dict(),
            "checks": [check.to_dict() for check in self.checks],
            "counts": self.counts,
            "screenshot_path": self.screenshot_path,
            "error": self.error,
        }


@dataclass
class AuditRun:
    """One execution of the whole audit."""

    run_id: str
    site_base_url: str
    started_at: datetime
    finished_at: datetime | None = None
    pages: list[PageAudit] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def total_counts(self) -> dict[str, int]:
        totals = {status.value: 0 for status in CheckStatus}
        for page in self.pages:
            for name, value in page.counts.items():
                totals[name] += value
        return totals

    @property
    def failing_pages(self) -> list[PageAudit]:
        return [page for page in self.pages if page.failed_checks or page.error]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "site_base_url": self.site_base_url,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "page_count": self.page_count,
            "totals": self.total_counts,
            "pages": [page.to_dict() for page in self.pages],
        }
