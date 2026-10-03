"""`tw discover`: probe every selected outlet concurrently, persist every fetch, write results back."""

from __future__ import annotations

import asyncio
import json
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from tw.config import Settings
from tw.discover.probe import DiscoveryResult, OutletProbe
from tw.fetch.client import Fetcher
from tw.fetch.ratelimit import HostRateLimiter
from tw.log import get_logger
from tw.outlets import OutletConfig, load_outlets, sync_outlets, write_back
from tw.record import record_fetch

log = get_logger(__name__)

OUTLET_CONCURRENCY = 6


async def discover(settings: Settings, session: Session, slugs: list[str] | None, *,
                   write: bool = True) -> list[DiscoveryResult]:
    configs = load_outlets(settings.outlets_path)
    known = {c.slug for c in configs}
    unknown = sorted(set(slugs or []) - known)
    if unknown:
        raise SystemExit(f"unknown outlet slug(s): {', '.join(unknown)}")
    rows = sync_outlets(session, configs, settings.default_rate_limit_seconds)
    session.commit()
    targets = [c for c in configs if (c.slug in slugs if slugs else c.active)]

    limiter = HostRateLimiter(settings.default_rate_limit_seconds)
    for c in targets:
        limiter.set_interval(urlsplit(c.base_url).hostname or "", rows[c.slug].rate_limit_seconds)

    sem = asyncio.Semaphore(OUTLET_CONCURRENCY)
    results: list[DiscoveryResult] = []

    async with Fetcher(settings, limiter) as fetcher:
        async def one(c: OutletConfig) -> DiscoveryResult:
            outlet = rows[c.slug]
            async with sem:
                log.info("discover.start", outlet=c.slug)
                probe = OutletProbe(
                    c, fetcher,
                    record=lambda kind, res: record_fetch(session, outlet.id, kind, res, settings.vantage),
                    vantage=settings.vantage, robots_token=settings.robots_agent_token,
                )
                r = await probe.run()
                session.commit()
                log.info("discover.done", outlet=c.slug, rss=len(r.rss_urls), sitemaps=len(r.sitemap_urls),
                         limitations=r.limitations)
                return r

        results = list(await asyncio.gather(*(one(c) for c in targets)))

    settings.report_dir.mkdir(parents=True, exist_ok=True)
    stamp = results[0].checked_at[:19].replace(":", "") if results else "empty"
    report_path = settings.report_dir / f"discover-{stamp}.json"
    report_path.write_text(json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=2),
                           encoding="utf-8")
    log.info("discover.report", path=str(report_path))

    if write:
        for r in results:
            c = next(c for c in targets if c.slug == r.slug)
            updates: dict = {
                "rss_urls": r.rss_urls,
                "sitemap_urls": r.sitemap_urls,
                "limitations": r.limitations,
                "discovery": {
                    "checked_at": r.checked_at,
                    "vantage": r.vantage,
                    "homepage_final_url": r.homepage.get("final_url"),
                    "homepage_status": r.homepage.get("status"),
                    "html_lang": r.homepage.get("html_lang"),
                    "detected_cms": r.detected_cms,
                    "robots_sitemaps": r.robots.get("sitemaps", []),
                    "candidates_checked": len(r.candidates),
                },
            }
            if c.cms is None and r.detected_cms:
                updates["cms"] = r.detected_cms
            write_back(settings.outlets_path, r.slug, updates)
        sync_outlets(session, load_outlets(settings.outlets_path), settings.default_rate_limit_seconds)
        session.commit()
    return results
