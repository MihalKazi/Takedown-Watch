"""`tw export-internal`: write data/internal/events.json for the authenticated M2 dashboard.

NOT the open dataset. Unlike tw.export (data/v1/*.json, public, aggregated, outlet-anonymous),
this names outlets and articles directly -- that is exactly what CLAUDE.md permits for M2-M3
("Full event dashboard, authenticated") and exactly what it forbids on the public site before
M4 ("Publish nothing about specific outlets until that policy exists").

data/internal/ must never be committed to the public git mirror, and the Astro page that reads
it must never be included if dist/ is ever pushed to that public mirror -- see
docs/m1-proposal.md / web/src/pages/internal/events.astro for the caveat.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, select
from sqlalchemy.orm import aliased

from tw.db.models import Article, Event, Outlet, Snapshot
from tw.db.session import session_scope
from tw.db.types import utcnow

SCHEMA_VERSION = "1.0.0"
DATASET_DIR = "internal"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InternalEvent(_Strict):
    id: int
    type: str
    detected_at: datetime
    confidence: Literal["confirmed", "probable", "unverified"]
    severity: int
    article_age_at_change: float
    outlet_slug: str
    outlet_name: str
    article_url: str
    from_headline: str | None
    to_headline: str | None
    reviewed_by: str | None
    review_decision: str | None
    published: bool


class InternalEvents(_Strict):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    generated_at: datetime
    events: list[InternalEvent]


def build(engine: Engine, *, limit: int = 2000) -> InternalEvents:
    now = utcnow()
    from_snap = aliased(Snapshot)
    to_snap = aliased(Snapshot)
    with session_scope(engine) as s:
        rows = s.execute(
            select(Event, Article, Outlet, from_snap, to_snap)
            .join(Article, Event.article_id == Article.id)
            .join(Outlet, Article.outlet_id == Outlet.id)
            .outerjoin(from_snap, Event.from_snapshot_id == from_snap.id)
            .outerjoin(to_snap, Event.to_snapshot_id == to_snap.id)
            .order_by(Event.detected_at.desc())
            .limit(limit)
        ).all()
        events = [
            InternalEvent(
                id=ev.id, type=ev.type, detected_at=ev.detected_at, confidence=ev.confidence,
                severity=ev.severity, article_age_at_change=ev.article_age_at_change,
                outlet_slug=o.slug, outlet_name=o.name, article_url=a.canonical_url,
                from_headline=fs.headline if fs else None, to_headline=ts.headline if ts else None,
                reviewed_by=ev.reviewed_by, review_decision=ev.review_decision, published=ev.published,
            )
            for ev, a, o, fs, ts in rows
        ]
    return InternalEvents(generated_at=now, events=events)


def write(data: InternalEvents, data_dir: Path) -> Path:
    out = data_dir / DATASET_DIR
    out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp = out / "events.json.tmp"
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(out / "events.json")
    return out
