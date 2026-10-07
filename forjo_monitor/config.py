"""Environment-backed configuration for forjo-monitor.

Every value comes from the process environment, optionally seeded from a local
``.env`` file. Nothing is hard-coded, and no secret is ever logged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_SITE_URL = "https://www.forjo.tech"
DEFAULT_AD_NETWORK_DOMAINS = (
    "adsterra.com",
    "monetag.com",
    "highperformanceformat.com",
    "profitableratecpm.com",
)
DEFAULT_CRAWL_DELAY_SECONDS = 2.0
DEFAULT_CRAWL_MAX_PAGES = 300
DEFAULT_BROWSER_TIMEOUT_MS = 30_000
DEFAULT_ARTIFACTS_DIR = "artifacts"
DEFAULT_REPORTS_DIR = "reports"

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off", ""})


class ConfigError(ValueError):
    """Raised when the environment is missing something the run needs."""


def _read_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _read_bool(name: str, default: bool) -> bool:
    raw = _read_str(name)
    if not raw:
        return default
    lowered = raw.lower()
    if lowered in _TRUTHY:
        return True
    if lowered in _FALSY:
        return False
    raise ConfigError(f"{name} must be a boolean, got {raw!r}")


def _read_int(name: str, default: int) -> int:
    raw = _read_str(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def _read_float(name: str, default: float) -> float:
    raw = _read_str(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc


def _read_list(name: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    raw = _read_str(name)
    if not raw:
        return default
    return tuple(part.strip().lower() for part in raw.split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of the runtime configuration."""

    site_base_url: str = DEFAULT_SITE_URL
    site_extra_hosts: tuple[str, ...] = ()
    mongodb_uri: str = ""
    mongodb_database: str = "forjo_monitor"
    ad_network_domains: tuple[str, ...] = DEFAULT_AD_NETWORK_DOMAINS
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    crawl_concurrency: int = 2
    crawl_delay_seconds: float = DEFAULT_CRAWL_DELAY_SECONDS
    crawl_max_pages: int = DEFAULT_CRAWL_MAX_PAGES
    crawl_respect_robots: bool = True
    browser_audit_enabled: bool = True
    browser_headless: bool = True
    browser_timeout_ms: int = DEFAULT_BROWSER_TIMEOUT_MS
    artifacts_dir: Path = field(default_factory=lambda: Path(DEFAULT_ARTIFACTS_DIR))
    reports_dir: Path = field(default_factory=lambda: Path(DEFAULT_REPORTS_DIR))
    alert_on_regression: bool = True

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "Settings":
        """Build settings from the environment.

        ``env_file`` defaults to ``.env`` in the current directory when present.
        """
        if env_file is None:
            candidate = Path(".env")
            if candidate.is_file():
                load_dotenv(candidate)
        elif env_file.is_file():
            load_dotenv(env_file)

        return cls(
            site_base_url=_read_str("SITE_BASE_URL", DEFAULT_SITE_URL).rstrip("/"),
            site_extra_hosts=_read_list("SITE_EXTRA_HOSTS"),
            mongodb_uri=_read_str("MONGODB_URI"),
            mongodb_database=_read_str("MONGODB_DATABASE", "forjo_monitor"),
            ad_network_domains=_read_list("AD_NETWORK_DOMAINS", DEFAULT_AD_NETWORK_DOMAINS),
            telegram_bot_token=_read_str("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=_read_str("TELEGRAM_CHAT_ID"),
            crawl_concurrency=_read_int("CRAWL_CONCURRENCY", 2),
            crawl_delay_seconds=_read_float("CRAWL_DELAY_SECONDS", DEFAULT_CRAWL_DELAY_SECONDS),
            crawl_max_pages=_read_int("CRAWL_MAX_PAGES", DEFAULT_CRAWL_MAX_PAGES),
            crawl_respect_robots=_read_bool("CRAWL_RESPECT_ROBOTS", True),
            browser_audit_enabled=_read_bool("BROWSER_AUDIT_ENABLED", True),
            browser_headless=_read_bool("BROWSER_HEADLESS", True),
            browser_timeout_ms=_read_int("BROWSER_TIMEOUT_MS", DEFAULT_BROWSER_TIMEOUT_MS),
            artifacts_dir=Path(_read_str("ARTIFACTS_DIR", DEFAULT_ARTIFACTS_DIR)),
            reports_dir=Path(_read_str("REPORTS_DIR", DEFAULT_REPORTS_DIR)),
            alert_on_regression=_read_bool("ALERT_ON_REGRESSION", True),
        )

    @property
    def owned_hosts(self) -> frozenset[str]:
        """Every hostname that counts as ``the site under audit``."""
        hosts = {self.host_from_url(self.site_base_url)}
        hosts.update(self.site_extra_hosts)
        return frozenset(host for host in hosts if host)

    @property
    def has_storage(self) -> bool:
        return bool(self.mongodb_uri)

    @property
    def has_telegram(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @staticmethod
    def host_from_url(url: str) -> str:
        """Return the lower-cased hostname of ``url``, or ``''`` when absent."""
        without_scheme = url.split("://", 1)[-1]
        authority = without_scheme.split("/", 1)[0]
        host = authority.split("@")[-1].split(":", 1)[0]
        return host.lower().removeprefix("www.")

    def require_storage(self) -> str:
        """Return the Mongo URI or explain what is missing."""
        if not self.mongodb_uri:
            raise ConfigError(
                "MONGODB_URI is not set. Copy .env.example to .env and paste the "
                "SRV connection string from MongoDB Atlas (free M0 tier)."
            )
        return self.mongodb_uri
