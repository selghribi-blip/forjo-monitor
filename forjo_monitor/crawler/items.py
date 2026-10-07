"""Structured record for one crawled page."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ContentItem:
    """What the content inventory records about one page."""

    url: str
    status: int
    title: str = ""
    h1: str = ""
    word_count: int = 0
    h2_count: int = 0
    image_count: int = 0
    images_without_alt: int = 0
    internal_links: int = 0
    external_links: int = 0
    lang: str = ""
    published: str = ""
    top_keywords: list[tuple[str, int]] = field(default_factory=list)
    top_bigrams: list[tuple[str, int]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
