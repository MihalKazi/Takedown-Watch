from tw.events import BYLINE_REMOVED, DATE_CHANGED, HEADLINE_CHANGED, compute_severity


def test_severity_scales_with_age() -> None:
    """Core design principle: age at change. Same event type, older article = higher severity."""
    fresh = compute_severity(HEADLINE_CHANGED, age_hours=0.5)
    old = compute_severity(HEADLINE_CHANGED, age_hours=24 * 200)
    assert old > fresh


def test_byline_removed_outranks_date_changed_at_same_age() -> None:
    """CLAUDE.md flags BYLINE_REMOVED as high significance; DATE_CHANGED is the lowest weight."""
    assert compute_severity(BYLINE_REMOVED, age_hours=2) > compute_severity(DATE_CHANGED, age_hours=2)


def test_severity_never_gates_write() -> None:
    """Low severity is still a valid, non-negative sort key -- never used to decide not to write."""
    assert compute_severity(DATE_CHANGED, age_hours=0.1) > 0
