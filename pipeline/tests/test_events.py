from datetime import timedelta

from tw.db.models import Article, Event, FetchAttempt, Outlet, Snapshot
from tw.db.session import session_scope
from tw.db.types import utcnow
from tw.events import (
    BODY_CHANGED,
    BYLINE_CHANGED,
    BYLINE_REMOVED,
    DATE_CHANGED,
    GONE_404,
    HEADLINE_CHANGED,
    REDIRECTED,
    RESTORED,
    ROBOTS_BLOCKED,
    EventDraft,
    check_gone,
    diff_snapshots,
    restored_event,
    write_event,
)

URL = "https://www.example-news.com/a"


def _seed_article(s, now=None):
    now = now or utcnow()
    o = Outlet(slug="ex", name="Ex", language="bn", base_url="https://www.example-news.com", tier="bangla_mass")
    s.add(o)
    s.flush()
    a = Article(outlet_id=o.id, canonical_url=URL, url_hash="0" * 64, first_seen=now, last_seen=now)
    s.add(a)
    s.flush()
    return o, a


def _snap(s, article, now, **overrides):
    fa = FetchAttempt(outlet_id=article.outlet_id, article_id=article.id, kind="article", url=URL,
                      vantage="t", started_at=now, outcome="ok", http_status=200)
    s.add(fa)
    s.flush()
    defaults = dict(
        article_id=article.id, fetch_attempt_id=fa.id, fetched_at=now, http_status=200, vantage="t",
        final_url=URL, headline="Headline", byline="Reporter", body_text="body", body_length=4,
        body_hash="b1", headline_hash="h1", byline_hash="y1", extractor_version="x", normaliser_version="1",
    )
    defaults.update(overrides)
    snap = Snapshot(**defaults)
    s.add(snap)
    s.flush()
    return snap


def test_diff_detects_headline_and_body_change(engine) -> None:
    with session_scope(engine) as s:
        _, art = _seed_article(s)
        now = utcnow()
        prev = _snap(s, art, now)
        new = _snap(s, art, now + timedelta(hours=1), headline_hash="h2", body_hash="b2")
        drafts = {d.type for d in diff_snapshots(prev, new)}
        assert drafts == {HEADLINE_CHANGED, BODY_CHANGED}


def test_diff_detects_byline_removed_vs_changed(engine) -> None:
    with session_scope(engine) as s:
        _, art = _seed_article(s)
        now = utcnow()
        prev = _snap(s, art, now, byline="Reporter A")
        removed = _snap(s, art, now + timedelta(hours=1), byline=None, byline_hash="")
        assert [d.type for d in diff_snapshots(prev, removed)] == [BYLINE_REMOVED]

        prev2 = _snap(s, art, now, byline="Reporter A", byline_hash="y1")
        changed = _snap(s, art, now + timedelta(hours=1), byline="Reporter B", byline_hash="y2")
        assert [d.type for d in diff_snapshots(prev2, changed)] == [BYLINE_CHANGED]


def test_diff_no_change_is_empty(engine) -> None:
    with session_scope(engine) as s:
        _, art = _seed_article(s)
        now = utcnow()
        prev = _snap(s, art, now)
        same = _snap(s, art, now + timedelta(hours=1))
        assert diff_snapshots(prev, same) == []


def test_diff_downgrades_date_change_from_unreliable_fallback(engine) -> None:
    """A published_at sourced from trafilatura's own guess (not jsonld/meta) is unreliable --
    observed landing on the fetch date itself. The event still gets written (invariant: capture
    everything), but confidence must not be 'confirmed'."""
    with session_scope(engine) as s:
        _, art = _seed_article(s)
        now = utcnow()
        prev = _snap(s, art, now, published_at="2026-09-23",
                    extra_meta={"field_sources": {"published_at": "jsonld"}})
        new = _snap(s, art, now + timedelta(days=10), published_at="2026-10-03",
                   extra_meta={"field_sources": {"published_at": "trafilatura_normalised"}})
        drafts = diff_snapshots(prev, new)
        assert [d.type for d in drafts] == [DATE_CHANGED]
        assert drafts[0].confidence == "unverified"


def test_diff_keeps_date_change_confirmed_when_both_sources_reliable(engine) -> None:
    with session_scope(engine) as s:
        _, art = _seed_article(s)
        now = utcnow()
        prev = _snap(s, art, now, published_at="2026-09-23",
                    extra_meta={"field_sources": {"published_at": "jsonld"}})
        new = _snap(s, art, now + timedelta(days=1), published_at="2026-09-24",
                   extra_meta={"field_sources": {"published_at": "meta"}})
        drafts = diff_snapshots(prev, new)
        assert drafts[0].confidence == "confirmed"


def test_diff_detects_redirected_final_url(engine) -> None:
    with session_scope(engine) as s:
        _, art = _seed_article(s)
        now = utcnow()
        prev = _snap(s, art, now, final_url=URL)
        moved = _snap(s, art, now + timedelta(hours=1), final_url=URL + "-moved")
        assert [d.type for d in diff_snapshots(prev, moved)] == [REDIRECTED]


def _fail(s, art, outcome, status, started_at):
    fa = FetchAttempt(outlet_id=art.outlet_id, article_id=art.id, kind="article", url=URL,
                      vantage="t", started_at=started_at, outcome=outcome, http_status=status)
    s.add(fa)
    s.flush()
    return fa


def test_gone_requires_n_consecutive_failures(engine) -> None:
    """Invariant 4: no GONE from a single failed fetch."""
    with session_scope(engine) as s:
        _, art = _seed_article(s)
        now = utcnow()
        _fail(s, art, "http_error", 404, now - timedelta(hours=8))
        assert check_gone(s, art, now=now) is None
        _fail(s, art, "http_error", 404, now - timedelta(hours=4))
        assert check_gone(s, art, now=now) is None  # only 2 of 3
        _fail(s, art, "http_error", 404, now)
        draft = check_gone(s, art, now=now)
        assert draft is not None and draft.type == GONE_404 and draft.confidence == "confirmed"


def test_gone_requires_minimum_span(engine) -> None:
    """3 failures within minutes of each other: not enough evidence of a real removal yet."""
    with session_scope(engine) as s:
        _, art = _seed_article(s)
        now = utcnow()
        for mins in (10, 5, 0):
            _fail(s, art, "http_error", 404, now - timedelta(minutes=mins))
        assert check_gone(s, art, now=now) is None


def test_gone_ignores_transient_outcomes(engine) -> None:
    """Timeouts/CF-challenges are not gone-shaped; they must not accumulate into a GONE event."""
    with session_scope(engine) as s:
        _, art = _seed_article(s)
        now = utcnow()
        for hrs in (8, 4, 0):
            _fail(s, art, "timeout", None, now - timedelta(hours=hrs))
        assert check_gone(s, art, now=now) is None


def test_gone_robots_blocked_is_lower_confidence(engine) -> None:
    with session_scope(engine) as s:
        _, art = _seed_article(s)
        now = utcnow()
        for hrs in (8, 4, 0):
            _fail(s, art, "robots_blocked", None, now - timedelta(hours=hrs))
        draft = check_gone(s, art, now=now)
        assert draft is not None and draft.type == ROBOTS_BLOCKED and draft.confidence == "probable"


def test_gone_ignores_failures_before_last_snapshot(engine) -> None:
    """Old failures from before the most recent successful capture must not count toward GONE."""
    with session_scope(engine) as s:
        _, art = _seed_article(s)
        now = utcnow()
        for hrs in (10, 9, 8):
            _fail(s, art, "http_error", 404, now - timedelta(hours=hrs))
        _snap(s, art, now - timedelta(hours=5))  # recovered since
        for hrs in (2, 1):
            _fail(s, art, "http_error", 404, now - timedelta(hours=hrs))
        assert check_gone(s, art, now=now) is None  # only 2 failures since the last snapshot


def test_restored_event_links_prior_gone_to_new_snapshot(engine) -> None:
    with session_scope(engine) as s:
        _, art = _seed_article(s)
        now = utcnow()
        gone = write_event(s, art, EventDraft(GONE_404, "confirmed", fetch_attempt_id=None), detected_at=now)
        new_snap = _snap(s, art, now + timedelta(days=1))
        draft = restored_event(gone, new_snap)
        assert draft.type == RESTORED
        assert draft.to_snapshot_id == new_snap.id


def test_write_event_computes_article_age(engine) -> None:
    with session_scope(engine) as s:
        _, art = _seed_article(s)
        detected = art.first_seen + timedelta(hours=30)
        ev = write_event(s, art, EventDraft(HEADLINE_CHANGED, "confirmed"), detected_at=detected)
        assert abs(ev.article_age_at_change - 30.0) < 0.01
        ev_id = ev.id

    with session_scope(engine) as s:
        reloaded = s.get(Event, ev_id)
        assert reloaded is not None and reloaded.type == HEADLINE_CHANGED
