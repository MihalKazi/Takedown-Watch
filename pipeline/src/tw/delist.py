"""M2: detect an article dropping out of RSS/sitemap listings between two runs of the same feed.

Reads what tw.discover.ingest already wrote (every listing fetch is stored in full, per its own
docstring: "M2 unpublish detection diffs these sets"). Nothing here performs a fetch; it only
compares ListingEntry sets already on disk.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from tw.db.models import Article, ArticleUrl, Event, Listing, ListingEntry, Outlet
from tw.events import diff_listing_presence, write_event


def _latest_two_hashes(s: Session, outlet_id: int, source_url: str) -> tuple[set[str], set[str]]:
    """(current, previous) url_hash sets for one configured feed/sitemap URL."""
    listing_ids = list(s.scalars(
        select(Listing.id).where(Listing.outlet_id == outlet_id, Listing.source_url == source_url)
        .order_by(Listing.fetched_at.desc()).limit(2)
    ))
    sets: list[set[str]] = []
    for lid in listing_ids:
        sets.append(set(s.scalars(select(ListingEntry.url_hash).where(ListingEntry.listing_id == lid))))
    cur = sets[0] if sets else set()
    prev = sets[1] if len(sets) > 1 else set()
    return cur, prev


def detect_delisting(s: Session, outlet: Outlet) -> list[Event]:
    """Call once per outlet after its listings have been (re-)fetched this run. Only meaningful
    once at least two fetches of the same feed exist; the first run of any outlet produces
    nothing here (there is no "previous" to compare against)."""
    cur_rss: set[str] = set()
    prev_rss: set[str] = set()
    for url in outlet.rss_urls:
        c, p = _latest_two_hashes(s, outlet.id, url)
        cur_rss |= c
        prev_rss |= p
    cur_sitemap: set[str] = set()
    prev_sitemap: set[str] = set()
    for url in outlet.sitemap_urls:
        c, p = _latest_two_hashes(s, outlet.id, url)
        cur_sitemap |= c
        prev_sitemap |= p

    if not prev_rss and not prev_sitemap:
        return []  # no prior run to diff against yet

    written: list[Event] = []
    articles = list(s.scalars(
        select(Article).where(Article.outlet_id == outlet.id, Article.status == "captured",
                              Article.merged_into_id.is_(None))
    ))
    for art in articles:
        url_hashes = set(s.scalars(select(ArticleUrl.url_hash).where(ArticleUrl.article_id == art.id)))
        draft = diff_listing_presence(prev_rss, prev_sitemap, cur_rss, cur_sitemap, url_hashes)
        if draft is not None:
            written.append(write_event(s, art, draft))
    return written
