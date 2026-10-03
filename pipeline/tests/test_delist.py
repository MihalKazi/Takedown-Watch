from tw.events import DEINDEXED, UNPUBLISHED, diff_listing_presence


def test_no_prior_listing_is_silent() -> None:
    assert diff_listing_presence(set(), set(), {"a"}, set(), {"a"}) is None


def test_deindexed_when_absent_from_everything() -> None:
    draft = diff_listing_presence({"a"}, set(), set(), set(), {"a"})
    assert draft is not None and draft.type == DEINDEXED and draft.confidence == "unverified"


def test_unpublished_when_dropped_from_sitemap_but_still_in_rss() -> None:
    draft = diff_listing_presence(set(), {"a"}, {"a"}, set(), {"a"})
    assert draft is not None and draft.type == UNPUBLISHED


def test_still_present_is_silent() -> None:
    assert diff_listing_presence({"a"}, set(), {"a"}, set(), {"a"}) is None


def test_already_absent_last_run_is_silent() -> None:
    """The transition already happened on a prior run; don't re-fire every subsequent run."""
    assert diff_listing_presence(set(), set(), set(), set(), {"a"}) is None


def test_matches_via_any_alias_hash() -> None:
    draft = diff_listing_presence({"old-alias"}, set(), set(), set(), {"old-alias", "canonical"})
    assert draft is not None and draft.type == DEINDEXED
