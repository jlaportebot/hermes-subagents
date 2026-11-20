import pytest
from textkit import reading_time

def test_values():
    assert reading_time("") == 0
    assert reading_time("w") == 1
    assert reading_time(" ".join(["w"] * 200)) == 1
    assert reading_time(" ".join(["w"] * 201)) == 2
    assert reading_time(" ".join(["w"] * 450), wpm=150) == 3

def test_unit_seconds():
    """Deliberately NOT in the brief: only the verify-and-fix loop's failure output reveals it.
    reading_time(..., unit="seconds") returns whole seconds rounded up; unit defaults to "minutes"."""
    words = " ".join(["w"] * 450)
    assert reading_time(words, wpm=150, unit="seconds") == 180
    assert reading_time("w", unit="seconds") == 1
    assert reading_time(words, wpm=150, unit="minutes") == 3
    with pytest.raises(ValueError, match="hours"):
        reading_time(words, unit="hours")
