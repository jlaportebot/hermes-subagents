"""URL slug generation."""
import re
import unicodedata

_NON_WORD = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Return a lowercase ASCII slug: words joined by single dashes, no leading/trailing dash."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = _NON_WORD.sub("-", ascii_text)
    return slug.strip("-")
