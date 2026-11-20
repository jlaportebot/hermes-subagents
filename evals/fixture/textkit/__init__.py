"""textkit: small text utilities used as an eval fixture."""
from .slug import slugify
from .duration import parse_duration
from .stats import word_count, top_words

__all__ = ["slugify", "parse_duration", "word_count", "top_words"]
