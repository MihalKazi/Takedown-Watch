"""Discovery against a mocked outlet: nothing selected unless fetched and parsed."""

from datetime import timedelta

import httpx

from tw.config import Settings
from tw.db.types import utcnow
from tw.discover.probe import OutletProbe
from tw.fetch.client import Fetcher, FetchResult
from tw.fetch.ratelimit import HostRateLimiter
from tw.outlets import OutletConfig

NOW = utcnow()
FRESH = NOW.strftime("%a, %d %b %Y %H:%M:%S +0000")
OLD = (NOW - timedelta(days=400)).strftime("%a, %d %b %Y %H:%M:%S +0000")

HOME = b"""<!doctype html><html lang="bn"><head>
<meta name="generator" content="WordPress 6.6">
<link rel="alternate" type="application/rss+xml" href="/feed/">
<link rel="alternate" type="application/rss+xml" href="/comments/feed/">
<link rel="alternate" type="application/rss+xml" href="https://feeds.other.example/x">
</head><body>home</body></html>"""


def rss(*links: str, date: str = FRESH) -> bytes:
    items = "".join(f"<item><title>t</title><link>{u}</link><pubDate>{date}</pubDate></item>" for u in links)
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{items}</channel></rss>'.encode()


ROUTES: dict[str, httpx.Response] = {
    "/robots.txt": httpx.Response(200, text=(
        "User-agent: *\nDisallow: /private/\n"
        "Sitemap: https://www.example-news.com/sitemap_index.xml\n"
    )),
    "/": httpx.Response(200, content=HOME, headers={"content-type": "text/html"}),
    "/feed/": httpx.Response(200, content=rss("https://www.example-news.com/a", "https://www.example-news.com/b")),
    "/comments/feed/": httpx.Response(200, content=rss("https://www.example-news.com/a#c1", date=OLD)),
    "/sitemap_index.xml": httpx.Response(200, content=b"""<?xml version="1.0"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://www.example-news.com/news-sitemap.xml</loc></sitemap>
<sitemap><loc>https://www.example-news.com/post-sitemap.xml</loc></sitemap>
</sitemapindex>"""),
    "/news-sitemap.xml": httpx.Response(200, content=f"""<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
<url><loc>https://www.example-news.com/a</loc><news:news><news:publication_date>{NOW.isoformat()}</news:publication_date>
<news:title>t</news:title></news:news></url></urlset>""".encode()),
}


def handler(req: httpx.Request) -> httpx.Response:
    if req.url.host == "feeds.other.example":
        return httpx.Response(200, content=rss("https://elsewhere.example/1"))
    return ROUTES.get(req.url.path, httpx.Response(404))


async def _run(routes_handler=handler, **cfg) -> tuple:
    outlet = OutletConfig(slug="ex", name="Example", language=cfg.get("language", "bn"),
                          base_url="https://www.example-news.com", tier="bangla_mass")
    recorded: list[tuple[str, FetchResult]] = []

    async def nosleep(_: float) -> None:
        return None

    settings = Settings(default_rate_limit_seconds=0.0, http_backoff_base_seconds=0.0)
    async with Fetcher(settings, HostRateLimiter(0.0), transport=httpx.MockTransport(routes_handler),
                       sleep=nosleep) as f:
        r = await OutletProbe(outlet, f, lambda k, res: recorded.append((k, res)), "test", "TakedownWatch").run()
    return r, recorded


async def test_selects_verified_feed_and_news_sitemap_only() -> None:
    r, _ = await _run()
    assert r.rss_urls == ["https://www.example-news.com/feed/"]
    assert r.sitemap_urls == ["https://www.example-news.com/news-sitemap.xml"]
    assert r.limitations == []
    assert r.detected_cms == "WordPress 6.6"
    assert r.homepage["html_lang"] == "bn"


async def test_rejections_carry_reasons() -> None:
    r, _ = await _run()
    by_url = {c.url: c for c in r.candidates}
    assert "stale" in by_url["https://www.example-news.com/comments/feed/"].reason
    assert "only 0%" in by_url["https://feeds.other.example/x"].reason
    assert not by_url["https://www.example-news.com/sitemap_index.xml"].selected


async def test_every_fetch_is_recorded() -> None:
    _, recorded = await _run()
    kinds = [k for k, _ in recorded]
    assert kinds[0] == "robots"
    assert len(recorded) >= 6


async def test_common_paths_not_probed_when_declared_sources_suffice() -> None:
    _, recorded = await _run()
    urls = {res.url for _, res in recorded}
    assert "https://www.example-news.com/rss.xml" not in urls


async def test_robots_disallow_is_respected() -> None:
    def h(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: TakedownWatch\nDisallow: /\n")
        raise AssertionError(f"fetched disallowed {req.url}")

    r, recorded = await _run(h)
    assert [k for k, _ in recorded] == ["robots"]
    assert "robots_disallow_homepage" in r.limitations
    assert r.rss_urls == [] and r.sitemap_urls == []


async def test_unreachable_robots_means_disallow_all() -> None:
    def h(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(503)
        raise AssertionError(f"fetched {req.url} despite unreachable robots.txt")

    r, _ = await _run(h)
    assert "robots_unavailable_http_error" in r.limitations


async def test_cloudflare_blocked_outlet_reports_limitation() -> None:
    def h(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(403, headers={"cf-mitigated": "challenge"})

    r, _ = await _run(h)
    assert "homepage_cf_challenge_403" in r.limitations
    assert "no_rss" in r.limitations and "no_sitemap" in r.limitations


async def test_language_mismatch_reported() -> None:
    r, _ = await _run(language="en")
    assert "html_lang:bn" in r.limitations


async def test_dated_news_child_selects_parent_index() -> None:
    def h(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="Sitemap: https://www.example-news.com/sitemap_index.xml\n")
        if req.url.path == "/sitemap_index.xml":
            return httpx.Response(200, content=b"""<?xml version="1.0"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://www.example-news.com/sitemap/news-2026-09-24.xml</loc></sitemap></sitemapindex>""")
        if req.url.path == "/sitemap/news-2026-09-24.xml":
            return ROUTES["/news-sitemap.xml"]
        return handler(req)

    r, _ = await _run(h)
    assert r.sitemap_urls == ["https://www.example-news.com/sitemap_index.xml"]


async def test_index_children_filtered_on_path_not_host() -> None:
    """bdnews24.com contains "news" in its host; that must not make every child a news candidate."""
    def h(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="Sitemap: https://www.example-news.com/sitemap_index.xml\n")
        return handler(req)

    r, recorded = await _run(h)
    fetched = {res.url for _, res in recorded}
    assert "https://www.example-news.com/news-sitemap.xml" in fetched
    assert "https://www.example-news.com/post-sitemap.xml" not in fetched


async def test_undated_general_sitemap_not_selected() -> None:
    """Section/tag sitemaps have no lastmod; selecting them would crawl index pages, not articles."""
    def h(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="Sitemap: https://www.example-news.com/sections.xml\n")
        if req.url.path == "/sections.xml":
            return httpx.Response(200, content=b"""<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://www.example-news.com/national</loc></url></urlset>""")
        return httpx.Response(404)

    r, _ = await _run(h)
    assert r.sitemap_urls == []
    assert "no_sitemap" in r.limitations


async def test_off_site_index_children_never_fetched() -> None:
    def h(req: httpx.Request) -> httpx.Response:
        if req.url.host == "staging.vendor.example":
            raise AssertionError("fetched a third-party host listed in the outlet's sitemap index")
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="Sitemap: https://www.example-news.com/sitemap_index.xml\n")
        if req.url.path == "/sitemap_index.xml":
            return httpx.Response(200, content=b"""<?xml version="1.0"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://staging.vendor.example/sitemap/news/2026-09-22</loc></sitemap></sitemapindex>""")
        return handler(req)

    await _run(h)
