Phase 2. Extend the function you just added (same files, same rules): give it a keyword-only parameter
`ellipsis: str = "..."` that replaces the fixed suffix everywhere the suffix was used (including the limit == 0 case),
e.g. `truncate_words("a b c", 2, ellipsis=" [more]") == "a b [more]"`. Add tests for it in the same test file, run the
full suite (`python3 -m pytest -q --deselect tests/test_basic.py::test_slugify_simple`; that one test is a known, separate bug — leave it), commit, and report in the usual format.
