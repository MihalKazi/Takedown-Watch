"""End-to-end: first capture schedules a recheck; running that recheck against changed content
emits a real Event row and schedules the next backoff step."""

from datetime import timedelta

import httpx
from sqlalchemy import select

from tw.blobs import BlobStore
from tw.capture import capture
from tw.crawl import crawl
from tw.db.models import Article, Event, Job
from tw.db.queue import claim
from tw.db.session import session_scope
from tw.db.types import utcnow
from tw.fetch.client import Fetcher
from tw.fetch.ratelimit import HostRateLimiter
from tw.outlets import load_outlets

SITE = "https://www.example-news.com"
NOW = utcnow()
FRESH = NOW.strftime("%a, %d %b %Y %H:%M:%S +0000")

OUTLETS = f"""outlets:
  ex:
    name: Example
    language: bn
    base_url: {SITE}
    tier: bangla_mass
    rss_urls: ["{SITE}/feed/"]
    sitemap_urls: []
"""

FEED = f"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>a</title><link>{SITE}/a</link><pubDate>{FRESH}</pubDate></item>
</channel></rss>""".encode()

ARTICLE_V1 = """<!doctype html><html lang="bn"><head></head>
<body><h1>প্রথম শিরোনাম</h1><p>{}</p></body></html>""".format("এটি প্রথম সংস্করণ। " * 40).encode()

ARTICLE_V2 = """<!doctype html><html lang="bn"><head></head>
<body><h1>দ্বিতীয় শিরোনাম</h1><p>{}</p></body></html>""".format("এটি দ্বিতীয় সংস্করণ। " * 40).encode()

_state = {"version": 1}


def handler(req: httpx.Request) -> httpx.Response:
    html = {"content-type": "text/html; charset=utf-8"}
    if req.url.path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\n")
    if req.url.path == "/feed/":
        return httpx.Response(200, content=FEED)
    if req.url.path == "/a":
        body = ARTICLE_V1 if _state["version"] == 1 else ARTICLE_V2
        return httpx.Response(200, content=body, headers=html)
    return httpx.Response(404)


async def test_recheck_detects_headline_change_and_reschedules(settings, engine) -> None:
    settings.outlets_path.write_text(OUTLETS, encoding="utf-8")

    await crawl(settings, engine, None, transport=httpx.MockTransport(handler))

    with session_scope(engine) as s:
        art = s.scalar(select(Article).where(Article.canonical_url == f"{SITE}/a"))
        art_id = art.id
        recheck_job = s.scalar(select(Job).where(Job.kind == "recheck_article", Job.ref_id == art_id))
        assert recheck_job is not None
        first_run_after = recheck_job.run_after
        assert abs((first_run_after - art.first_seen) - timedelta(hours=1)) < timedelta(seconds=1)
        # force it due now so the test doesn't wait on the real schedule
        recheck_job.run_after = utcnow()

    _state["version"] = 2  # outlet silently changes the headline before the recheck fires
    outlet = load_outlets(settings.outlets_path)[0]

    limiter = HostRateLimiter(0.0)
    async with Fetcher(settings, limiter, transport=httpx.MockTransport(handler)) as fetcher:
        from tw.robots import fetch_robots
        robots = await fetch_robots(fetcher, outlet.base_url, settings.robots_agent_token,
                                    lambda *_: None)
        with session_scope(engine) as s:
            from tw.db.models import Outlet as OutletModel
            outlet_row = s.scalar(select(OutletModel).where(OutletModel.slug == "ex"))
            jobs = claim(s, "recheck_article", "w", limit=5)
            job_id = jobs[0].id
        blobs = BlobStore(settings.blob_dir)
        outcome = await capture(settings, engine, fetcher, blobs, outlet_row, robots, job_id)
        assert outcome == "captured"

    with session_scope(engine) as s:
        events = list(s.scalars(select(Event).where(Event.article_id == art_id)))
        # the fixture changes both headline and body text, so both are real, independent events
        assert {e.type for e in events} == {"HEADLINE_CHANGED", "BODY_CHANGED"}
        assert all(e.confidence == "confirmed" for e in events)

        art = s.get(Article, art_id)
        next_job = s.scalar(
            select(Job).where(Job.kind == "recheck_article", Job.ref_id == art_id, Job.status == "pending")
        )
        assert next_job is not None
        assert abs((next_job.run_after - art.first_seen) - timedelta(hours=6)) < timedelta(seconds=1)
