"""Fetch one article, extract, write an append-only snapshot, enqueue archival.

Only a 2xx HTML response yields a snapshot. Every other outcome (404, 410, CF challenge, non-HTML)
exists only as fetch_attempt rows; M2's GONE detection reads those.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from urllib.parse import urljoin, urlsplit

from sqlalchemy import Engine, func, select

from tw.blobs import BlobStore
from tw.config import Settings
from tw.db.models import Article, Event, Job, Outlet, Snapshot
from tw.db.queue import complete, enqueue, fail
from tw.db.session import session_scope
from tw.db.types import utcnow
from tw.discover.canon import canonicalise
from tw.discover.ingest import add_alias
from tw.discover.probe import same_site, site_root
from tw.events import check_gone, diff_snapshots, restored_event, write_event
from tw.extract.extractor import EXTRACTOR_VERSION, Extraction, extract
from tw.extract.hashing import text_hash
from tw.extract.normalise import NORMALISER_VERSION
from tw.fetch.classify import is_retryable
from tw.fetch.client import Fetcher, FetchResult
from tw.log import get_logger
from tw.recheck.backoff import delay_for_step
from tw.record import record_fetch, record_robots_block
from tw.robots import Robots

log = get_logger(__name__)

HTML_TYPES = ("text/html", "application/xhtml+xml")


def is_html(res: FetchResult) -> bool:
    ct = (res.content_type or "").split(";")[0].strip().lower()
    if ct:
        return ct in HTML_TYPES
    head = res.content[:512].lstrip().lower()
    return head.startswith((b"<!doctype html", b"<html"))


async def capture(settings: Settings, engine: Engine, fetcher: Fetcher, blobs: BlobStore,
                  outlet: Outlet, robots: Robots, job_id: int) -> str:
    """Process one fetch_article job. Returns the outcome label for run stats."""
    with session_scope(engine) as s:
        job = s.get(Job, job_id)
        assert job is not None
        art = s.get(Article, job.ref_id)
        if art is None:
            complete(s, job)
            return "missing_article"
        url, article_id = art.canonical_url, art.id

    if not robots.allowed(url):
        with session_scope(engine) as s:
            record_robots_block(s, outlet.id, "article", url, settings.vantage, article_id=article_id)
            complete(s, s.get(Job, job_id))
        return "robots_blocked"

    res = await fetcher.get(url)
    ext: Extraction | None = None
    extract_error: str | None = None
    if res.ok and is_html(res):
        try:
            ext = await asyncio.to_thread(extract, res.content, res.final_url or url)
        except Exception as e:  # noqa: BLE001 - a broken page must not abort the run; it is recorded
            extract_error = f"{type(e).__name__}: {e}"
            log.warning("extract.error", url=url, error=extract_error)

    with session_scope(engine) as s:
        rows = record_fetch(s, outlet.id, "article", res, settings.vantage, article_id=article_id)
        job = s.get(Job, job_id)
        art = s.get(Article, article_id)
        assert job is not None and art is not None

        if res.ok and is_html(res):
            prev = s.scalar(
                select(Snapshot).where(Snapshot.article_id == art.id)
                .order_by(Snapshot.fetched_at.desc()).limit(1)
            )
            snap = _snapshot(settings, s, blobs, outlet, art, res, rows[-1].id, rows[-1].started_at,
                             ext, extract_error)
            art.status = "captured"
            root = site_root(urlsplit(outlet.base_url).hostname)
            if res.final_url and canonicalise(res.final_url) != art.canonical_url and same_site(res.final_url, root):
                add_alias(s, art, res.final_url, "redirect")
            if ext and ext.canonical_link:
                c = urljoin(res.final_url or url, ext.canonical_link)
                if same_site(c, root) and canonicalise(c) != art.canonical_url:
                    add_alias(s, art, c, "canonical")
            enqueue(s, "archive", snap.id, max_attempts=settings.archive_max_attempts)

            if prev is not None:
                last_gone = s.scalar(
                    select(Event).where(Event.article_id == art.id, Event.to_snapshot_id.is_(None))
                    .order_by(Event.detected_at.desc()).limit(1)
                )
                if last_gone is not None:
                    write_event(s, art, restored_event(last_gone, snap), detected_at=snap.fetched_at)
                for draft in diff_snapshots(prev, snap):
                    write_event(s, art, draft, detected_at=snap.fetched_at)
            complete(s, job)  # must close this job before scheduling the next: enqueue()'s
            _schedule_next_recheck(s, art)  # open-job idempotency check would otherwise see it.
            return "captured"
        if is_retryable(res.outcome, res.status):
            fail(s, job, f"{res.outcome} {res.status or ''}".strip(),
                 backoff=timedelta(minutes=settings.fetch_job_backoff_minutes))
            return f"retry_{res.outcome}"
        # final: 404/410/403/CF/non-HTML. The observation is the fetch_attempt row; invariant 4
        # (no GONE from one failed fetch) is enforced inside check_gone.
        draft = check_gone(s, art)
        if draft is not None:
            write_event(s, art, draft)
        complete(s, job)
        if job.kind == "recheck_article":
            _schedule_next_recheck(s, art)
        return "non_html" if res.ok else f"{res.outcome}_{res.status}" if res.status else str(res.outcome)


def _schedule_next_recheck(s, art: Article) -> None:
    """M2 backoff: schedule the next recheck from article.first_seen, per
    tw.recheck.backoff.SCHEDULE. step = how many snapshots already exist, 0-indexed into the
    schedule for the *next* one. No-op once the schedule is exhausted."""
    snapshot_count = s.scalar(select(func.count(Snapshot.id)).where(Snapshot.article_id == art.id)) or 0
    step = snapshot_count - 1
    delay_total = delay_for_step(step)
    if delay_total is None:
        return
    run_at = art.first_seen + delay_total
    delay = run_at - utcnow()
    if delay.total_seconds() < 0:
        delay = timedelta(0)
    enqueue(s, "recheck_article", art.id, delay=delay)


def _snapshot(settings: Settings, s, blobs: BlobStore, outlet: Outlet, art: Article, res: FetchResult,
              fetch_attempt_id: int, fetched_at, ext: Extraction | None, extract_error: str | None) -> Snapshot:
    body = ext.body_text if ext else None
    body_hash = text_hash(body)
    keep_html = outlet.retain_html == "always" or s.scalar(
        select(Snapshot.id).where(Snapshot.article_id == art.id, Snapshot.body_hash == body_hash).limit(1)
    ) is None
    extra = dict(ext.extra_meta) if ext else {}
    if extract_error:
        extra["extract_error"] = extract_error
    snap = Snapshot(
        article_id=art.id, fetch_attempt_id=fetch_attempt_id, fetched_at=fetched_at, http_status=res.status or 0,
        vantage=settings.vantage, final_url=res.final_url or art.canonical_url,
        canonical_link=ext.canonical_link if ext else None,
        headline=ext.headline if ext else None, byline=ext.byline if ext else None,
        published_at=ext.published_at if ext else None, modified_at=ext.modified_at if ext else None,
        body_text=body, body_length=len(body or ""), body_hash=body_hash,
        headline_hash=text_hash(ext.headline if ext else None),
        byline_hash=text_hash(ext.byline if ext else None),
        extra_meta=extra, raw_html_ref=blobs.put(res.content) if keep_html else None,
        extractor_version=EXTRACTOR_VERSION, normaliser_version=NORMALISER_VERSION,
    )
    s.add(snap)
    s.flush()
    return snap
