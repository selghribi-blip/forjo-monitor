"""The vocabulary of audit results: statuses, severities and check records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class CheckStatus(str, Enum):
    """Outcome of a single audit check."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


class Severity(str, Enum):
    """How much a failing check matters for traffic and revenue."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


@dataclass(frozen=True)
class Check:
    """One named assertion about one page."""

    check_id: str
    label: str
    status: CheckStatus
    severity: Severity
    detail: str = ""

    @property
    def is_failure(self) -> bool:
        return self.status is CheckStatus.FAIL

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "label": self.label,
            "status": self.status.value,
            "severity": self.severity.value,
            "detail": self.detail,
        }


class CheckId:
    """Stable identifiers so reports and history stay comparable across runs."""

    HTTP_OK = "http.status_ok"
    HTTPS = "http.https"
    TITLE_PRESENT = "seo.title_present"
    TITLE_LENGTH = "seo.title_length"
    META_DESCRIPTION = "seo.meta_description"
    CANONICAL = "seo.canonical"
    ROBOTS_META = "seo.robots_meta"
    HEADING_ONE = "seo.single_h1"
    OPEN_GRAPH = "seo.open_graph"
    STRUCTURED_DATA = "seo.structured_data"
    LANG_ATTR = "seo.html_lang"
    IMAGE_ALT = "a11y.image_alt"
    INTERNAL_LINKS = "links.internal"
    BROKEN_LINKS = "links.broken"
    AD_SCRIPT_PRESENT = "ads.script_present"
    AD_SLOT_VISIBLE = "ads.slot_visible"
    AD_ABOVE_FOLD = "ads.above_fold"
    PAGE_WEIGHT = "perf.page_weight"
    TTFB = "perf.ttfb"
    LCP = "perf.lcp"
    CLS = "perf.cls"
    JS_ERRORS = "perf.js_errors"
