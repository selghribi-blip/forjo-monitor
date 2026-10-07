"""Orchestrate a full audit run: discover, fetch, measure, store, report."""

from __future__ import annotations

import logging
from contextlib import ExitStack
from dataclasses import dataclass
from uuid import uuid4

from forjo_monitor.alerts import TelegramNotifier
from forjo_monitor.browser_auditor import BrowserAuditor
from forjo_monitor.config import Settings
from forjo_monitor.discovery import build_session, discover_pages
from forjo_monitor.models import AuditRun, utc_now
from forjo_monitor.page_audit import audit_single_page
from forjo_monitor.reporting import ReportPaths, write_reports
from forjo_monitor.storage import AuditStore

LOGGER = logging.getLogger(__name__)

PROGRESS_EVERY = 10


@dataclass(frozen=True)
class AuditOptions:
    """Per-invocation switches, all optional."""

    limit: int = 0
    use_browser: bool = True
    check_links: bool = True
    notify: bool = True


@dataclass(frozen=True)
class AuditResult:
    """Everything the caller needs to know after a run."""

    run: AuditRun
    reports: ReportPaths
    previous_failures: int | None
    stored: bool


class AuditRunner:
    """Runs the whole pipeline once."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _open_browser(self, stack: ExitStack, enabled: bool) -> BrowserAuditor | None:
        if not enabled or not self._settings.browser_audit_enabled:
            LOGGER.info("Browser auditing disabled: running HTTP-only")
            return None
        try:
            return stack.enter_context(BrowserAuditor(self._settings))
        except RuntimeError as exc:
            LOGGER.warning("Browser auditing unavailable, falling back to HTTP-only: %s", exc)
            return None

    def _audit_all(
        self, run: AuditRun, options: AuditOptions, browser: BrowserAuditor | None
    ) -> None:
        session = build_session()
        page_refs = discover_pages(self._settings, session)
        if options.limit > 0:
            page_refs = page_refs[: options.limit]

        LOGGER.info("Auditing %d pages on %s", len(page_refs), run.site_base_url)
        total = len(page_refs)

        for index, page_ref in enumerate(page_refs, start=1):
            page = audit_single_page(
                settings=self._settings,
                session=session,
                page_ref=page_ref,
                run_id=run.run_id,
                browser=browser,
                check_links=options.check_links,
            )
            run.pages.append(page)
            if index % PROGRESS_EVERY == 0 or index == total:
                LOGGER.info("Progress %d/%d", index, total)

    def run(self, options: AuditOptions | None = None) -> AuditResult:
        """Execute the pipeline and return the run plus its artefacts."""
        chosen = options or AuditOptions()
        run = AuditRun(
            run_id=uuid4().hex[:12],
            site_base_url=self._settings.site_base_url,
            started_at=utc_now(),
        )

        store = AuditStore(self._settings).connect()
        try:
            previous = store.previous_run(
                self._settings.site_base_url, exclude_run_id=run.run_id
            )
            previous_totals = previous.get("totals") if previous else None
            previous_failures = previous_totals.get("fail") if previous_totals else None

            with ExitStack() as stack:
                browser = self._open_browser(stack, chosen.use_browser)
                self._audit_all(run, chosen, browser)

            run.finished_at = utc_now()
            reports = write_reports(run, self._settings.reports_dir, previous_totals)
            store.save_run(run)

            if chosen.notify and self._settings.alert_on_regression:
                notifier = TelegramNotifier(self._settings)
                notifier.notify_run(run, previous_totals)

            return AuditResult(
                run=run,
                reports=reports,
                previous_failures=previous_failures,
                stored=store.available,
            )
        finally:
            store.close()
