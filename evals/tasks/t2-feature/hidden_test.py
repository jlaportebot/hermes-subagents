import pytest
from textkit import parse_duration

@pytest.mark.parametrize("text,expected", [("1h30m", 5400), ("1h 30m 10s", 5410), ("  45m ", 2700), ("90", 90),
    ("2d", 172800), ("1H30M", 5400), ("1d2h3m4s", 93784), ("0s", 0), ("10s", 10), ("1d 1s", 86401)])
def test_ok(text, expected):
    assert parse_duration(text) == expected
    assert isinstance(parse_duration(text), int)

@pytest.mark.parametrize("text", ["", "   ", "abc", "5x", "1h30", "h", "-5m", "1.5h", "30m1h", "1h1h", "1 h", "s1"])
def test_bad(text):
    with pytest.raises(ValueError) as err:
        parse_duration(text)
    assert repr(text) in str(err.value) or text.strip() in str(err.value)
