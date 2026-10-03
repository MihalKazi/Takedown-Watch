"""Persist fetch results. Every HTTP attempt becomes a fetch_attempt row, whatever its outcome."""

from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from tw.db.models import FetchAttempt, RobotsSnapshot
from tw.db.types import utcnow
from tw.fetch.classify import Outcome
from tw.fetch.client import FetchResult


def record_fetch(session: Session, outlet_id: int, kind: str, res: FetchResult, vantage: str,
                 *, article_id: int | None = None) -> list[FetchAttempt]:
    rows = [
        FetchAttempt(
            outlet_id=outlet_id, article_id=article_id, kind=kind, url=a.url, final_url=a.final_url,
            vantage=vantage, started_at=a.started_at, elapsed_ms=a.elapsed_ms, attempt=a.attempt,
            outcome=str(a.outcome), http_status=a.http_status, content_type=a.content_type,
            response_bytes=a.response_bytes, error=a.error,
        )
        for a in res.attempts
    ]
    session.add_all(rows)
    session.flush()
    if kind == "robots" and res.ok and rows:
        session.add(RobotsSnapshot(
            outlet_id=outlet_id, fetch_attempt_id=rows[-1].id, fetched_at=rows[-1].started_at,
            body_hash=hashlib.sha256(res.content).hexdigest(), body_text=res.text(),
        ))
    return rows


def record_robots_block(session: Session, outlet_id: int, kind: str, url: str, vantage: str,
                        *, article_id: int | None = None) -> FetchAttempt:
    """A fetch we declined because robots.txt disallows it. Recorded so the gap is visible."""
    row = FetchAttempt(outlet_id=outlet_id, article_id=article_id, kind=kind, url=url, vantage=vantage,
                       started_at=utcnow(), attempt=1, outcome=str(Outcome.ROBOTS_BLOCKED))
    session.add(row)
    session.flush()
    return row
