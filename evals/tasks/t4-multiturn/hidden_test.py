import pytest
from textkit import truncate_words

def test_phase1():
    assert truncate_words("a b c", 2) == "a b..."
    assert truncate_words(" a  b ", 5) == "a b"
    assert truncate_words("a b", 2) == "a b"
    assert truncate_words("x", 0) == "..."
    assert truncate_words("", 0) == ""
    with pytest.raises(ValueError):
        truncate_words("a", -1)

def test_phase2():
    assert truncate_words("a b c", 2, ellipsis=" [more]") == "a b [more]"
    assert truncate_words("a b c", 0, ellipsis="~") == "~"
    assert truncate_words("a b", 3, ellipsis="~") == "a b"
    with pytest.raises(TypeError):
        truncate_words("a b c", 2, "~")
