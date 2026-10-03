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

import difflib
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, select
from sqlalchemy.orm import aliased

from tw.db.models import Annotation, Article, Event, Outlet, Snapshot
from tw.db.session import session_scope
from tw.db.types import utcnow
from tw.discover.ingest import _is_non_article_path

SCHEMA_VERSION = "1.0.0"
DATASET_DIR = "internal"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InternalAnnotation(_Strict):
    author: str
    written_at: datetime
    body: str
    review_state: Literal["draft", "published", "retracted"]


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
    from_byline: str | None
    to_byline: str | None
    from_published_at: str | None
    to_published_at: str | None
    from_final_url: str | None
    to_final_url: str | None
    body_diff: str | None  # short excerpt around the first differing region, not the full body
    reviewed_by: str | None
    review_decision: str | None
    published: bool
    annotations: list[InternalAnnotation]


MAX_DIFF_SIDE_CHARS = 400  # hard cap per side: a reviewer glance, not a full-text dump


def _body_diff_snippet(before: str | None, after: str | None, *, context: int = 60) -> str | None:
    """A short "- old / + new" excerpt around the first differing region, not the whole body --
    this is for a reviewer to see at a glance what moved, not to republish the article."""
    before, after = before or "", after or ""
    if before == after:
        return None
    matcher = difflib.SequenceMatcher(a=before, b=after, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        lo_a, lo_b = max(0, i1 - context), max(0, j1 - context)
        old = before[lo_a:i2 + context][:MAX_DIFF_SIDE_CHARS]
        new = after[lo_b:j2 + context][:MAX_DIFF_SIDE_CHARS]
        prefix = "…" if lo_a > 0 else ""
        suffix = "…" if i2 + context < len(before) else ""
        return f"- {prefix}{old}{suffix}\n+ {prefix if lo_b > 0 else ''}{new}{'…' if j2 + context < len(after) else ''}"
    return None  # equal under the matcher despite before != after (shouldn't happen)


class InternalEvents(_Strict):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    generated_at: datetime
    events: list[InternalEvent]


def build(engine: Engine, *, limit: int = 2000) -> InternalEvents:
    now = utcnow()
    from_snap = aliased(Snapshot)
    to_snap = aliased(Snapshot)
    with session_scope(engine) as s:
        # Triage ordering (M3): severity is a sort key, never a filter -- every row below is
        # still written regardless of this order. Ties broken by most-recently detected.
        #
        # Fetch wider than `limit` and filter out non-article URLs (tag/category/author listing
        # pages, see tw.discover.ingest._is_non_article_path) in Python: these rows exist in the
        # DB from before that filter was added (non-destructive -- they're not deleted there,
        # only kept out of this view), and a listing page's content changes every crawl, so they
        # would otherwise dominate the top of a severity-sorted dashboard with noise.
        candidates = s.execute(
            select(Event, Article, Outlet, from_snap, to_snap)
            .join(Article, Event.article_id == Article.id)
            .join(Outlet, Article.outlet_id == Outlet.id)
            .outerjoin(from_snap, Event.from_snapshot_id == from_snap.id)
            .outerjoin(to_snap, Event.to_snapshot_id == to_snap.id)
            .order_by(Event.severity.desc(), Event.detected_at.desc())
            .limit(limit * 3)
        ).all()
        rows = [r for r in candidates if not _is_non_article_path(r[1].canonical_url)][:limit]
        event_ids = [ev.id for ev, *_ in rows]
        anns_by_event: dict[int, list[Annotation]] = {}
        if event_ids:
            for ann in s.scalars(
                select(Annotation).where(Annotation.event_id.in_(event_ids)).order_by(Annotation.written_at)
            ):
                anns_by_event.setdefault(ann.event_id, []).append(ann)
        events = [
            InternalEvent(
                id=ev.id, type=ev.type, detected_at=ev.detected_at, confidence=ev.confidence,
                severity=ev.severity, article_age_at_change=ev.article_age_at_change,
                outlet_slug=o.slug, outlet_name=o.name, article_url=a.canonical_url,
                from_headline=fs.headline if fs else None, to_headline=ts.headline if ts else None,
                from_byline=fs.byline if fs else None, to_byline=ts.byline if ts else None,
                from_published_at=fs.published_at if fs else None, to_published_at=ts.published_at if ts else None,
                from_final_url=fs.final_url if fs else None, to_final_url=ts.final_url if ts else None,
                body_diff=_body_diff_snippet(fs.body_text if fs else None, ts.body_text if ts else None),
                reviewed_by=ev.reviewed_by, review_decision=ev.review_decision, published=ev.published,
                annotations=[
                    InternalAnnotation(author=an.author, written_at=an.written_at, body=an.body,
                                       review_state=an.review_state)
                    for an in anns_by_event.get(ev.id, [])
                ],
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
