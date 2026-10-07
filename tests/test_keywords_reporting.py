"""Tests for the keyword extractor, the reporter and configuration."""

from __future__ import annotations

import json

import pytest

from forjo_monitor.alerts import build_summary
from forjo_monitor.analyzers.keywords import bigrams, normalize_token, tokenize, top_keywords
from forjo_monitor.checks import Check, CheckId, CheckStatus, Severity
from forjo_monitor.config import ConfigError, Settings
from forjo_monitor.models import (
    AuditRun,
    HttpSnapshot,
    PageAudit,
    PageRef,
    PerformanceMetrics,
    SeoFacts,
    utc_now,
)
from forjo_monitor.reporting import render_json, render_markdown, write_reports

ARABIC_TEXT = (
    "الربح من التدوين للمبتدئين. الربح من التدوين يحتاج صبراً. التدوين مهنة "
    "تحتاج محتوى جيد، والمحتوى الجيد يجلب الزيارات. الزيارات تعني الربح."
)


def test_normalize_token_unifies_arabic_forms() -> None:
    assert normalize_token("أحمد") == normalize_token("احمد")
    assert normalize_token("مكتبة") == normalize_token("مكتبه")


def test_tokenize_drops_stopwords_and_short_tokens() -> None:
    tokens = tokenize("من في الربح على التدوين و the and a job")
    assert "الربح" in tokens
    assert "التدوين" in tokens
    assert "من" not in tokens
    assert "the" not in tokens


def test_top_keywords_ranks_repeated_terms() -> None:
    ranked = dict(top_keywords(ARABIC_TEXT, limit=5))
    assert ranked
    assert ranked["الربح"] >= ranked["محتوى"] if "محتوى" in ranked else True
    assert len(ranked) <= 5


def test_bigrams_builds_phrases() -> None:
    phrases = bigrams(tokenize(ARABIC_TEXT), limit=5)
    assert phrases
    assert all(" " in phrase for phrase, _ in phrases)


def _sample_page(url: str, *, fails: int) -> PageAudit:
    checks = [
        Check(CheckId.HTTP_OK, "الصفحة تُرجع 200", CheckStatus.PASS, Severity.CRITICAL, "HTTP 200")
    ]
    for index in range(fails):
        checks.append(
            Check(
                f"test.check_{index}",
                f"فحص تجريبي {index}",
                CheckStatus.FAIL,
                Severity.MAJOR,
                "تفصيل",
            )
        )
    return PageAudit(
        page=PageRef(url=url, source="sitemap"),
        audit_id="run-1",
        started_at=utc_now(),
        snapshot=HttpSnapshot(url, 200, "text/html", 2048, 0),
        seo=SeoFacts(title="عنوان", meta_description="وصف"),
        checks=checks,
        performance=PerformanceMetrics(ttfb_ms=120.0, lcp_ms=1800.0),
    )


def _sample_run() -> AuditRun:
    run = AuditRun(run_id="run-1", site_base_url="https://www.forjo.tech", started_at=utc_now())
    run.pages.append(_sample_page("https://www.forjo.tech/a.html", fails=0))
    run.pages.append(_sample_page("https://www.forjo.tech/b.html", fails=2))
    run.finished_at = utc_now()
    return run


def test_render_markdown_lists_failing_pages() -> None:
    markdown = render_markdown(_sample_run(), previous_totals={"fail": 0})
    assert "تقرير فحص موقع" in markdown
    assert "https://www.forjo.tech/b.html" in markdown
    assert "fail" in markdown


def test_render_json_is_valid_and_complete() -> None:
    payload = json.loads(render_json(_sample_run()))
    assert payload["run_id"] == "run-1"
    assert payload["page_count"] == 2
    assert len(payload["pages"]) == 2
    assert payload["pages"][1]["counts"]["fail"] == 2


def test_write_reports_creates_all_three_files(tmp_path) -> None:
    paths = write_reports(_sample_run(), tmp_path)
    assert paths.markdown.is_file()
    assert paths.json.is_file()
    assert paths.history.is_file()
    assert paths.markdown.read_text(encoding="utf-8").strip()
    assert len(paths.history.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_build_summary_reports_the_trend() -> None:
    summary = build_summary(_sample_run(), previous_totals={"fail": 0})
    assert "forjo-monitor" in summary
    assert "pages audited: 2" in summary
    assert "failures vs previous run: +2" in summary


def test_build_summary_without_previous_run() -> None:
    summary = build_summary(_sample_run(), None)
    assert "vs previous run" not in summary


def test_settings_defaults_and_host_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "SITE_BASE_URL",
        "SITE_EXTRA_HOSTS",
        "MONGODB_URI",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()

    assert settings.site_base_url == "https://www.forjo.tech"
    assert settings.owned_hosts == frozenset({"forjo.tech"})
    assert settings.has_storage is False
    assert settings.has_telegram is False


def test_settings_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SITE_BASE_URL", "https://example.org/")
    monkeypatch.setenv("SITE_EXTRA_HOSTS", "blog.example.org, cdn.example.org")
    monkeypatch.setenv("MONGODB_URI", "mongodb+srv://u:p@c.mongodb.net/")
    monkeypatch.setenv("BROWSER_AUDIT_ENABLED", "false")
    monkeypatch.setenv("CRAWL_DELAY_SECONDS", "0.5")

    settings = Settings.from_env()

    assert settings.site_base_url == "https://example.org"
    assert settings.owned_hosts == frozenset({"example.org", "blog.example.org", "cdn.example.org"})
    assert settings.browser_audit_enabled is False
    assert settings.crawl_delay_seconds == 0.5


def test_settings_rejects_bad_boolean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BROWSER_AUDIT_ENABLED", "maybe")
    with pytest.raises(ConfigError):
        Settings.from_env()


def test_require_storage_explains_the_missing_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MONGODB_URI", raising=False)
    settings = Settings.from_env()
    with pytest.raises(ConfigError):
        settings.require_storage()
