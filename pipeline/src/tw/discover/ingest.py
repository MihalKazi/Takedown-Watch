"""Fetch an outlet's configured feeds and sitemaps, store every listing in full, upsert articles.

The complete URL set of every listing fetch is stored (listing + listing_entry) whether or not its
entries are enqueued: M2 unpublish detection diffs these sets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from tw.blobs import BlobStore
from tw.config import Settings
from tw.db.models import Article, ArticleUrl, Listing, ListingEntry, Outlet
from tw.db.queue import enqueue
from tw.db.session import session_scope
from tw.db.types import utcnow
from tw.discover.canon import canonicalise, url_hash
from tw.discover.listings import ListingItem, parse_listing
from tw.discover.probe import parse_date, same_site, site_root
from tw.fetch.client import Fetcher
from tw.log import get_logger
from tw.record import record_fetch, record_robots_block
from tw.robots import Robots

log = get_logger(__name__)

MAX_INDEX_DEPTH = 2
UNDATED_ALWAYS_ENQUEUE = {"rss", "atom", "news_sitemap"}

# Listing pages, not articles. A dedicated news sitemap only ever lists articles; a general
# sitemap.xml (the only source for outlets with no_news_sitemap, e.g. newagebd) lists every page
# type on the site, including these -- and they can carry a real, recent <lastmod>, so the
# capture-window check alone doesn't filter them out. First path segment is enough here: these
# prefixes are structural CMS sections, not content a URL inside one could plausibly collide with.
NON_ARTICLE_PATH_PREFIXES = {
    "tag", "tags", "topic", "topics", "category", "categories", "author", "authors",
    "search", "page", "pages", "archive", "archives",
    "articlelist",  # newagebd.net's category-listing path, e.g. /articlelist/79/theatre
}


def _is_non_article_path(url: str) -> bool:
    segments = [s for s in urlsplit(url).path.split("/") if s]
    return bool(segments) and segments[0].lower() in NON_ARTICLE_PATH_PREFIXES


@dataclass
class IngestStats:
    listings_ok: int = 0
    listings_failed: list[str] = field(default_factory=list)
    entries_seen: int = 0
    new_articles: int = 0
    known_articles: int = 0
    outside_window: int = 0
    off_site: int = 0
    non_article: int = 0


def resolve_article(session: Session, url: str) -> Article | None:
    au = session.scalar(select(ArticleUrl).where(ArticleUrl.url_hash == url_hash(canonicalise(url))))
    if au is None:
        return None
    art = session.get(Article, au.article_id)
    while art is not None and art.merged_into_id is not None:
        art = session.get(Article, art.merged_into_id)
    return art


def upsert_article(session: Session, outlet_id: int, url: str, source: str,
                   now: datetime) -> tuple[Article, bool]:
    existing = resolve_article(session, url)
    if existing is not None:
        existing.last_seen = now
        return existing, False
    canon = canonicalise(url)
    h = url_hash(canon)
    art = Article(outlet_id=outlet_id, canonical_url=canon, url_hash=h, first_seen=now, last_seen=now,
                  status="discovered")
    session.add(art)
    session.flush()
    session.add(ArticleUrl(article_id=art.id, url=canon, url_hash=h, source=source, first_seen=now))
    enqueue(session, "fetch_article", art.id)
    return art, True


def add_alias(session: Session, art: Article, url: str, source: str) -> None:
    """Record another URL form for `art`. If it already belongs to a different article, the two are
    the same document: the newer is merged into the older. Nothing is deleted."""
    canon = canonicalise(url)
    h = url_hash(canon)
    au = session.scalar(select(ArticleUrl).where(ArticleUrl.url_hash == h))
    if au is None:
        session.add(ArticleUrl(article_id=art.id, url=canon, url_hash=h, source=source, first_seen=utcnow()))
        return
    if au.article_id == art.id:
        return
    other = session.get(Article, au.article_id)
    if other is None or other.merged_into_id == art.id or art.merged_into_id == other.id:
        return
    older, newer = (other, art) if other.id < art.id else (art, other)
    newer.merged_into_id = older.id
    log.info("article.merged", newer=newer.id, older=older.id, via=source)


class OutletIngest:
    def __init__(self, settings: Settings, engine: Engine, fetcher: Fetcher, blobs: BlobStore,
                 outlet: Outlet, robots: Robots) -> None:
        self.settings = settings
        self.engine = engine
        self.fetcher = fetcher
        self.blobs = blobs
        self.outlet = outlet
        self.robots = robots
        self.root = site_root(urlsplit(outlet.base_url).hostname)
        self.cutoff = utcnow() - timedelta(hours=settings.capture_window_hours)
        self.stats = IngestStats()

    async def run(self) -> IngestStats:
        for url in self.outlet.rss_urls:
            await self._listing(url, "rss", 0)
        for url in self.outlet.sitemap_urls:
            await self._listing(url, "sitemap", 0)
        return self.stats

    async def _listing(self, url: str, fetch_kind: str, depth: int) -> None:
        if not self.robots.allowed(url):
            with session_scope(self.engine) as s:
                record_robots_block(s, self.outlet.id, fetch_kind, url, self.settings.vantage)
            self.stats.listings_failed.append(f"{url} (robots)")
            return
        res = await self.fetcher.get(url)
        children: list[str] = []
        with session_scope(self.engine) as s:
            rows = record_fetch(s, self.outlet.id, fetch_kind, res, self.settings.vantage)
            parsed = parse_listing(res.content) if res.ok else None
            if parsed is None:
                self.stats.listings_failed.append(f"{url} ({res.outcome} {res.status or ''})".strip())
                return
            self.stats.listings_ok += 1
            listing = Listing(outlet_id=self.outlet.id, fetch_attempt_id=rows[-1].id, kind=parsed.kind,
                              source_url=url, fetched_at=rows[-1].started_at, entry_count=len(parsed.items),
                              raw_ref=self.blobs.put(res.content))
            s.add(listing)
            s.flush()
            s.add_all(
                ListingEntry(listing_id=listing.id, url=i.url, url_hash=url_hash(canonicalise(i.url)),
                             lastmod=i.date, title=i.title)
                for i in parsed.items
            )
            if parsed.kind == "sitemap_index":
                children = self._pick_children(parsed.items) if depth < MAX_INDEX_DEPTH else []
            else:
                self._upsert(s, parsed.kind, parsed.items)
        for child in children:
            await self._listing(child, "sitemap", depth + 1)

    def _pick_children(self, items: list[ListingItem]) -> list[str]:
        on_site = [i for i in items if same_site(i.url, self.root)]
        dated = [(d, i.url) for i in on_site if (d := parse_date(i.date))]
        recent = sorted(((d, u) for d, u in dated if d >= self.cutoff), reverse=True)
        if dated:
            return [u for _, u in recent[: self.settings.max_index_children]]
        # Undated index: only children that name themselves news listings.
        return [i.url for i in on_site if "news" in urlsplit(i.url).path.lower()][:5]

    def _upsert(self, s: Session, kind: str, items: list[ListingItem]) -> None:
        now = utcnow()
        source = "rss" if kind in ("rss", "atom") else "sitemap"
        for i in items:
            self.stats.entries_seen += 1
            if not same_site(i.url, self.root):
                self.stats.off_site += 1
                continue
            if _is_non_article_path(i.url):
                self.stats.non_article += 1
                continue
            d = parse_date(i.date)
            in_window = d >= self.cutoff if d else kind in UNDATED_ALWAYS_ENQUEUE
            if not in_window:
                # Still upsert last_seen for known articles; new out-of-window URLs stay in listing_entry.
                known = resolve_article(s, i.url)
                if known is not None:
                    known.last_seen = now
                    self.stats.known_articles += 1
                else:
                    self.stats.outside_window += 1
                continue
            _, created = upsert_article(s, self.outlet.id, i.url, source, now)
            if created:
                self.stats.new_articles += 1
            else:
                self.stats.known_articles += 1
