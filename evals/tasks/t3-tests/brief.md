# T3: write a thorough test suite for textkit/stats.py

## Goal
`textkit/stats.py` has no dedicated tests. Write `tests/test_stats.py` that pins down its behaviour precisely,
so that any behavioural change to `word_count` or `top_words` makes at least one test fail.

## Context you need
- `textkit/stats.py` (whole file):
  ```python
  _WORD = re.compile(r"[A-Za-z']+")

  def word_count(text: str) -> int:
      """Number of words in text."""
      return len(_WORD.findall(text))

  def top_words(text: str, n: int = 3) -> list[tuple[str, int]]:
      """The n most common words (case-insensitive) with counts, most common first, ties alphabetical."""
      counts = Counter(w.lower() for w in _WORD.findall(text))
      return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
  ```
- Behaviours worth pinning: empty text, punctuation/digits not words, apostrophes inside words ("don't" is one
  word), case-insensitivity of top_words, tie ordering (alphabetical), the default n=3, n larger than the number
  of distinct words, n=0, counts are correct, return types.

## Constraints
- Do NOT modify `textkit/` at all. Only create `tests/test_stats.py`.

## Acceptance
- `python3 -m pytest -q tests/test_stats.py` -> exit 0, at least 12 tests.
- `python3 -m coverage run --include='textkit/stats.py' -m pytest -q tests/test_stats.py && python3 -m coverage report --fail-under=100` -> exit 0.
