"""DB-backed job queue. Postgres: SELECT ... FOR UPDATE SKIP LOCKED. SQLite: the database-level
write lock serialises claimers, and SQLAlchemy drops the FOR UPDATE clause there."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.orm import Session

from tw.db.models import Job
from tw.db.types import utcnow

LOCK_TIMEOUT = timedelta(hours=1)


def enqueue(session: Session, kind: str, ref_id: int, *, delay: timedelta = timedelta(0),
            max_attempts: int = 5) -> bool:
    """Idempotent: no second open job for the same (kind, ref_id). uq_job_open enforces it in the DB;
    the check here keeps a duplicate from poisoning the caller's transaction."""
    open_job = session.scalar(
        select(Job.id).where(Job.kind == kind, Job.ref_id == ref_id, Job.status.in_(("pending", "running")))
    )
    if open_job is not None:
        return False
    now = utcnow()
    session.add(Job(kind=kind, ref_id=ref_id, run_after=now + delay, created_at=now, max_attempts=max_attempts))
    session.flush()
    return True


def claim(session: Session, kind: str, worker: str, *, limit: int,
          where: ColumnElement[bool] | None = None) -> list[Job]:
    now = utcnow()
    q = (
        select(Job)
        .where(
            Job.kind == kind,
            Job.run_after <= now,
            or_(Job.status == "pending",
                and_(Job.status == "running", Job.locked_at < now - LOCK_TIMEOUT)),
        )
        .order_by(Job.run_after, Job.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    if where is not None:
        q = q.where(where)
    jobs = list(session.scalars(q))
    for j in jobs:
        j.status, j.locked_by, j.locked_at = "running", worker, now
    session.commit()
    return jobs


def complete(session: Session, job: Job) -> None:
    job.status, job.locked_by, job.locked_at = "done", None, None
    job.attempts += 1


def fail(session: Session, job: Job, error: str, *, backoff: timedelta) -> None:
    """Retry with exponential backoff until max_attempts, then park as failed (never deleted)."""
    job.attempts += 1
    job.last_error = error[:2000]
    job.locked_by = job.locked_at = None
    if job.attempts >= job.max_attempts:
        job.status = "failed"
    else:
        job.status = "pending"
        job.run_after = utcnow() + backoff * (2 ** (job.attempts - 1))


def release(session: Session, job: Job) -> None:
    """Hand a claimed job back untouched: the failure was ours (e.g. missing credentials), not the job's."""
    job.status, job.locked_by, job.locked_at = "pending", None, None
