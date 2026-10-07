"""Extract the terms a blog actually talks about.

Used for content planning: the words a site repeats are the topics it competes
for, and gaps show up as topics it never covers.
"""

from __future__ import annotations

import re
from collections import Counter

_ARABIC_DIACRITICS = re.compile(r"[\u064B-\u0652\u0670\u0640]")
_TOKEN_RE = re.compile(r"[\w\u0600-\u06FF]{3,}", re.UNICODE)
_LATIN_ONLY = re.compile(r"^[a-z]+$")

STOPWORDS: frozenset[str] = frozenset(
    {
        # Arabic
        "من", "في", "على", "إلى", "الى", "عن", "مع", "هذا", "هذه", "ذلك", "التي",
        "الذي", "الذين", "كان", "كانت", "يكون", "كل", "بعد", "قبل", "بين", "حتى",
        "أو", "او", "ثم", "لكن", "قد", "لا", "ما", "هو", "هي", "هم", "نحن", "أنت",
        "يمكن", "يجب", "عند", "عندما", "إذا", "اذا", "كما", "كذلك", "أي", "اي",
        "هناك", "هنالك", "دون", "غير", "أكثر", "اكثر", "أقل", "اقل", "جدا", "جداً",
        "الله", "اليوم", "الآن", "الان", "أيضا", "أيضاً", "ايضا", "فقط", "لكي",
        # English
        "the", "and", "for", "with", "that", "this", "from", "your", "you", "are",
        "was", "were", "have", "has", "had", "not", "but", "can", "will", "would",
        "there", "their", "them", "then", "than", "into", "over", "about", "more",
        "most", "some", "such", "only", "also", "very", "just", "all", "any", "our",
        "out", "who", "what", "when", "where", "which", "how", "why", "its", "it",
    }
)


def normalize_token(token: str) -> str:
    """Strip Arabic diacritics and unify alef/ya forms so counts merge."""
    cleaned = _ARABIC_DIACRITICS.sub("", token)
    cleaned = cleaned.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    cleaned = cleaned.replace("ى", "ي").replace("ة", "ه")
    return cleaned.lower()


def tokenize(text: str) -> list[str]:
    """Split text into comparable tokens, discarding stopwords."""
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(text):
        if _LATIN_ONLY.match(raw) and raw.lower() in STOPWORDS:
            continue
        normalized = normalize_token(raw)
        if normalized in STOPWORDS or len(normalized) < 3:
            continue
        tokens.append(normalized)
    return tokens


def top_keywords(text: str, limit: int = 20) -> list[tuple[str, int]]:
    """Return the most frequent meaningful terms in ``text``."""
    counts = Counter(tokenize(text))
    return counts.most_common(limit)


def bigrams(tokens: list[str], limit: int = 15) -> list[tuple[str, int]]:
    """Return the most frequent two-word phrases, useful as topic candidates."""
    counts: Counter[str] = Counter(
        f"{tokens[index]} {tokens[index + 1]}" for index in range(len(tokens) - 1)
    )
    return counts.most_common(limit)
