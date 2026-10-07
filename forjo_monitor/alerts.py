"""Optional Telegram notifications.

Plain text only, so nothing needs escaping. If no token is configured the
notifier silently no-ops.
"""

from __future__ import annotations

import logging

import requests

from forjo_monitor.config import Settings
from forjo_monitor.models import AuditRun

LOGGER = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
REQUEST_TIMEOUT = 15
MAX_MESSAGE_CHARS = 3900
TOP_FAILING_PAGES = 8


def build_summary(run: AuditRun, previous_totals: dict[str, int] | None = None) -> str:
    """A short, readable summary of one audit run."""
    totals = run.total_counts
    lines = [
        f"forjo-monitor — {run.site_base_url}",
        f"pages audited: {run.page_count}",
        f"pass: {totals.get('pass', 0)}  warn: {totals.get('warn', 0)}  "
        f"fail: {totals.get('fail', 0)}  skip: {totals.get('skip', 0)}",
    ]

    if previous_totals is not None:
        delta = totals.get("fail", 0) - previous_totals.get("fail", 0)
        trend = f"{delta:+d}" if delta else "no change"
        lines.append(f"failures vs previous run: {trend}")

    failures = sorted(
        run.failing_pages, key=lambda page: len(page.failed_checks), reverse=True
    )[:TOP_FAILING_PAGES]

    if failures:
        lines.append("")
        lines.append("worst pages:")
        for page in failures:
            reasons = ", ".join(check.check_id for check in page.failed_checks[:3])
            suffix = f" — {reasons}" if reasons else ""
            lines.append(f"• {page.page.url} ({len(page.failed_checks)} fail){suffix}")
    else:
        lines.append("")
        lines.append("no failing checks on any audited page.")

    return "\n".join(lines)


class TelegramNotifier:
    """Sends the run summary to a chat the user controls."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def enabled(self) -> bool:
        return self._settings.has_telegram

    def send(self, text: str) -> bool:
        """Post one message. Returns ``True`` when Telegram accepted it."""
        if not self.enabled:
            LOGGER.info("Telegram is not configured; skipping notification")
            return False

        url = f"{TELEGRAM_API}/bot{self._settings.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": self._settings.telegram_chat_id,
            "text": text[:MAX_MESSAGE_CHARS],
            "disable_web_page_preview": True,
        }
        try:
            response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            LOGGER.warning("Telegram request failed: %s", exc)
            return False

        if response.status_code != 200:
            LOGGER.warning("Telegram rejected the message: HTTP %s", response.status_code)
            return False
        return True

    def notify_run(self, run: AuditRun, previous_totals: dict[str, int] | None) -> bool:
        """Send the standard run summary."""
        return self.send(build_summary(run, previous_totals))
