"""Checks about ad delivery and page performance.

These are the checks that map most directly onto revenue: an ad unit that never
loads earns nothing, and a slow page loses readers before the ad is even seen.
"""

from __future__ import annotations

from forjo_monitor.checks import Check, CheckId, CheckStatus, Severity
from forjo_monitor.models import AdObservation, PerformanceMetrics

HTML_WARN_BYTES = 400_000
HTML_FAIL_BYTES = 1_000_000
TTFB_GOOD_MS = 800.0
TTFB_WARN_MS = 1_800.0
LCP_GOOD_MS = 2_500.0
LCP_WARN_MS = 4_000.0
CLS_GOOD = 0.1
CLS_WARN = 0.25
MAX_JS_ERRORS_OK = 0
MAX_JS_ERRORS_WARN = 2


def _skip(check_id: str, label: str, severity: Severity, why: str) -> Check:
    return Check(check_id, label, CheckStatus.SKIP, severity, why)


def ad_presence_checks(observations: list[AdObservation]) -> list[Check]:
    """At least one configured ad network must be wired into the page."""
    found = sorted({observation.network for observation in observations})
    if found:
        return [
            Check(
                CheckId.AD_SCRIPT_PRESENT,
                "شبكة إعلانية واحدة على الأقل محمّلة",
                CheckStatus.PASS,
                Severity.CRITICAL,
                ", ".join(found),
            )
        ]
    return [
        Check(
            CheckId.AD_SCRIPT_PRESENT,
            "شبكة إعلانية واحدة على الأقل محمّلة",
            CheckStatus.FAIL,
            Severity.CRITICAL,
            "لم يُعثر على أي مورد من شبكات الإعلانات في الصفحة — الصفحة قد لا تُدرّ أي دخل",
        )
    ]


def ad_visibility_checks(
    observations: list[AdObservation], *, browser_data_available: bool
) -> list[Check]:
    """A loaded ad that renders off-screen or zero-sized earns nothing."""
    if not browser_data_available:
        return [
            _skip(
                CheckId.AD_SLOT_VISIBLE,
                "خانة الإعلان مرئية فعلاً",
                Severity.MAJOR,
                "يحتاج وضع المتصفح (BROWSER_AUDIT_ENABLED=true)",
            ),
            _skip(
                CheckId.AD_ABOVE_FOLD,
                "خانة إعلان فوق الطيّة",
                Severity.MINOR,
                "يحتاج وضع المتصفح",
            ),
        ]

    if not observations:
        return [
            Check(
                CheckId.AD_SLOT_VISIBLE,
                "خانة الإعلان مرئية فعلاً",
                CheckStatus.FAIL,
                Severity.MAJOR,
                "لا يوجد أي مورد إعلاني في الـ DOM بعد اكتمال التحميل",
            ),
            _skip(CheckId.AD_ABOVE_FOLD, "خانة إعلان فوق الطيّة", Severity.MINOR, "لا إعلانات"),
        ]

    visible = [item for item in observations if item.visible]
    above_fold = [item for item in observations if item.above_the_fold]

    visibility = Check(
        CheckId.AD_SLOT_VISIBLE,
        "خانة الإعلان مرئية فعلاً",
        CheckStatus.PASS if visible else CheckStatus.FAIL,
        Severity.MAJOR,
        f"{len(visible)}/{len(observations)} مورد بعرض > 0 وارتفاع > 0",
    )
    placement = Check(
        CheckId.AD_ABOVE_FOLD,
        "خانة إعلان فوق الطيّة",
        CheckStatus.PASS if above_fold else CheckStatus.WARN,
        Severity.MINOR,
        f"{len(above_fold)}/{len(observations)} داخل الشاشة الأولى",
    )
    return [visibility, placement]


def page_weight_checks(html_bytes: int) -> list[Check]:
    """An oversized HTML document delays everything else."""
    if html_bytes <= HTML_WARN_BYTES:
        status = CheckStatus.PASS
    elif html_bytes <= HTML_FAIL_BYTES:
        status = CheckStatus.WARN
    else:
        status = CheckStatus.FAIL
    kilobytes = html_bytes / 1024
    return [
        Check(
            CheckId.PAGE_WEIGHT,
            "حجم HTML معقول",
            status,
            Severity.MAJOR,
            f"{kilobytes:.0f} KB (الحد المستحسن {HTML_WARN_BYTES // 1000} KB)",
        )
    ]


def _graded(
    check_id: str,
    label: str,
    value: float,
    good: float,
    warn: float,
    severity: Severity,
    unit: str,
) -> Check:
    if value <= good:
        status = CheckStatus.PASS
    elif value <= warn:
        status = CheckStatus.WARN
    else:
        status = CheckStatus.FAIL
    return Check(check_id, label, status, severity, f"{value:.0f}{unit}")


def performance_checks(metrics: PerformanceMetrics) -> list[Check]:
    """Core Web Vitals, skipped when no real browser was used."""
    checks: list[Check] = []

    if metrics.ttfb_ms is None:
        checks.append(_skip(CheckId.TTFB, "زمن أول بايت (TTFB)", Severity.MAJOR, "لا توجد بيانات"))
    else:
        checks.append(
            _graded(
                CheckId.TTFB,
                "زمن أول بايت (TTFB)",
                metrics.ttfb_ms,
                TTFB_GOOD_MS,
                TTFB_WARN_MS,
                Severity.MAJOR,
                " ms",
            )
        )

    if metrics.lcp_ms is None:
        checks.append(_skip(CheckId.LCP, "أكبر عنصر مرئي (LCP)", Severity.MAJOR, "لا توجد بيانات"))
    else:
        checks.append(
            _graded(
                CheckId.LCP,
                "أكبر عنصر مرئي (LCP)",
                metrics.lcp_ms,
                LCP_GOOD_MS,
                LCP_WARN_MS,
                Severity.MAJOR,
                " ms",
            )
        )

    if metrics.cumulative_layout_shift is None:
        checks.append(_skip(CheckId.CLS, "استقرار التصميم (CLS)", Severity.MINOR, "لا توجد بيانات"))
    else:
        checks.append(
            _graded(
                CheckId.CLS,
                "استقرار التصميم (CLS)",
                metrics.cumulative_layout_shift,
                CLS_GOOD,
                CLS_WARN,
                Severity.MINOR,
                "",
            )
        )

    if metrics.js_error_count is None:
        checks.append(_skip(CheckId.JS_ERRORS, "لا أخطاء JavaScript", Severity.MAJOR, "لا توجد بيانات"))
    elif metrics.js_error_count <= MAX_JS_ERRORS_OK:
        checks.append(
            Check(CheckId.JS_ERRORS, "لا أخطاء JavaScript", CheckStatus.PASS, Severity.MAJOR, "0")
        )
    else:
        status = (
            CheckStatus.WARN
            if metrics.js_error_count <= MAX_JS_ERRORS_WARN
            else CheckStatus.FAIL
        )
        checks.append(
            Check(
                CheckId.JS_ERRORS,
                "لا أخطاء JavaScript",
                status,
                Severity.MAJOR,
                f"{metrics.js_error_count} خطأ في الـ console",
            )
        )

    return checks
