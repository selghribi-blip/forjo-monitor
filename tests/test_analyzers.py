"""Tests for HTML fact extraction, ad detection and the rule engine."""

from __future__ import annotations

from forjo_monitor.analyzers.ad_detector import (
    detect_static_ad_resources,
    match_network,
    merge_observations,
)
from forjo_monitor.analyzers.aggregate import build_page_checks
from forjo_monitor.analyzers.html_facts import extract_seo_facts, normalize_host
from forjo_monitor.checks import CheckId, CheckStatus
from forjo_monitor.models import AdObservation, HttpSnapshot, PerformanceMetrics

OWNED = frozenset({"forjo.tech"})
AD_DOMAINS = ("adsterra.com", "monetag.com", "profitableratecpm.com")

GOOD_PAGE = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <title>دليل شامل للربح من التدوين للطلاب خطوة بخطوة</title>
  <meta name="description" content="دليل عملي يشرح كيف يبدأ الطالب مدونة ويربح منها، مع خطوات نشر المحتوى وتحسين الظهور في محركات البحث.">
  <link rel="canonical" href="https://www.forjo.tech/2026/08/blog-post_294.html">
  <meta property="og:title" content="دليل شامل للربح من التدوين">
  <meta property="og:image" content="https://www.forjo.tech/cover.png">
  <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"BlogPosting","headline":"دليل"}
  </script>
  <script src="https://pl12345.profitableratecpm.com/aa/bb/cc/invoke.js"></script>
</head>
<body>
  <h1>دليل شامل للربح من التدوين</h1>
  <h2>الخطوة الأولى</h2>
  <h2>الخطوة الثانية</h2>
  <img src="/a.png" alt="صورة توضيحية">
  <a href="/2026/08/blog-post_613.html">مقال آخر</a>
  <a href="/2026/08/blog-post_480.html">مقال ثالث</a>
  <a href="/about.html">من نحن</a>
  <a href="https://example.com/source">مصدر خارجي</a>
  <p>نص تجريبي طويل بما يكفي لعدّ الكلمات في الصفحة.</p>
</body>
</html>
"""


def test_normalize_host_strips_www_and_scheme() -> None:
    assert normalize_host("https://WWW.Forjo.tech/path") == "forjo.tech"
    assert normalize_host("not a url") == ""


def test_extract_seo_facts_reads_the_head() -> None:
    facts = extract_seo_facts(GOOD_PAGE, "https://www.forjo.tech/post.html", OWNED)
    assert facts.title.startswith("دليل شامل")
    assert facts.title_length > 20
    assert facts.meta_description_length > 50
    assert facts.canonical == "https://www.forjo.tech/2026/08/blog-post_294.html"
    assert facts.html_lang == "ar"
    assert facts.h1_texts == ("دليل شامل للربح من التدوين",)
    assert facts.h2_count == 2
    assert facts.image_count == 1
    assert facts.images_without_alt == 0
    assert facts.internal_links == 3
    assert facts.external_links == 1
    assert facts.has_open_graph is True
    assert facts.has_og_image is True
    assert facts.has_json_ld is True
    assert facts.json_ld_types == ("BlogPosting",)
    assert facts.word_count > 0


def test_extract_seo_facts_counts_missing_alt() -> None:
    html = (
        '<html lang="ar"><head><title>عنوان طويل بما يكفي للفحص</title></head>'
        '<body><img src="a.png"><img src="b.png" alt="وصف"></body></html>'
    )
    facts = extract_seo_facts(html, "https://www.forjo.tech/p.html", OWNED)
    assert facts.image_count == 2
    assert facts.images_without_alt == 1


def test_match_network_handles_subdomains() -> None:
    assert match_network("https://pl1.profitableratecpm.com/x.js", ("profitableratecpm.com",))
    assert match_network("https://www.adsterra.com/x.js", ("adsterra.com",))
    assert match_network("https://example.com/x.js", ("adsterra.com",)) == ""


def test_detect_static_ad_resources_finds_one_per_network() -> None:
    html = """
    <html><body>
      <script src="https://cdn.adsterra.com/a.js"></script>
      <script src="https://cdn.adsterra.com/b.js"></script>
      <iframe src="https://x.monetag.com/frame"></iframe>
    </body></html>
    """
    found = {observation.network for observation in detect_static_ad_resources(html, AD_DOMAINS)}
    assert found == {"adsterra.com", "monetag.com"}


def test_merge_observations_prefers_live_data() -> None:
    static = [AdObservation("adsterra.com", "script", "https://cdn.adsterra.com/a.js")]
    live = [
        AdObservation("adsterra.com", "iframe", "https://cdn.adsterra.com/ad.html", visible=True)
    ]
    merged = merge_observations(static, live)
    assert len(merged) == 1
    assert merged[0].visible is True


def _checks_for(html: str, *, snapshot: HttpSnapshot | None = None) -> dict[str, CheckStatus]:
    facts = extract_seo_facts(html, "https://www.forjo.tech/p.html", OWNED)
    default_snapshot = HttpSnapshot(
        final_url="https://www.forjo.tech/p.html",
        status_code=200,
        content_type="text/html",
        html_bytes=len(html),
        redirects=0,
    )
    checks = build_page_checks(
        snapshot=snapshot or default_snapshot,
        facts=facts,
        owned_hosts=OWNED,
        ads=detect_static_ad_resources(html, AD_DOMAINS),
        performance=PerformanceMetrics(),
        broken_links=0,
        browser_data_available=False,
    )
    return {check.check_id: check.status for check in checks}


def test_healthy_page_passes_metadata_checks() -> None:
    statuses = _checks_for(GOOD_PAGE)
    assert statuses[CheckId.TITLE_PRESENT] is CheckStatus.PASS
    assert statuses[CheckId.META_DESCRIPTION] is CheckStatus.PASS
    assert statuses[CheckId.HEADING_ONE] is CheckStatus.PASS
    assert statuses[CheckId.CANONICAL] is CheckStatus.PASS
    assert statuses[CheckId.LANG_ATTR] is CheckStatus.PASS
    assert statuses[CheckId.AD_SCRIPT_PRESENT] is CheckStatus.PASS


def test_missing_metadata_fails() -> None:
    statuses = _checks_for("<html><body><h1>فقط</h1></body></html>")
    assert statuses[CheckId.TITLE_PRESENT] is CheckStatus.FAIL
    assert statuses[CheckId.META_DESCRIPTION] is CheckStatus.FAIL
    assert statuses[CheckId.AD_SCRIPT_PRESENT] is CheckStatus.FAIL


def test_noindex_page_fails_robots_check() -> None:
    html = GOOD_PAGE.replace(
        '<link rel="canonical"',
        '<meta name="robots" content="noindex, follow"><link rel="canonical"',
    )
    statuses = _checks_for(html)
    assert statuses[CheckId.ROBOTS_META] is CheckStatus.FAIL


def test_browser_only_checks_are_skipped_in_http_mode() -> None:
    statuses = _checks_for(GOOD_PAGE)
    assert statuses[CheckId.AD_SLOT_VISIBLE] is CheckStatus.SKIP
    assert statuses[CheckId.LCP] is CheckStatus.SKIP
    assert statuses[CheckId.TTFB] is CheckStatus.SKIP


def test_slow_page_fails_performance_checks() -> None:
    facts = extract_seo_facts(GOOD_PAGE, "https://www.forjo.tech/p.html", OWNED)
    checks = build_page_checks(
        snapshot=HttpSnapshot("https://www.forjo.tech/p.html", 200, "text/html", 120_000, 0),
        facts=facts,
        owned_hosts=OWNED,
        ads=detect_static_ad_resources(GOOD_PAGE, AD_DOMAINS),
        performance=PerformanceMetrics(
            ttfb_ms=3_000.0, lcp_ms=9_000.0, cumulative_layout_shift=0.4, js_error_count=5
        ),
        broken_links=2,
        browser_data_available=True,
    )
    statuses = {check.check_id: check.status for check in checks}
    assert statuses[CheckId.TTFB] is CheckStatus.FAIL
    assert statuses[CheckId.LCP] is CheckStatus.FAIL
    assert statuses[CheckId.CLS] is CheckStatus.FAIL
    assert statuses[CheckId.JS_ERRORS] is CheckStatus.FAIL
    assert statuses[CheckId.BROKEN_LINKS] is CheckStatus.FAIL
    assert statuses[CheckId.AD_SLOT_VISIBLE] is CheckStatus.FAIL
