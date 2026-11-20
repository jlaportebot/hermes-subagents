from textkit import slugify

def test_hidden_cases():
    assert slugify("Hello World") == "hello-world"
    assert slugify("ÀÉÎ õü") == "aei-ou"
    assert slugify("--A--B--") == "a-b"
    assert slugify("") == ""
    assert slugify("Ünïcödé 2026!") == "unicode-2026"
