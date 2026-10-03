"""`tw crawl`: one discovery + capture pass. Outlets run concurrently; each outlet's own requests are
serialised by the per-host rate limiter. Archival is only enqueued here, never performed."""

from __future__ import annotations

import asyncio
import os
import socket
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from sqlalchemy import Engine, select

from tw.blobs import BlobStore
from tw.capture import capture
from tw.config import Settings
from tw.db.models import Article, Job, Outlet
from tw.db.queue import claim
from tw.db.session import session_scope
from tw.discover.ingest import IngestStats, OutletIngest
from tw.fetch.client import Fetcher
from tw.fetch.ratelimit import HostRateLimiter
from tw.log import get_logger
from tw.outlets import load_outlets, sync_outlets
from tw.record import record_fetch
from tw.robots import fetch_robots

log = get_logger(__name__)

CLAIM_BATCH = 10


@dataclass
class OutletRun:
    slug: str
    ingest: IngestStats = field(default_factory=IngestStats)
    captures: Counter = field(default_factory=Counter)
    robots_limitation: str | None = None


async def crawl_outlet(settings: Settings, engine: Engine, fetcher: Fetcher, blobs: BlobStore,
                       outlet: Outlet, max_articles: int | None, worker: str) -> OutletRun:
    run = OutletRun(outlet.slug)

    def rec(kind, res):
        with session_scope(engine) as s:
            record_fetch(s, outlet.id, kind, res, settings.vantage)

    robots = await fetch_robots(fetcher, outlet.base_url, settings.robots_agent_token, rec)
    run.robots_limitation = robots.limitation
    run.ingest = await OutletIngest(settings, engine, fetcher, blobs, outlet, robots).run()

    done = 0
    in_outlet = Job.ref_id.in_(select(Article.id).where(Article.outlet_id == outlet.id))
    for kind in ("fetch_article", "recheck_article"):
        while max_articles is None or done < max_articles:
            batch = CLAIM_BATCH if max_articles is None else min(CLAIM_BATCH, max_articles - done)
            with session_scope(engine) as s:
                job_ids = [j.id for j in claim(s, kind, worker, limit=batch, where=in_outlet)]
            if not job_ids:
                break
            for jid in job_ids:
                run.captures[await capture(settings, engine, fetcher, blobs, outlet, robots, jid)] += 1
                done += 1
            log.info("crawl.progress", outlet=outlet.slug, kind=kind, processed=done, **dict(run.captures))
    return run


async def crawl(settings: Settings, engine: Engine, slugs: list[str] | None,
                max_articles: int | None = None, *, transport=None) -> list[OutletRun]:
    configs = load_outlets(settings.outlets_path)
    unknown = sorted(set(slugs or []) - {c.slug for c in configs})
    if unknown:
        raise SystemExit(f"unknown outlet slug(s): {', '.join(unknown)}")
    with session_scope(engine) as s:
        sync_outlets(s, configs, settings.default_rate_limit_seconds)
    with session_scope(engine) as s:
        outlets = [o for o in s.scalars(select(Outlet).order_by(Outlet.slug))
                   if o.active and (o.slug in slugs if slugs else True)]
    skipped = [o.slug for o in outlets if not (o.rss_urls or o.sitemap_urls)]
    if skipped:
        log.warning("crawl.no_sources", outlets=skipped, hint="run `tw discover`; see outlets.yaml limitations")
    outlets = [o for o in outlets if o.rss_urls or o.sitemap_urls]

    limiter = HostRateLimiter(settings.default_rate_limit_seconds)
    for o in outlets:
        limiter.set_interval(urlsplit(o.base_url).hostname or "", o.rate_limit_seconds)
    blobs = BlobStore(settings.blob_dir)
    worker = f"{socket.gethostname()}:{os.getpid()}"

    async with Fetcher(settings, limiter, transport=transport) as fetcher:
        return list(await asyncio.gather(*(
            crawl_outlet(settings, engine, fetcher, blobs, o, max_articles, worker) for o in outlets
        )))
