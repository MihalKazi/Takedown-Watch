"""M3 human analysis layer. Writes to `annotation` only -- never adds a reason/motive/cause
column to `event` (invariant 1). Every annotation is signed by a named author and timestamped.

No web form yet: for a one-developer team this is a CLI step, same DB-table-not-Redis philosophy
as the rest of the pipeline. A review UI can be layered on later without changing this contract.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from tw.db.models import Annotation, Event
from tw.db.types import utcnow

REVIEW_STATES = ("draft", "published", "retracted")
REVIEW_DECISIONS = ("confirmed", "dismissed", "escalated")


def add_annotation(session: Session, event_id: int, author: str, body: str, *,
                   review_state: str = "draft") -> Annotation:
    if review_state not in REVIEW_STATES:
        raise ValueError(f"review_state must be one of {REVIEW_STATES}, got {review_state!r}")
    if session.get(Event, event_id) is None:
        raise ValueError(f"no event with id {event_id}")
    ann = Annotation(event_id=event_id, author=author, written_at=utcnow(), body=body, review_state=review_state)
    session.add(ann)
    session.flush()
    return ann


def set_review(session: Session, event_id: int, reviewed_by: str, decision: str) -> Event:
    """Workflow state on the event itself: who looked at it and what they decided. This is not
    interpretation (no "why") -- the reasoning, if any, belongs in an Annotation."""
    if decision not in REVIEW_DECISIONS:
        raise ValueError(f"decision must be one of {REVIEW_DECISIONS}, got {decision!r}")
    ev = session.get(Event, event_id)
    if ev is None:
        raise ValueError(f"no event with id {event_id}")
    ev.reviewed_by = reviewed_by
    ev.reviewed_at = utcnow()
    ev.review_decision = decision
    session.flush()
    return ev


def list_annotations(session: Session, event_id: int) -> list[Annotation]:
    return list(session.scalars(
        select(Annotation).where(Annotation.event_id == event_id).order_by(Annotation.written_at)
    ))
