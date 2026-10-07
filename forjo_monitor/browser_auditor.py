"""Real-browser observation of the site owner's own pages.

A headless Chromium loads each page once, records Core Web Vitals, counts
console errors and measures where ad-network elements actually render. It
never clicks, scrolls-to, or otherwise engages an ad unit.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from forjo_monitor.browser_scripts import (
    AD_ELEMENT_PROBE,
    AD_RESOURCE_PROBE,
    INIT_METRICS_PROBE,
    NAVIGATION_TIMING_PROBE,
)
from forjo_monitor.config import Settings
from forjo_monitor.models import AdObservation, PerformanceMetrics

LOGGER = logging.getLogger(__name__)

VIEWPORT_WIDTH = 1366
VIEWPORT_HEIGHT = 900
SETTLE_MILLISECONDS = 2500
MAX_RECORDED_JS_ERRORS = 20


@dataclass
class BrowserOutcome:
    """Everything one headless page load produced."""

    performance: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    ads: list[AdObservation] = field(default_factory=list)
    js_errors: list[str] = field(default_factory=list)
    screenshot_path: str = ""
    error: str = ""

    @property
    def succeeded(self) -> bool:
        return not self.error

    @property
    def needs_screenshot(self) -> bool:
        """Capture evidence when something looks wrong, not on every page."""
        return bool(self.error) or bool(self.js_errors) or not self.ads


def screenshot_name(url: str) -> str:
    """A stable, filesystem-safe file name for a page URL."""
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    return f"page-{digest}.png"


def _geometry_observations(elements: list[dict[str, Any]]) -> dict[str, AdObservation]:
    observations: dict[str, AdObservation] = {}
    for element in elements:
        network = str(element.get("network", ""))
        if not network:
            continue
        width = float(element.get("width") or 0.0)
        height = float(element.get("height") or 0.0)
        top = float(element.get("top") or 0.0)
        viewport_width = float(element.get("viewportWidth") or 1.0)
        viewport_height = float(element.get("viewportHeight") or 1.0)
        observations[network] = AdObservation(
            network=network,
            kind=str(element.get("tag", "unknown")),
            resource_url=str(element.get("url", "")),
            detected_in_dom=True,
            visible=width > 0 and height > 0,
            coverage_ratio=(width * height) / (viewport_width * viewport_height),
            above_the_fold=0 <= top < viewport_height,
        )
    return observations


def _resource_observations(resources: list[dict[str, Any]]) -> dict[str, AdObservation]:
    observations: dict[str, AdObservation] = {}
    for resource in resources:
        network = str(resource.get("network", ""))
        if not network or network in observations:
            continue
        observations[network] = AdObservation(
            network=network,
            kind=str(resource.get("kind", "other")),
            resource_url=str(resource.get("url", "")),
            detected_in_dom=True,
        )
    return observations


def merge_ad_observations(
    elements: list[dict[str, Any]], resources: list[dict[str, Any]]
) -> list[AdObservation]:
    """Combine geometry (from the DOM) with delivery (from the network log)."""
    merged = _resource_observations(resources)
    merged.update(_geometry_observations(elements))
    return sorted(merged.values(), key=lambda item: item.network)


def _metrics_from_payload(payload: dict[str, Any], js_error_count: int) -> PerformanceMetrics:
    def milliseconds(key: str) -> float | None:
        value = payload.get(key)
        return float(value) if isinstance(value, (int, float)) and value > 0 else None

    return PerformanceMetrics(
        ttfb_ms=milliseconds("ttfb"),
        dom_content_loaded_ms=milliseconds("domContentLoaded"),
        load_ms=milliseconds("load"),
        lcp_ms=milliseconds("lcp"),
        cumulative_layout_shift=float(payload.get("cls") or 0.0),
        request_count=int(payload.get("requestCount") or 0),
        transfer_bytes=int(payload.get("transferBytes") or 0),
        js_error_count=js_error_count,
    )


class BrowserAuditor:
    """A reusable headless browser shared across every page of one run."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._playwright: Any = None
        self._browser: Any = None

    def __enter__(self) -> "BrowserAuditor":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - depends on local install
            raise RuntimeError(
                "Playwright is not installed. Run: pip install playwright "
                "&& python -m playwright install chromium"
            ) from exc

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self._settings.browser_headless)
        LOGGER.info("Headless Chromium started (headless=%s)", self._settings.browser_headless)
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def _new_page(self, context: Any) -> tuple[Any, list[str]]:
        page = context.new_page()
        errors: list[str] = []

        def record(kind: str, message: str) -> None:
            if len(errors) < MAX_RECORDED_JS_ERRORS:
                errors.append(f"[{kind}] {message}")

        page.on("pageerror", lambda exc: record("pageerror", str(exc)))
        page.on(
            "console",
            lambda msg: record("console", msg.text) if msg.type == "error" else None,
        )
        return page, errors

    def _capture(self, page: Any, url: str) -> str:
        target_dir: Path = self._settings.artifacts_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / screenshot_name(url)
        try:
            page.screenshot(path=str(path), full_page=False)
        except Exception as exc:  # noqa: BLE001 - evidence capture must never abort a run
            LOGGER.warning("Screenshot failed for %s: %s", url, exc)
            return ""
        return str(path)

    def audit(self, url: str) -> BrowserOutcome:
        """Load one page once and report what the browser observed."""
        if self._browser is None:
            raise RuntimeError("BrowserAuditor must be used as a context manager")

        context = self._browser.new_context(
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
            ignore_https_errors=True,
        )
        context.add_init_script(script=INIT_METRICS_PROBE)
        page, js_errors = self._new_page(context)

        try:
            page.goto(
                url,
                wait_until="load",
                timeout=self._settings.browser_timeout_ms,
            )
            page.wait_for_timeout(SETTLE_MILLISECONDS)
            domains = list(self._settings.ad_network_domains)
            payload = page.evaluate(NAVIGATION_TIMING_PROBE)
            elements = page.evaluate(AD_ELEMENT_PROBE, domains)
            resources = page.evaluate(AD_RESOURCE_PROBE, domains)
        except Exception as exc:  # noqa: BLE001 - a single bad page must not stop the run
            LOGGER.warning("Browser audit failed for %s: %s", url, exc)
            outcome = BrowserOutcome(js_errors=js_errors, error=str(exc))
            if outcome.needs_screenshot:
                outcome.screenshot_path = self._capture(page, url)
            context.close()
            return outcome

        outcome = BrowserOutcome(
            performance=_metrics_from_payload(payload, len(js_errors)),
            ads=merge_ad_observations(elements, resources),
            js_errors=js_errors,
        )
        if outcome.needs_screenshot:
            outcome.screenshot_path = self._capture(page, url)
        context.close()
        return outcome
