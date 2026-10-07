"""Turn raw observations into graded checks.

Thresholds are deliberately boring and documented: a check only fails when the
problem demonstrably costs traffic or ad revenue.
"""

from __future__ import annotations

from forjo_monitor.analyzers.html_facts import normalize_host
from forjo_monitor.checks import Check, CheckId, CheckStatus, Severity
from forjo_monitor.models import HttpSnapshot, SeoFacts

TITLE_MIN = 15
TITLE_MAX = 65
TITLE_HARD_MAX = 80
META_DESCRIPTION_MIN = 50
META_DESCRIPTION_MAX = 160
MIN_INTERNAL_LINKS = 3
MAX_MISSING_ALT_RATIO = 0.2
MIN_ARTICLE_WORDS = 300


def _check(
    check_id: str,
    label: str,
    ok: bool,
    severity: Severity,
    detail: str = "",
    *,
    warn: bool = False,
) -> Check:
    """Build a pass/warn/fail check from a boolean."""
    if ok:
        return Check(check_id, label, CheckStatus.PASS, severity, detail)
    status = CheckStatus.WARN if warn else CheckStatus.FAIL
    return Check(check_id, label, status, severity, detail)


def http_checks(snapshot: HttpSnapshot) -> list[Check]:
    """Verify the page loads, over HTTPS, without a redirect chain."""
    checks = [
        _check(
            CheckId.HTTP_OK,
            "الصفحة تُرجع 200",
            snapshot.is_ok,
            Severity.CRITICAL,
            f"HTTP {snapshot.status_code}",
        ),
        _check(
            CheckId.HTTPS,
            "الرابط يستخدم HTTPS",
            snapshot.final_url.startswith("https://"),
            Severity.MAJOR,
            snapshot.final_url,
        ),
    ]
    if snapshot.redirects:
        checks.append(
            _check(
                "http.redirect_chain",
                "عدد التحويلات صفر أو واحد",
                snapshot.redirects <= 1,
                Severity.MINOR,
                f"{snapshot.redirects} redirect(s)",
                warn=True,
            )
        )
    return checks


def canonical_check(facts: SeoFacts, owned_hosts: frozenset[str]) -> Check:
    """Canonical must exist and must point back at the audited site."""
    if not facts.canonical:
        return Check(
            CheckId.CANONICAL,
            "وسم canonical يشير إلى نفس الموقع",
            CheckStatus.WARN,
            Severity.MAJOR,
            "مفقود",
        )
    same_site = normalize_host(facts.canonical) in owned_hosts
    return _check(
        CheckId.CANONICAL,
        "وسم canonical يشير إلى نفس الموقع",
        same_site,
        Severity.MAJOR,
        facts.canonical,
        warn=not same_site,
    )


def title_checks(facts: SeoFacts) -> list[Check]:
    """Title presence and length."""
    if not facts.title:
        return [
            Check(
                CheckId.TITLE_PRESENT,
                "عنوان الصفحة موجود",
                CheckStatus.FAIL,
                Severity.CRITICAL,
                "لا يوجد <title>",
            )
        ]

    length = facts.title_length
    if length < TITLE_MIN:
        status = CheckStatus.WARN
        detail = f"{length} حرفاً — أقصر من {TITLE_MIN}"
    elif length > TITLE_HARD_MAX:
        status = CheckStatus.FAIL
        detail = f"{length} حرفاً — أطول من {TITLE_HARD_MAX}"
    elif length > TITLE_MAX:
        status = CheckStatus.WARN
        detail = f"{length} حرفاً — سيُقتطع في نتائج البحث"
    else:
        status = CheckStatus.PASS
        detail = f"{length} حرفاً"

    return [
        Check(
            CheckId.TITLE_PRESENT,
            "عنوان الصفحة موجود",
            CheckStatus.PASS,
            Severity.CRITICAL,
            detail,
        ),
        Check(CheckId.TITLE_LENGTH, "طول العنوان مناسب", status, Severity.MAJOR, detail),
    ]


def _description_check(facts: SeoFacts) -> Check:
    length = facts.meta_description_length
    if length == 0:
        return Check(
            CheckId.META_DESCRIPTION,
            "الوصف التعريفي (meta description) موجود",
            CheckStatus.FAIL,
            Severity.MAJOR,
            "مفقود",
        )
    if META_DESCRIPTION_MIN <= length <= META_DESCRIPTION_MAX:
        return Check(
            CheckId.META_DESCRIPTION,
            "طول الوصف التعريفي مناسب",
            CheckStatus.PASS,
            Severity.MAJOR,
            f"{length} حرفاً",
        )
    return Check(
        CheckId.META_DESCRIPTION,
        "طول الوصف التعريفي مناسب",
        CheckStatus.WARN,
        Severity.MAJOR,
        f"{length} حرفاً (المستحسن {META_DESCRIPTION_MIN}-{META_DESCRIPTION_MAX})",
    )


def _heading_check(facts: SeoFacts) -> Check:
    h1_count = len(facts.h1_texts)
    if h1_count == 1:
        status = CheckStatus.PASS
    elif h1_count == 0:
        status = CheckStatus.FAIL
    else:
        status = CheckStatus.WARN
    return Check(CheckId.HEADING_ONE, "عنوان H1 واحد فقط", status, Severity.MAJOR, f"{h1_count} × H1")


def seo_checks(facts: SeoFacts, owned_hosts: frozenset[str]) -> list[Check]:
    """Metadata checks that drive click-through and indexing."""
    blocked = "noindex" in facts.robots_meta.lower()

    checks = [
        *title_checks(facts),
        _description_check(facts),
        _check(
            CheckId.ROBOTS_META,
            "الصفحة قابلة للفهرسة (ليست noindex)",
            not blocked,
            Severity.CRITICAL,
            facts.robots_meta or "لا يوجد وسم robots",
        ),
        _heading_check(facts),
        canonical_check(facts, owned_hosts),
        _check(
            CheckId.OPEN_GRAPH,
            "وسوم Open Graph موجودة",
            facts.has_open_graph,
            Severity.MINOR,
            "تُستخدم عند مشاركة الرابط",
            warn=True,
        ),
        _check(
            CheckId.STRUCTURED_DATA,
            "بيانات منظمة (JSON-LD) موجودة",
            facts.has_json_ld,
            Severity.MAJOR,
            ", ".join(facts.json_ld_types) or "مفقودة",
            warn=True,
        ),
        _check(
            CheckId.LANG_ATTR,
            "خاصية lang على <html>",
            bool(facts.html_lang),
            Severity.MINOR,
            facts.html_lang or "مفقودة",
            warn=True,
        ),
    ]
    return checks


def accessibility_checks(facts: SeoFacts) -> list[Check]:
    """Images must carry alt text; missing alt also loses image-search traffic."""
    if facts.image_count == 0:
        return [
            Check(
                CheckId.IMAGE_ALT,
                "كل الصور تحتوي alt",
                CheckStatus.PASS,
                Severity.MINOR,
                "لا توجد صور",
            )
        ]

    ratio = facts.images_without_alt / facts.image_count
    if ratio == 0:
        status = CheckStatus.PASS
    elif ratio <= MAX_MISSING_ALT_RATIO:
        status = CheckStatus.WARN
    else:
        status = CheckStatus.FAIL

    return [
        Check(
            CheckId.IMAGE_ALT,
            "كل الصور تحتوي alt",
            status,
            Severity.MAJOR,
            f"{facts.images_without_alt}/{facts.image_count} صورة بلا alt",
        )
    ]


def link_checks(facts: SeoFacts, broken_count: int) -> list[Check]:
    """Internal-link depth and dead links."""
    broken = Check(
        CheckId.BROKEN_LINKS,
        "لا توجد روابط مكسورة",
        CheckStatus.PASS if broken_count == 0 else CheckStatus.FAIL,
        Severity.MAJOR,
        "0" if broken_count == 0 else f"{broken_count} رابط لا يعمل",
    )
    internal = Check(
        CheckId.INTERNAL_LINKS,
        "روابط داخلية كافية",
        CheckStatus.PASS if facts.internal_links >= MIN_INTERNAL_LINKS else CheckStatus.WARN,
        Severity.MAJOR if facts.internal_links >= MIN_INTERNAL_LINKS else Severity.MINOR,
        f"{facts.internal_links} رابط (المستحسن {MIN_INTERNAL_LINKS}+) — يزيد عمق الزحف",
    )
    return [internal, broken]
