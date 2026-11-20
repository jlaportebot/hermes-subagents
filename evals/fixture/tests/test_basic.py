from textkit import slugify, parse_duration, word_count


def test_slugify_simple():
    assert slugify("Hello World") == "hello-world"


def test_parse_duration_simple():
    assert parse_duration("1h30m") == 5400


def test_word_count():
    assert word_count("one two three") == 3
