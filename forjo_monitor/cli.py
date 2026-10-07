"""Command-line entry point."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from forjo_monitor.audit import AuditOptions, AuditRunner
from forjo_monitor.config import ConfigError, Settings
from forjo_monitor.reporting import MARKDOWN_FILE_NAME

LOGGER = logging.getLogger("forjo_monitor")

EXIT_OK = 0
EXIT_FAILURES_FOUND = 1
EXIT_ERROR = 2


def configure_logging(verbose: bool) -> None:
    """Human-readable logging on stderr, so stdout stays machine-friendly."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forjo-monitor",
        description="Self-audit a site you own: SEO, ad delivery and Core Web Vitals.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit", help="run a full site audit")
    audit.add_argument("--limit", type=int, default=0, help="audit only the first N pages")
    audit.add_argument(
        "--http-only", action="store_true", help="skip the headless browser (fast mode)"
    )
    audit.add_argument("--no-links", action="store_true", help="skip outbound link probing")
    audit.add_argument("--no-notify", action="store_true", help="skip the Telegram summary")
    audit.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="exit with code 1 when any check failed (useful in CI)",
    )

    inventory = subparsers.add_parser("inventory", help="crawl content and extract topics")
    inventory.add_argument("--limit", type=int, default=0, help="crawl only the first N pages")

    subparsers.add_parser("show", help="print the path of the latest report")
    return parser


def run_audit(args: argparse.Namespace, settings: Settings) -> int:
    options = AuditOptions(
        limit=args.limit,
        use_browser=not args.http_only,
        check_links=not args.no_links,
        notify=not args.no_notify,
    )
    result = AuditRunner(settings).run(options)
    totals = result.run.total_counts

    print(f"pages audited : {result.run.page_count}")
    print(f"pass/warn/fail: {totals['pass']}/{totals['warn']}/{totals['fail']}")
    print(f"report        : {result.reports.markdown}")
    print(f"json          : {result.reports.json}")
    print(f"stored in Atlas: {'yes' if result.stored else 'no (MONGODB_URI not set)'}")

    if args.fail_on_findings and totals["fail"] > 0:
        return EXIT_FAILURES_FOUND
    return EXIT_OK


def run_inventory(args: argparse.Namespace, settings: Settings) -> int:
    from forjo_monitor.crawler.runner import run_inventory as execute_inventory

    result = execute_inventory(settings, max_pages=args.limit)
    print(f"pages crawled : {result.item_count}")
    print(f"inventory file: {result.output_path}")
    print(f"stored in Atlas: {'yes' if result.stored else 'no (MONGODB_URI not set)'}")
    return EXIT_OK


def run_show(settings: Settings) -> int:
    report = settings.reports_dir / MARKDOWN_FILE_NAME
    if not report.is_file():
        print(f"no report yet at {report}", file=sys.stderr)
        return EXIT_ERROR
    print(Path(report).resolve())
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the requested command."""
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.verbose)

    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        LOGGER.error("Configuration error: %s", exc)
        return EXIT_ERROR

    if args.command == "audit":
        return run_audit(args, settings)
    if args.command == "inventory":
        return run_inventory(args, settings)
    return run_show(settings)
