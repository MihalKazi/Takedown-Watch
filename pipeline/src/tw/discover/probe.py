"""Feed and sitemap discovery for one outlet.

Nothing is trusted until fetched and parsed. Candidate sources, in order:
  1. robots.txt `Sitemap:` lines
  2. <link rel="alternate" type="application/rss+xml|atom+xml"> on the homepage
  3. common paths, probed only when 1-2 yielded nothing usable (keeps request count low)
  4. children of a verified sitemap index whose URL mentions "news"

A candidate is *verified* when it returns 2xx and parses as RSS/Atom/sitemap with at least one entry.
It is *selected* (written to outlets.yaml) when it is verified, mostly links to the outlet's own
site, and is not stale. Every candidate, selected or not, is reported with the reason.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit

from lxml import html as lxml_html

from tw.db.types import utcnow
from tw.discover.listings import parse_listing
from tw.fetch.client import Fetcher, FetchResult
from tw.log import get_logger
from tw.outlets import OutletConfig
from tw.robots import Robots, fetch_robots

log = get_logger(__name__)

COMMON_RSS_PATHS = ("/feed", "/rss", "/rss.xml", "/feed.xml", "/feeds/latest", "/rss/latest-news")
COMMON_SITEMAP_PATHS = (
    "/news-sitemap.xml",
    "/sitemap-news.xml",
    "/sitemap_news.xml",
    "/sitemap/news.xml",
    "/sitemap.xml",
    "/sitemap_index.xml",
)
MAX_INDEX_CHILDREN = 5
STALE_AFTER = timedelta(days=30)
MIN_ON_SITE_SHARE = 0.5

_DATED = re.compile(r"(19|20)\d{2}[-_/]?(0[1-9]|1[0-2])")

FEED_TYPES = {"application/rss+xml", "application/atom+xml", "application/rdf+xml"}

# (fetch kind, fetch result) -> nothing. Caller persists attempts; probe stays DB-agnostic.
Recorder = Callable[[str, FetchResult], None]


@dataclass
class Candidate:
    url: str
    source: str  # robots | homepage_link | common_path | index_child
    outcome: str | None = None
    status: int | None = None
    final_url: str | None = None
    kind: str | None = None  # rss | atom | sitemap | news_sitemap | sitemap_index | unparseable
    entries: int = 0
    on_site_share: float | None = None
    newest: str | None = None  # ISO 8601, UTC
    parent: str | None = None  # sitemap index this came from
    selected: bool = False
    reason: str = ""


@dataclass
class DiscoveryResult:
    slug: str
    checked_at: str
    vantage: str
    homepage: dict = field(default_factory=dict)
    robots: dict = field(default_factory=dict)
    candidates: list[Candidate] = field(default_factory=list)
    rss_urls: list[str] = field(default_factory=list)
    sitemap_urls: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    detected_cms: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def site_root(host: str | None) -> str:
    return (host or "").lower().rstrip(".").removeprefix("www.")


def same_site(url: str, root: str) -> bool:
    h = site_root(urlsplit(url).hostname)
    return h == root or h.endswith("." + root)


def parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    dt: datetime | None = None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=utcnow().tzinfo)
    return dt


_LANG_RE = re.compile(rb"<html\b[^>]*?\blang\s*=\s*[\"']?([A-Za-z]{2,3}(?:-[A-Za-z0-9]+)*)", re.I)


def inspect_homepage(content: bytes, base: str) -> dict:
    m = _LANG_RE.search(content[:65_536])
    out: dict = {"html_lang": m.group(1).decode() if m else None, "feed_links": [], "generator": None}
    try:
        doc = lxml_html.fromstring(content)
    except (ValueError, lxml_html.etree.ParserError):
        return out
    for link in doc.iter("link"):
        rels = (link.get("rel") or "").lower().split()
        if "alternate" in rels and (link.get("type") or "").lower().strip() in FEED_TYPES and link.get("href"):
            out["feed_links"].append(urljoin(base, link.get("href").strip()))
    gen = doc.xpath("//meta[translate(@name,'GENERATOR','generator')='generator']/@content")
    if gen:
        out["generator"] = str(gen[0]).strip()
    return out


def detect_cms(content: bytes, generator: str | None) -> str | None:
    if generator:
        return generator
    if b"/wp-content/" in content or b"/wp-includes/" in content:
        return "WordPress"
    if b"quintype" in content.lower():
        return "Quintype"
    if b"__NEXT_DATA__" in content:
        return "Next.js"
    return None


class OutletProbe:
    def __init__(self, outlet: OutletConfig, fetcher: Fetcher, record: Recorder, vantage: str,
                 robots_token: str) -> None:
        self.outlet = outlet
        self.fetcher = fetcher
        self.record = record
        self.robots_token = robots_token
        self.root = site_root(urlsplit(outlet.base_url).hostname)
        self.result = DiscoveryResult(slug=outlet.slug, checked_at=utcnow().isoformat(), vantage=vantage)
        self.robots: Robots | None = None
        self._seen: set[str] = set()
        self._item_sets: dict[frozenset[str], str] = {}

    async def _get(self, kind: str, url: str) -> FetchResult:
        res = await self.fetcher.get(url)
        self.record(kind, res)
        return res

    def _allowed(self, url: str) -> bool:
        return self.robots is None or self.robots.allowed(url)

    async def run(self) -> DiscoveryResult:
        r = self.result
        base = self.outlet.base_url + "/"
        await self._fetch_robots(base)

        if self.robots is not None and self.robots.disallow_all:
            r.homepage = {"url": base, "skipped": "robots_disallow"}
            r.limitations.append("robots_disallow_homepage")
            self._select()
            return r

        if self._allowed(base):
            home = await self._get("probe", base)
            r.homepage = {"url": base, "final_url": home.final_url, "status": home.status,
                          "outcome": str(home.outcome)}
            if home.ok:
                info = inspect_homepage(home.content, home.final_url or base)
                r.homepage["html_lang"] = info["html_lang"]
                r.detected_cms = detect_cms(home.content, info["generator"])
                for u in info["feed_links"]:
                    await self._try(u, "homepage_link")
            else:
                r.limitations.append(f"homepage_{home.outcome}" + (f"_{home.status}" if home.status else ""))
            if home.final_url and not same_site(home.final_url, self.root):
                r.limitations.append(f"moved:{urlsplit(home.final_url).hostname}")
            lang = (r.homepage.get("html_lang") or "").split("-")[0].lower()
            if lang and lang != self.outlet.language:
                r.limitations.append(f"html_lang:{r.homepage['html_lang']}")
        else:
            r.homepage = {"url": base, "skipped": "robots_disallow"}
            r.limitations.append("robots_disallow_homepage")

        if not self._verified("rss", "atom"):
            for p in COMMON_RSS_PATHS:
                await self._try(urljoin(base, p), "common_path")
        if not self._verified("news_sitemap"):
            for p in COMMON_SITEMAP_PATHS:
                await self._try(urljoin(base, p), "common_path")
                if self._verified("news_sitemap"):
                    break

        self._select()
        return r

    async def _fetch_robots(self, base: str) -> None:
        self.robots = await fetch_robots(self.fetcher, base, self.robots_token, self.record)
        if self.robots.limitation:
            self.result.limitations.append(self.robots.limitation)
        self.result.robots = self.robots.info
        for sm in self.robots.info["sitemaps"]:
            await self._try(sm, "robots")

    def _verified(self, *kinds: str) -> bool:
        return any(c.kind in kinds and c.entries > 0 for c in self.result.candidates)

    async def _try(self, url: str, source: str, parent: str | None = None) -> Candidate | None:
        key = url.split("#")[0]
        if key in self._seen:
            return None
        self._seen.add(key)
        cand = Candidate(url=url, source=source, parent=parent)
        self.result.candidates.append(cand)
        if not self._allowed(url):
            cand.reason = "robots.txt disallows"
            return cand
        res = await self._get("probe", url)
        cand.outcome, cand.status, cand.final_url = str(res.outcome), res.status, res.final_url
        if not res.ok:
            cand.reason = f"fetch {res.outcome}" + (f" {res.status}" if res.status else "")
            return cand
        if res.final_url and res.final_url.split("#")[0] != key:
            if res.final_url in self._seen:
                cand.reason = f"redirects to already-checked {res.final_url}"
                return cand
            self._seen.add(res.final_url)
        parsed = parse_listing(res.content)
        if parsed is None:
            cand.kind = "unparseable"
            cand.reason = f"not RSS/Atom/sitemap (content-type {res.content_type})"
            return cand
        cand.kind = parsed.kind
        cand.entries = len(parsed.items)
        if not parsed.items:
            cand.reason = "parsed but empty"
            return cand
        cand.on_site_share = round(sum(same_site(i.url, self.root) for i in parsed.items) / len(parsed.items), 3)
        dates = [d for i in parsed.items if (d := parse_date(i.date))]
        if dates:
            cand.newest = max(dates).isoformat()
        if parsed.kind == "sitemap_index":
            # Off-site children are never fetched: an index pointing elsewhere is the outlet's
            # misconfiguration, and the other host is not ours to crawl.
            children = [i.url for i in parsed.items
                        if "news" in urlsplit(i.url).path.lower() and same_site(i.url, self.root)]
            for child in children[:MAX_INDEX_CHILDREN]:
                await self._try(child, "index_child", parent=cand.final_url or url)
        else:
            items = frozenset(i.url for i in parsed.items)
            if items in self._item_sets:
                cand.reason = f"same entries as {self._item_sets[items]}"
            else:
                self._item_sets[items] = cand.final_url or url
        return cand

    def _selectable(self, c: Candidate) -> bool:
        if c.entries <= 0 or c.reason:
            return False
        if c.on_site_share is not None and c.on_site_share < MIN_ON_SITE_SHARE:
            c.reason = f"only {c.on_site_share:.0%} of entries on {self.root}"
            return False
        if c.kind != "sitemap_index" and c.newest:
            age = utcnow() - datetime.fromisoformat(c.newest)
            if age > STALE_AFTER:
                c.reason = f"stale: newest entry {age.days} days old"
                return False
        return True

    def _select(self) -> None:
        r = self.result
        feeds = [c for c in r.candidates if c.kind in ("rss", "atom") and self._selectable(c)]
        news = [c for c in r.candidates if c.kind == "news_sitemap" and self._selectable(c)]
        for c in feeds + news:
            c.selected = True
            if c.parent and _DATED.search(urlsplit(c.url).path):
                # A dated child (news-2026-09-24.xml) goes stale tomorrow; keep the index instead.
                c.selected = False
                c.reason = "dated child; parent index selected"
                parent = next(p for p in r.candidates if (p.final_url or p.url) == c.parent)
                parent.selected = True
                parent.reason = "index of dated news sitemaps"
        if not news:
            # No news sitemap: fall back to the site's declared general sitemaps, so crawl still has
            # a complete URL set to diff in M2. Prefer robots.txt declarations over guessed paths.
            # Undated sitemaps list sections/tags/static pages, not articles: not a usable fallback.
            general = [c for c in r.candidates if c.kind in ("sitemap_index", "sitemap") and self._selectable(c)]
            for c in general:
                if c.newest is None:
                    c.reason = "no dated entries; likely sections, not articles"
            general = [c for c in general if c.newest is not None]
            declared = [c for c in general if c.source == "robots"] or general[:1]
            for c in declared:
                c.selected = True
                c.reason = "no news sitemap; general sitemap selected"
        for c in r.candidates:
            if not c.selected and not c.reason:
                c.reason = "verified, not needed"
        r.rss_urls = [c.final_url or c.url for c in r.candidates if c.selected and c.kind in ("rss", "atom")]
        r.sitemap_urls = [c.final_url or c.url for c in r.candidates
                          if c.selected and c.kind in ("news_sitemap", "sitemap", "sitemap_index")]
        if not r.rss_urls:
            r.limitations.append("no_rss")
        if not r.sitemap_urls:
            r.limitations.append("no_sitemap")
        elif not news:
            r.limitations.append("no_news_sitemap")
