"""`tw archive`: drain the archival queue. Separate from crawl; never blocks capture.

Every submission is an archive_attempt row. Coverage gap = snapshot with no `ok` attempt.
"""

from __future__ import annotations

import os
import socket
from collections import Counter
from datetime import timedelta

from sqlalchemy import Engine, func, select

from tw.config import Settings
from tw.db.models import ArchiveAttempt, Job, Snapshot
from tw.db.queue import claim, complete, enqueue, fail, release
from tw.db.session import session_scope
from tw.db.types import utcnow
from tw.archive.spn import SpnClient, SpnResult
from tw.fetch.ratelimit import HostRateLimiter
from tw.log import get_logger

log = get_logger(__name__)


def _apply(attempt: ArchiveAttempt, res: SpnResult) -> None:
    attempt.outcome = res.outcome
    attempt.spn_job_id = res.job_id or attempt.spn_job_id
    attempt.archive_url = res.archive_url
    attempt.error = res.error
    if res.outcome != "pending":
        attempt.completed_at = utcnow()


async def drain(settings: Settings, engine: Engine, limit: int | None = None,
                client: SpnClient | None = None) -> Counter:
    counts: Counter = Counter()
    spn = client or SpnClient(settings, HostRateLimiter(settings.default_rate_limit_seconds))
    worker = f"{socket.gethostname()}:{os.getpid()}"
    log.info("archive.start", mode=spn.mode)
    try:
        # 1. Resolve submissions left pending by earlier runs.
        with session_scope(engine) as s:
            pending = [(a.id, a.spn_job_id) for a in s.scalars(
                select(ArchiveAttempt).where(ArchiveAttempt.outcome == "pending",
                                             ArchiveAttempt.spn_job_id.is_not(None)))]
        for attempt_id, job_id in pending:
            res = await spn.status(job_id)
            with session_scope(engine) as s:
                a = s.get(ArchiveAttempt, attempt_id)
                _apply(a, res)
                if res.outcome not in ("ok", "pending"):
                    enqueue(s, "archive", a.snapshot_id, max_attempts=settings.archive_max_attempts)
            counts[f"resolved_{res.outcome}"] += 1

        # 2. New submissions.
        processed = 0
        while limit is None or processed < limit:
            with session_scope(engine) as s:
                jobs = claim(s, "archive", worker, limit=1)
                if not jobs:
                    break
                job_id, snap_id = jobs[0].id, jobs[0].ref_id
                snap = s.get(Snapshot, snap_id)
                url = snap.final_url if snap else None
                attempt = ArchiveAttempt(snapshot_id=snap_id, requested_at=utcnow(), mode=spn.mode,
                                         outcome="pending")
                s.add(attempt)
                s.flush()
                attempt_id = attempt.id
            processed += 1
            if url is None:
                with session_scope(engine) as s:
                    _apply(s.get(ArchiveAttempt, attempt_id), SpnResult("error", error="snapshot missing"))
                    complete(s, s.get(Job, job_id))
                continue
            res = await spn.save(url)
            counts[res.outcome] += 1
            with session_scope(engine) as s:
                _apply(s.get(ArchiveAttempt, attempt_id), res)
                job = s.get(Job, job_id)
                if res.outcome in ("ok", "pending"):
                    complete(s, job)  # pending: resolved by step 1 of a later run
                elif res.outcome == "auth_required":
                    release(s, job)  # our configuration, not this URL: no attempt counted
                else:
                    fail(s, job, f"{res.outcome}: {res.error}",
                         backoff=timedelta(minutes=settings.archive_job_backoff_minutes))
            log.info("archive.result", url=url, outcome=res.outcome, archive_url=res.archive_url, error=res.error)
            if res.outcome == "rate_limited":
                log.warning("archive.rate_limited", hint="stopping this run; remaining jobs stay queued")
                break
            if res.outcome == "auth_required":
                log.error("archive.auth_required", mode=spn.mode, error=res.error,
                          hint="set TW_IA_ACCESS_KEY and TW_IA_SECRET_KEY (https://archive.org/account/s3.php)")
                counts["stopped_auth_required"] = 1
                break
    finally:
        if client is None:
            await spn.aclose()
    return counts


def coverage(engine: Engine) -> tuple[int, int]:
    """(snapshots, snapshots with at least one successful archive)."""
    with session_scope(engine) as s:
        total = s.scalar(select(func.count(Snapshot.id))) or 0
        ok = s.scalar(select(func.count(func.distinct(ArchiveAttempt.snapshot_id)))
                      .where(ArchiveAttempt.outcome == "ok")) or 0
    return total, ok
