"""End-to-end crawl against a mocked outlet serving real article HTML."""

import gzip
from datetime import timedelta
from pathlib import Path

import httpx
from sqlalchemy import func, select

from tw.blobs import BlobStore
from tw.crawl import crawl
from tw.db.models import Article, ArticleUrl, FetchAttempt, Job, Listing, ListingEntry, Snapshot
from tw.db.session import session_scope
from tw.db.types import utcnow
from tw.extract.extractor import EXTRACTOR_VERSION
from tw.extract.normalise import NORMALISER_VERSION

FIX = Path(__file__).parent / "fixtures"
BN_HTML = gzip.decompress((FIX / "bn/prothomalo-2.html.gz").read_bytes())
SITE = "https://www.example-news.com"
NOW = utcnow()
FRESH = NOW.strftime("%a, %d %b %Y %H:%M:%S +0000")
OLD = (NOW - timedelta(days=10)).isoformat()

OUTLETS = f"""outlets:
  ex:
    name: Example
    language: bn
    base_url: {SITE}
    tier: bangla_mass
    rss_urls: ["{SITE}/feed/"]
    sitemap_urls: ["{SITE}/news-sitemap.xml"]
"""

FEED = f"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>a</title><link>{SITE}/a?utm_source=rss</link><pubDate>{FRESH}</pubDate></item>
<item><title>b</title><link>{SITE}/b</link><pubDate>{FRESH}</pubDate></item>
<item><title>private</title><link>{SITE}/private/x</link><pubDate>{FRESH}</pubDate></item>
</channel></rss>""".encode()

NEWS = f"""<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
<url><loc>{SITE}/a</loc><news:news><news:publication_date>{NOW.isoformat()}</news:publication_date></news:news></url>
<url><loc>{SITE}/c-old</loc><news:news><news:publication_date>{OLD}</news:publication_date></news:news></url>
<url><loc>{SITE}/d-gone</loc><news:news><news:publication_date>{NOW.isoformat()}</news:publication_date></news:news></url>
<url><loc>https://elsewhere.example/x</loc><news:news><news:publication_date>{NOW.isoformat()}</news:publication_date></news:news></url>
</urlset>""".encode()

B_HTML = f"""<!doctype html><html lang="bn"><head><link rel="canonical" href="{SITE}/a"></head>
<body><h1>একই খবর</h1><p>{'এটি একই প্রতিবেদনের দ্বিতীয় ঠিকানা। ' * 40}</p></body></html>""".encode()


def handler(req: httpx.Request) -> httpx.Response:
    html = {"content-type": "text/html; charset=utf-8"}
    return {
        "/robots.txt": httpx.Response(200, text="User-agent: *\nDisallow: /private/\n"),
        "/feed/": httpx.Response(200, content=FEED),
        "/news-sitemap.xml": httpx.Response(200, content=NEWS),
        "/a": httpx.Response(200, content=BN_HTML, headers=html),
        "/b": httpx.Response(200, content=B_HTML, headers=html),
    }.get(req.url.path, httpx.Response(404))


async def _crawl(settings, engine):
    settings.outlets_path.write_text(OUTLETS, encoding="utf-8")
    return await crawl(settings, engine, None, transport=httpx.MockTransport(handler))


def _count(s, model, *where):
    return s.scalar(select(func.count()).select_from(model).where(*where))


async def test_crawl_end_to_end(settings, engine) -> None:
    runs = await _crawl(settings, engine)
    assert runs[0].ingest.new_articles == 4  # a, b, private/x, d-gone
    assert runs[0].ingest.outside_window == 1  # c-old
    assert runs[0].ingest.off_site == 1

    with session_scope(engine) as s:
        urls = {a.canonical_url for a in s.scalars(select(Article))}
        assert f"{SITE}/a" in urls  # utm stripped, and the feed + sitemap forms are one article
        assert f"{SITE}/c-old" not in urls

        # Out-of-window URL still recorded in the full listing set.
        assert _count(s, ListingEntry, ListingEntry.url == f"{SITE}/c-old") == 1
        assert _count(s, Listing) == 2

        # Real Bangla page -> snapshot with raw fields, hashes and versions.
        a = s.scalar(select(Article).where(Article.canonical_url == f"{SITE}/a"))
        snap = s.scalar(select(Snapshot).where(Snapshot.article_id == a.id))
        assert snap.headline and "আব্বু" in snap.headline
        assert snap.body_length > 1000
        assert snap.extractor_version == EXTRACTOR_VERSION
        assert snap.normaliser_version == NORMALISER_VERSION
        assert BlobStore(settings.blob_dir).get(snap.raw_html_ref) == BN_HTML
        assert a.status == "captured"

        # 404: observation recorded, no snapshot, job finished (never retried).
        d = s.scalar(select(Article).where(Article.canonical_url == f"{SITE}/d-gone"))
        assert _count(s, Snapshot, Snapshot.article_id == d.id) == 0
        assert _count(s, FetchAttempt, FetchAttempt.article_id == d.id, FetchAttempt.http_status == 404) == 1
        assert s.scalar(select(Job.status).where(Job.kind == "fetch_article", Job.ref_id == d.id)) == "done"

        # robots.txt disallow: not requested, but the decision is on record.
        p = s.scalar(select(Article).where(Article.canonical_url == f"{SITE}/private/x"))
        assert s.scalar(select(FetchAttempt.outcome).where(FetchAttempt.article_id == p.id)) == "robots_blocked"

        # b declares a's URL canonical: same document -> b merged into a, nothing deleted.
        b = s.scalar(select(Article).where(Article.canonical_url == f"{SITE}/b"))
        assert b.merged_into_id == a.id
        assert _count(s, Snapshot, Snapshot.article_id == b.id) == 1

        # Archival queued for every snapshot, not performed during crawl.
        assert _count(s, Job, Job.kind == "archive", Job.status == "pending") == 2


async def test_recrawl_creates_no_duplicates(settings, engine) -> None:
    await _crawl(settings, engine)
    with session_scope(engine) as s:
        before = (_count(s, Article), _count(s, ArticleUrl), _count(s, Snapshot), _count(s, Job))
    runs = await _crawl(settings, engine)
    assert runs[0].ingest.new_articles == 0
    with session_scope(engine) as s:
        after = (_count(s, Article), _count(s, ArticleUrl), _count(s, Snapshot), _count(s, Job))
        assert after == before
        assert _count(s, Listing) == 4  # listings are observations: stored every run


async def test_max_articles_leaves_rest_queued(settings, engine) -> None:
    settings.outlets_path.write_text(OUTLETS, encoding="utf-8")
    await crawl(settings, engine, None, max_articles=1, transport=httpx.MockTransport(handler))
    with session_scope(engine) as s:
        assert _count(s, Job, Job.kind == "fetch_article", Job.status == "done") == 1
        assert _count(s, Job, Job.kind == "fetch_article", Job.status == "pending") == 3
