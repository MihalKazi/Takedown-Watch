from tw.export_internal import _body_diff_snippet


def test_identical_bodies_have_no_diff() -> None:
    assert _body_diff_snippet("same text here", "same text here") is None


def test_diff_shows_only_changed_region_with_context() -> None:
    before = "The quick brown fox jumps over the lazy dog every single morning without fail."
    after = "The quick brown fox leaps over the lazy dog every single morning without fail."
    snippet = _body_diff_snippet(before, after, context=10)
    assert snippet is not None
    assert "jumps" in snippet
    assert "leaps" in snippet
    assert snippet.startswith("- ")
    assert "\n+ " in snippet
    # most of the 80-char sentence should NOT be in a short-context snippet
    assert len(snippet) < len(before) + len(after)


def test_none_before_treated_as_empty() -> None:
    snippet = _body_diff_snippet(None, "new content", context=5)
    assert snippet is not None and "new content" in snippet


def test_both_none_has_no_diff() -> None:
    assert _body_diff_snippet(None, None) is None
