# T1: fix slugify not lowercasing

## Goal
`textkit.slugify` must return lowercase slugs. Today `slugify("Hello World")` returns `"ello-orld"` because the
regex `[^a-z0-9]+` is applied before lowercasing, so capital letters are treated as separators and dropped.

## Context you need
- Repo: tiny stdlib-only Python package `textkit/` with pytest tests in `tests/`. Rules in `AGENTS.md`.
- `textkit/slug.py` (whole file, 13 lines):
  ```python
  _NON_WORD = re.compile(r"[^a-z0-9]+")

  def slugify(text: str) -> str:
      """Return a lowercase ASCII slug: words joined by single dashes, no leading/trailing dash."""
      ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
      slug = _NON_WORD.sub("-", ascii_text)
      return slug.strip("-")
  ```
- Failing test today: `tests/test_basic.py::test_slugify_simple`.

## What to do
1. Add regression tests in a new file `tests/test_slug.py`: mixed case (`"Hello World"` -> `"hello-world"`),
   accents (`"Crème Brûlée"` -> `"creme-brulee"`), punctuation runs (`"  Hi -- there!! "` -> `"hi-there"`),
   empty string -> `""`. Run them and see the case test fail first.
2. Fix `slugify` (lowercase the ASCII text before applying the regex).
3. Run the full suite.

## Constraints
- Edit only `textkit/slug.py` and `tests/test_slug.py`.

## Acceptance
- `python3 -m pytest -q` -> exit 0, all tests pass.
