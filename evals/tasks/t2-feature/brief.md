# T2: make parse_duration strict and more flexible

## Goal
`textkit.parse_duration` silently returns 0 for garbage and cannot parse common forms. Make it accept more
formats and reject invalid input with `ValueError`.

## Context you need
- Repo: stdlib-only Python package `textkit/`, pytest tests in `tests/`, rules in `AGENTS.md`
  (errors: `ValueError` whose message names the bad input).
- `textkit/duration.py` today:
  ```python
  _UNIT_SECONDS = {"h": 3600, "m": 60, "s": 1}
  _PART = re.compile(r"(\d+)([hms])")

  def parse_duration(text: str) -> int:
      total = 0
      for amount, unit in _PART.findall(text):
          total += int(amount) * _UNIT_SECONDS[unit]
      return total
  ```

## Required behaviour (all of it)
| input | result |
|---|---|
| `"1h30m"` | 5400 |
| `"1h 30m 10s"` (spaces between parts allowed) | 5410 |
| `"  45m "` (surrounding whitespace ignored) | 2700 |
| `"90"` (bare integer = seconds) | 90 |
| `"2d"` (new unit d = 86400) | 172800 |
| `"1H30M"` (units case-insensitive) | 5400 |
| `"1d2h3m4s"` | 93784 |
| `""`, `"   "`, `"abc"`, `"5x"`, `"1h30"`, `"h"`, `"-5m"`, `"1.5h"`, `"30m1h"` (units out of order) | raise `ValueError` mentioning the input |
| each unit at most once: `"1h1h"` | raise `ValueError` |
Units must appear in descending order d, h, m, s. Return type stays `int`.

## What to do
1. Write `tests/test_duration.py` covering every row above (parametrize). Run it; see failures.
2. Re-implement `parse_duration` (a single full-match regex like
   `^(?:(\d+)d)?\s*(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:(\d+)s)?$` on the stripped, lowercased text works well, plus the
   bare-integer case and an "at least one part" check). Keep functions small; no magic numbers (named constants).
3. Run the full suite (`python3 -m pytest -q --deselect tests/test_basic.py::test_slugify_simple`; that one test is a known, separate bug — leave it).

## Constraints
- Edit only `textkit/duration.py` and `tests/test_duration.py`.

## Acceptance
- `python3 -m pytest -q tests/test_duration.py tests/test_basic.py::test_parse_duration_simple` -> exit 0.
