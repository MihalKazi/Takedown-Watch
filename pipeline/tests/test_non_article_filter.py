"""newagebd (and any outlet with no dedicated news sitemap) has only a general sitemap.xml,
which lists every page type -- including tag/category listing pages like /tags/heatwave, which
can carry a real recent <lastmod> and would otherwise pass the capture-window check and get
treated as an article."""

import gzip
from datetime import timedelta
from pathlib import Path

import httpx
from sqlalchemy import select

from tw.crawl import crawl
from tw.db.models import Article
from tw.db.session import session_scope
from tw.db.types import utcnow
from tw.discover.ingest import _is_non_article_path

FIX = Path(__file__).parent / "fixtures"
BN_HTML = gzip.decompress((FIX / "bn/prothomalo-2.html.gz").read_bytes())
SITE = "https://www.example-news.com"
NOW = utcnow()

OUTLETS = f"""outlets:
  ex:
    name: Example
    language: bn
    base_url: {SITE}
    tier: bangla_mass
    rss_urls: []
    sitemap_urls: ["{SITE}/sitemap.xml"]
"""

SITEMAP = f"""<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>{SITE}/a</loc><lastmod>{NOW.isoformat()}</lastmod></url>
<url><loc>{SITE}/tags/heatwave</loc><lastmod>{NOW.isoformat()}</lastmod></url>
<url><loc>{SITE}/category/sports</loc><lastmod>{NOW.isoformat()}</lastmod></url>
<url><loc>{SITE}/author/jane-doe</loc><lastmod>{NOW.isoformat()}</lastmod></url>
</urlset>""".encode()


def handler(req: httpx.Request) -> httpx.Response:
    html = {"content-type": "text/html; charset=utf-8"}
    return {
        "/robots.txt": httpx.Response(200, text="User-agent: *\n"),
        "/sitemap.xml": httpx.Response(200, content=SITEMAP),
        "/a": httpx.Response(200, content=BN_HTML, headers=html),
    }.get(req.url.path, httpx.Response(404))


def test_is_non_article_path() -> None:
    assert _is_non_article_path(f"{SITE}/tags/heatwave") is True
    assert _is_non_article_path(f"{SITE}/category/sports") is True
    assert _is_non_article_path(f"{SITE}/author/jane-doe") is True
    assert _is_non_article_path(f"{SITE}/bangladesh/some-real-article-slug") is False
    assert _is_non_article_path(f"{SITE}/") is False


async def test_tag_and_category_pages_never_become_articles(settings, engine) -> None:
    settings.outlets_path.write_text(OUTLETS, encoding="utf-8")
    runs = await crawl(settings, engine, None, transport=httpx.MockTransport(handler))
    assert runs[0].ingest.non_article == 3  # tags, category, author
    assert runs[0].ingest.new_articles == 1  # only /a

    with session_scope(engine) as s:
        urls = {a.canonical_url for a in s.scalars(select(Article))}
        assert f"{SITE}/a" in urls
        assert f"{SITE}/tags/heatwave" not in urls
        assert f"{SITE}/category/sports" not in urls
        assert f"{SITE}/author/jane-doe" not in urls
