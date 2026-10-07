"""Render an audit run as Markdown and JSON, and write both to disk."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from forjo_monitor.checks import CheckStatus
from forjo_monitor.models import AuditRun, PageAudit

JSON_FILE_NAME = "latest.json"
MARKDOWN_FILE_NAME = "latest.md"
HISTORY_FILE_NAME = "history.jsonl"
MAX_DETAILED_PAGES = 40


@dataclass(frozen=True)
class ReportPaths:
    """Where the run's artefacts were written."""

    markdown: Path
    json: Path
    history: Path


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def render_json(run: AuditRun) -> str:
    """Serialise the whole run, including every page."""
    return json.dumps(run.to_dict(), ensure_ascii=False, indent=2, default=_json_default)


def _duration_seconds(run: AuditRun) -> float | None:
    if run.finished_at is None:
        return None
    return (run.finished_at - run.started_at).total_seconds()


def _totals_table(run: AuditRun, previous_totals: dict[str, int] | None) -> list[str]:
    totals = run.total_counts
    rows = ["| المقياس | العدد |", "| --- | --- |", f"| صفحات مفحوصة | {run.page_count} |"]
    for key in ("pass", "warn", "fail", "skip"):
        value = totals.get(key, 0)
        rows.append(f"| {key} | {value} |")
    if previous_totals is not None:
        delta = totals.get("fail", 0) - previous_totals.get("fail", 0)
        rows.append(f"| تغيّر حالات الفشل عن التشغيل السابق | {delta:+d} |")
    return rows


def _failing_pages_table(run: AuditRun) -> list[str]:
    failures = sorted(run.failing_pages, key=lambda page: len(page.failed_checks), reverse=True)
    if not failures:
        return ["لا توجد صفحات بها حالات فشل."]

    lines = ["| الصفحة | حالات الفشل | أول ثلاثة أسباب |", "| --- | --- | --- |"]
    for page in failures[:MAX_DETAILED_PAGES]:
        reasons = ", ".join(check.check_id for check in page.failed_checks[:3])
        lines.append(f"| {page.page.url} | {len(page.failed_checks)} | {reasons or '-'} |")
    return lines


def _ad_coverage_lines(run: AuditRun) -> list[str]:
    pages_with_ads = sum(1 for page in run.pages if page.ads)
    networks: dict[str, int] = {}
    for page in run.pages:
        for observation in page.ads:
            networks[observation.network] = networks.get(observation.network, 0) + 1

    lines = [
        f"- صفحات عليها مورد إعلاني واحد على الأقل: {pages_with_ads}/{run.page_count}",
        f"- شبكات تم رصدها: {', '.join(sorted(networks)) if networks else 'لا شيء'}",
    ]
    for network, count in sorted(networks.items(), key=lambda item: -item[1]):
        lines.append(f"  - {network}: ظهرت في {count} صفحة")
    return lines


def _slowest_pages_lines(run: AuditRun) -> list[str]:
    measured = [page for page in run.pages if page.performance.lcp_ms is not None]
    if not measured:
        return ["لم تُقس الأزمنة (شغّل وضع المتصفح لقياس Core Web Vitals)."]

    measured.sort(key=lambda page: page.performance.lcp_ms or 0.0, reverse=True)
    lines = ["| الصفحة | LCP (ms) | TTFB (ms) | CLS |", "| --- | --- | --- | --- |"]
    for page in measured[:10]:
        metrics = page.performance
        lines.append(
            f"| {page.page.url} | {metrics.lcp_ms:.0f} | "
            f"{metrics.ttfb_ms:.0f} | {metrics.cumulative_layout_shift or 0.0:.3f} |"
        )
    return lines


def _page_detail_lines(page: PageAudit) -> list[str]:
    lines = [f"### {page.page.url}", ""]
    if page.error:
        lines.append(f"- خطأ أثناء الفحص: {page.error}")
    failed = [check for check in page.checks if check.status is CheckStatus.FAIL]
    if not failed:
        lines.append("- لا حالات فشل.")
    for check in failed:
        lines.append(f"- [{check.severity.value}] {check.label} — {check.detail}")
    lines.append("")
    return lines


def render_markdown(run: AuditRun, previous_totals: dict[str, int] | None = None) -> str:
    """A human-readable report in Arabic (RTL-friendly plain Markdown)."""
    duration = _duration_seconds(run)
    header = [
        "# تقرير فحص موقع forjo.tech",
        "",
        f"- الموقع: {run.site_base_url}",
        f"- معرّف التشغيل: `{run.run_id}`",
        f"- البداية: {run.started_at.isoformat()}",
    ]
    if duration is not None:
        header.append(f"- المدة: {duration:.1f} ثانية")

    sections: list[tuple[str, list[str]]] = [
        ("## الملخص", _totals_table(run, previous_totals)),
        ("## الإعلانات", _ad_coverage_lines(run)),
        ("## الصفحات الأكثر فشلاً", _failing_pages_table(run)),
        ("## أبطأ الصفحات", _slowest_pages_lines(run)),
    ]

    body: list[str] = []
    detailed = sorted(run.failing_pages, key=lambda page: len(page.failed_checks), reverse=True)
    if detailed:
        body.append("## تفاصيل الصفحات التي تحتاج إصلاحاً")
        body.append("")
        for page in detailed[:MAX_DETAILED_PAGES]:
            body.extend(_page_detail_lines(page))

    lines = [*header, ""]
    for title, content in sections:
        lines.append(title)
        lines.append("")
        lines.extend(content)
        lines.append("")
    lines.extend(body)
    return "\n".join(lines)


def write_reports(
    run: AuditRun, reports_dir: Path, previous_totals: dict[str, int] | None = None
) -> ReportPaths:
    """Write ``latest.json``, ``latest.md`` and append to ``history.jsonl``."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / JSON_FILE_NAME
    markdown_path = reports_dir / MARKDOWN_FILE_NAME
    history_path = reports_dir / HISTORY_FILE_NAME

    json_path.write_text(render_json(run), encoding="utf-8")
    markdown_path.write_text(render_markdown(run, previous_totals), encoding="utf-8")

    summary = {
        "run_id": run.run_id,
        "site_base_url": run.site_base_url,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "page_count": run.page_count,
        "totals": run.total_counts,
    }
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(summary, ensure_ascii=False, default=_json_default))
        handle.write("\n")

    return ReportPaths(markdown=markdown_path, json=json_path, history=history_path)
