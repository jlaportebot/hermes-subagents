"""Word statistics."""
import re
from collections import Counter

_WORD = re.compile(r"[A-Za-z']+")


def word_count(text: str) -> int:
    """Number of words in text."""
    return len(_WORD.findall(text))


def top_words(text: str, n: int = 3) -> list[tuple[str, int]]:
    """The n most common words (case-insensitive) with counts, most common first, ties alphabetical."""
    counts = Counter(w.lower() for w in _WORD.findall(text))
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
