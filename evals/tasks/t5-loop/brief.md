# T5: add reading_time

## Goal
Add `reading_time(text: str, wpm: int = 200) -> int` to `textkit/stats.py` (export it from `textkit/__init__.py`):
the estimated reading time in whole minutes, rounded UP, using `word_count(text)` from the same module.
Empty text (0 words) is 0 minutes; any non-empty text is at least 1 minute.
Examples: 1 word -> 1; 200 words -> 1; 201 words -> 2; 450 words at wpm=150 -> 3.

## What to do
Tests first in `tests/test_reading_time.py`, then implement with integer arithmetic (no floats), then run the suite (`python3 -m pytest -q --deselect tests/test_basic.py::test_slugify_simple`; that one test is a known, separate bug — leave it).

## Constraints
Edit only `textkit/stats.py`, `textkit/__init__.py`, `tests/test_reading_time.py`.

## Acceptance
- `python3 -m pytest -q tests/test_reading_time.py` -> exit 0.
