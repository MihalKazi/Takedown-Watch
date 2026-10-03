"""M2 diff engine: compares two snapshots (or a snapshot + a run of gone fetch_attempts) and emits
`Event` rows. See CLAUDE.md "Event taxonomy" and invariants 1, 3, 4.

Writes only what was mechanically observed. No reason/motive/cause anywhere here -- that is
`annotation`'s job (M3), signed by a human. Every detected change is written, however small;
`severity` only orders human review, it never gates what gets stored (invariant: capture
everything, filter at read time).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from tw.db.models import Article, Event, FetchAttempt, Snapshot
from tw.db.types import utcnow
from tw.fetch.classify import Outcome

# invariant 4: no GONE from one failed fetch. Needs N consecutive failures across >= M hours.
GONE_MIN_CONSECUTIVE_FAILURES = 3
GONE_MIN_SPAN_HOURS = 6.0

# taxonomy, CLAUDE.md "Event taxonomy"
HEADLINE_CHANGED = "HEADLINE_CHANGED"
BODY_CHANGED = "BODY_CHANGED"
BYLINE_REMOVED = "BYLINE_REMOVED"
BYLINE_CHANGED = "BYLINE_CHANGED"
DATE_CHANGED = "DATE_CHANGED"
REDIRECTED = "REDIRECTED"
GONE_404 = "GONE_404"
GONE_410 = "GONE_410"
GONE_SOFT = "GONE_SOFT"
ROBOTS_BLOCKED = "ROBOTS_BLOCKED"
RESTORED = "RESTORED"
DEINDEXED = "DEINDEXED"
UNPUBLISHED = "UNPUBLISHED"
# Not generated here (needs a second vantage point): GEO_BLOCKED.
# FIRST_SEEN is implicit at article creation, not a diff outcome.


# M3 severity: a sort key only (invariant: capture everything, filter at read time -- severity
# never gates what gets written). article_age_at_change is the primary multiplier, per CLAUDE.md
# "Core design principle: age at change" -- editing a 2-hour-old article is routine; editing a
# 6-month-old one is anomalous. Age bands reuse the same boundaries as the recheck backoff
# schedule, since that's already the project's definition of "how old is old".
BASE_SEVERITY: dict[str, int] = {
    BYLINE_REMOVED: 9,  # CLAUDE.md flags this "(high significance)" explicitly
    GONE_404: 8,
    GONE_410: 8,
    GONE_SOFT: 8,
    ROBOTS_BLOCKED: 6,
    BODY_CHANGED: 5,
    DEINDEXED: 5,
    UNPUBLISHED: 4,
    BYLINE_CHANGED: 4,
    HEADLINE_CHANGED: 3,
    REDIRECTED: 3,
    DATE_CHANGED: 2,
    RESTORED: 1,  # good news, but still worth a human glance
}

_AGE_BAND_HOURS = (1, 6, 24, 72, 168, 720, 2160, 8760)  # 1h,6h,24h,3d,7d,30d,90d,365d


def _age_multiplier(age_hours: float) -> int:
    for i, bound in enumerate(_AGE_BAND_HOURS, start=1):
        if age_hours <= bound:
            return i
    return len(_AGE_BAND_HOURS) + 1


def compute_severity(event_type: str, age_hours: float) -> int:
    return BASE_SEVERITY.get(event_type, 3) * _age_multiplier(age_hours)


@dataclass
class EventDraft:
    type: str
    confidence: str  # confirmed | probable | unverified
    from_snapshot_id: int | None = None
    to_snapshot_id: int | None = None
    fetch_attempt_id: int | None = None


def _age_hours(first_seen: datetime, at: datetime) -> float:
    return max((at - first_seen).total_seconds() / 3600.0, 0.0)


def diff_snapshots(prev: Snapshot, new: Snapshot) -> list[EventDraft]:
    """Compare a newly-fetched snapshot against the most recent prior one for the same article.
    Every real difference becomes its own event; a page can emit several at once (e.g. headline
    AND byline changed together)."""
    drafts: list[EventDraft] = []

    if prev.headline_hash != new.headline_hash:
        drafts.append(EventDraft(HEADLINE_CHANGED, "confirmed", prev.id, new.id))

    if prev.byline_hash != new.byline_hash:
        prev_empty = not (prev.byline or "").strip()
        new_empty = not (new.byline or "").strip()
        if new_empty and not prev_empty:
            drafts.append(EventDraft(BYLINE_REMOVED, "confirmed", prev.id, new.id))
        else:
            drafts.append(EventDraft(BYLINE_CHANGED, "confirmed", prev.id, new.id))

    if prev.body_hash != new.body_hash:
        drafts.append(EventDraft(BODY_CHANGED, "confirmed", prev.id, new.id))

    if (prev.published_at or None) != (new.published_at or None):
        drafts.append(EventDraft(DATE_CHANGED, "confirmed", prev.id, new.id))

    if prev.final_url != new.final_url:
        drafts.append(EventDraft(REDIRECTED, "confirmed", prev.id, new.id))

    return drafts


def restored_event(prev_gone_event: Event, new_snapshot: Snapshot) -> EventDraft:
    """A previously-GONE article's URL now resolves again with a real snapshot."""
    return EventDraft(RESTORED, "confirmed", prev_gone_event.to_snapshot_id, new_snapshot.id)


def check_gone(session: Session, article: Article, *, now: datetime | None = None) -> EventDraft | None:
    """Look at the article's most recent `fetch_attempt` rows (article kind) since its last
    snapshot. If the last N are all terminal failures of the same gone-shaped kind, spanning
    >= M hours, emit the matching GONE_* draft. Otherwise None -- a lone bad response is never
    enough (invariant 4)."""
    now = now or utcnow()
    last_snap_at = session.scalar(
        select(Snapshot.fetched_at).where(Snapshot.article_id == article.id)
        .order_by(Snapshot.fetched_at.desc()).limit(1)
    )
    q = (
        select(FetchAttempt)
        .where(FetchAttempt.article_id == article.id, FetchAttempt.kind == "article")
        .order_by(FetchAttempt.started_at.desc())
        .limit(GONE_MIN_CONSECUTIVE_FAILURES)
    )
    if last_snap_at is not None:
        q = q.where(FetchAttempt.started_at > last_snap_at)
    recent = list(session.scalars(q))
    if len(recent) < GONE_MIN_CONSECUTIVE_FAILURES:
        return None

    kinds = {_gone_kind(a) for a in recent}
    if len(kinds) != 1 or None in kinds:
        return None  # mixed or non-gone-shaped failures: not enough signal yet

    span_hours = (recent[0].started_at - recent[-1].started_at).total_seconds() / 3600.0
    if span_hours < GONE_MIN_SPAN_HOURS:
        return None

    gone_type = kinds.pop()
    last_attempt = recent[0]
    confidence = "confirmed" if gone_type in (GONE_404, GONE_410) else "probable"
    return EventDraft(gone_type, confidence, fetch_attempt_id=last_attempt.id)


def _gone_kind(attempt: FetchAttempt) -> str | None:
    if attempt.outcome == Outcome.ROBOTS_BLOCKED:
        return ROBOTS_BLOCKED
    if attempt.outcome != Outcome.HTTP_ERROR:
        return None  # timeouts, CF challenges, rate limits etc are transient, not gone-shaped
    if attempt.http_status == 404:
        return GONE_404
    if attempt.http_status == 410:
        return GONE_410
    return None


def diff_listing_presence(prev_rss: set[str], prev_sitemap: set[str], cur_rss: set[str],
                          cur_sitemap: set[str], url_hashes: set[str]) -> EventDraft | None:
    """Compare where an article's URL (any known alias hash) appeared in the immediately prior
    listing fetch vs the current one. Transitions only: an article that was already absent last
    run produces nothing this run (invariant: capture everything, but this models a one-time
    transition, not a standing state re-announced every crawl). Confidence is "unverified" --
    a feed can drop an entry for reasons unrelated to editorial intent (pagination limits, feed
    size caps), so this is weaker evidence than a direct content diff or a repeated fetch
    failure."""
    was_listed = bool(url_hashes & (prev_rss | prev_sitemap))
    if not was_listed:
        return None
    now_rss = bool(url_hashes & cur_rss)
    now_sitemap = bool(url_hashes & cur_sitemap)
    if not now_rss and not now_sitemap:
        return EventDraft(DEINDEXED, "unverified")
    if bool(url_hashes & prev_sitemap) and not now_sitemap and now_rss:
        return EventDraft(UNPUBLISHED, "unverified")
    return None


def write_event(session: Session, article: Article, draft: EventDraft, *, detected_at: datetime | None = None,
                severity: int | None = None) -> Event:
    detected_at = detected_at or utcnow()
    age = _age_hours(article.first_seen, detected_at)
    ev = Event(
        article_id=article.id, type=draft.type, detected_at=detected_at,
        from_snapshot_id=draft.from_snapshot_id, to_snapshot_id=draft.to_snapshot_id,
        fetch_attempt_id=draft.fetch_attempt_id,
        severity=severity if severity is not None else compute_severity(draft.type, age),
        confidence=draft.confidence, article_age_at_change=age, created_at=detected_at,
    )
    session.add(ev)
    session.flush()
    return ev
