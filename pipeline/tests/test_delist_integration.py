from datetime import timedelta

from sqlalchemy import select

from tw.db.models import Article, ArticleUrl, Event, FetchAttempt, Listing, ListingEntry, Outlet
from tw.db.session import session_scope
from tw.db.types import utcnow
from tw.delist import detect_delisting
from tw.events import DEINDEXED

SITE = "https://www.example-news.com"
FEED = f"{SITE}/feed/"


def _seed_listing(s, outlet_id, source_url, kind, urls, fetched_at):
    fa = FetchAttempt(outlet_id=outlet_id, kind="rss", url=source_url, vantage="t",
                      started_at=fetched_at, outcome="ok", http_status=200)
    s.add(fa)
    s.flush()
    listing = Listing(outlet_id=outlet_id, fetch_attempt_id=fa.id, kind=kind, source_url=source_url,
                      fetched_at=fetched_at, entry_count=len(urls), raw_ref="0" * 64)
    s.add(listing)
    s.flush()
    s.add_all(ListingEntry(listing_id=listing.id, url=u, url_hash=u, lastmod=None, title=None) for u in urls)
    s.flush()


def test_detect_delisting_emits_deindexed_on_drop(engine) -> None:
    now = utcnow()
    with session_scope(engine) as s:
        o = Outlet(slug="ex", name="Ex", language="en", base_url=SITE, tier="english",
                  rss_urls=[FEED], sitemap_urls=[])
        s.add(o)
        s.flush()
        art = Article(outlet_id=o.id, canonical_url=f"{SITE}/a", url_hash=f"{SITE}/a",
                     first_seen=now - timedelta(hours=2), last_seen=now, status="captured")
        s.add(art)
        s.flush()
        s.add(ArticleUrl(article_id=art.id, url=f"{SITE}/a", url_hash=f"{SITE}/a", source="rss",
                         first_seen=now - timedelta(hours=2)))
        s.flush()
        outlet_id, article_id = o.id, art.id

        # run 1: article is listed
        _seed_listing(s, outlet_id, FEED, "rss", [f"{SITE}/a", f"{SITE}/b"], now - timedelta(hours=1))

    with session_scope(engine) as s:
        o = s.get(Outlet, outlet_id)
        events = detect_delisting(s, o)
        assert events == []  # only one run so far: nothing to diff against

    with session_scope(engine) as s:
        # run 2: article has dropped out of the feed
        _seed_listing(s, outlet_id, FEED, "rss", [f"{SITE}/b"], now)

    with session_scope(engine) as s:
        o = s.get(Outlet, outlet_id)
        events = detect_delisting(s, o)
        assert len(events) == 1 and events[0].type == DEINDEXED and events[0].article_id == article_id

    with session_scope(engine) as s:
        # run 3: still absent -- must not refire
        _seed_listing(s, outlet_id, FEED, "rss", [f"{SITE}/b"], now + timedelta(hours=1))

    with session_scope(engine) as s:
        o = s.get(Outlet, outlet_id)
        assert detect_delisting(s, o) == []
        assert s.scalar(select(Event).where(Event.article_id == article_id, Event.type == DEINDEXED)) is not None
