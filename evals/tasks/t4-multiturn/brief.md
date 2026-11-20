# T4 (phase 1): add truncate_words

## Goal
Add `truncate_words(text: str, limit: int) -> str` to `textkit/stats.py` and export it from `textkit/__init__.py`.

## Behaviour
- Splits on whitespace (`text.split()`), keeps the first `limit` words joined by single spaces.
- If the text has more than `limit` words, append `"..."` directly after the last kept word: `truncate_words("a b c", 2) == "a b..."`.
- If it has `limit` words or fewer, return them joined by single spaces with no suffix: `truncate_words(" a  b ", 5) == "a b"`.
- `limit` < 0 raises `ValueError` naming the bad limit. `limit == 0` returns `"..."` for non-empty text and `""` for empty text.

## What to do
Tests first in `tests/test_truncate.py`, then implement, then run the full suite (`python3 -m pytest -q --deselect tests/test_basic.py::test_slugify_simple`; that one test is a known, separate bug — leave it).

## Constraints
Edit only `textkit/stats.py`, `textkit/__init__.py`, `tests/test_truncate.py`.

## Acceptance
- `python3 -m pytest -q tests/test_truncate.py` -> exit 0.
