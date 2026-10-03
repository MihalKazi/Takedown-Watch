"""Coverage and health figures. Computed at read time from the raw record; nothing here is stored.

Extraction health: each snapshot's body length against its outlet's rolling median. A redesign that
breaks extraction shows up as a run of anomalously short bodies here, before it can show up as a
phantom diff wave in M2.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field

from sqlalchemy import Engine, case, func, select

from tw.db.models import ArchiveAttempt, Article, FetchAttempt, Job, Outlet, Snapshot
from tw.db.session import session_scope
from tw.db.types import utcnow

HEALTH_WINDOW = 50  # snapshots in the rolling median
LOW_RATIO = 0.3
HIGH_RATIO = 3.0
MIN_BODY = 200  # characters; below this a news article body is almost certainly not extracted


@dataclass
class OutletStats:
    slug: str
    name: str
    language: str
    active: bool
    has_sources: bool
    limitations: list[str]
    articles: int = 0
    captured: int = 0
    snapshots: int = 0
    article_fetches: dict[str, int] = field(default_factory=dict)
    archived_ok: int = 0
    archive_pending: int = 0
    archive_failed_jobs: int = 0
    median_body_length: float | None = None
    health_sample: int = 0
    anomalous_short: int = 0
    anomalous_long: int = 0
    empty_bodies: int = 0
    extract_errors: int = 0
    last_capture: str | None = None

    @property
    def health(self) -> str:
        if self.health_sample == 0:
            return "no_data"
        bad = (self.anomalous_short + self.extract_errors) / self.health_sample  # short includes empty
        return "ok" if bad < 0.1 else "degraded" if bad < 0.4 else "failing"


def _health(bodies: list[tuple[int, bool]]) -> tuple[float | None, int, int, int, int]:
    """bodies: newest first, (length, had_extract_error)."""
    sample = bodies[:HEALTH_WINDOW]
    lengths = [n for n, _ in sample]
    if not lengths:
        return None, 0, 0, 0, 0
    med = statistics.median(lengths)
    short = sum(1 for n in lengths if n < max(MIN_BODY, LOW_RATIO * med))
    long_ = sum(1 for n in lengths if med and n > HIGH_RATIO * med)
    empty = sum(1 for n in lengths if n == 0)
    errors = sum(1 for _, e in sample if e)
    return med, short, long_, empty, errors


def collect(engine: Engine) -> list[OutletStats]:
    out: list[OutletStats] = []
    with session_scope(engine) as s:
        for o in s.scalars(select(Outlet).order_by(Outlet.slug)):
            st = OutletStats(o.slug, o.name, o.language, o.active, bool(o.rss_urls or o.sitemap_urls),
                             list(o.limitations))
            art_ids = select(Article.id).where(Article.outlet_id == o.id)
            st.articles, st.captured = s.execute(
                select(func.count(Article.id), func.sum(case((Article.status == "captured", 1), else_=0)))
                .where(Article.outlet_id == o.id, Article.merged_into_id.is_(None))
            ).one()
            st.captured = st.captured or 0
            st.snapshots = s.scalar(select(func.count(Snapshot.id)).where(Snapshot.article_id.in_(art_ids))) or 0
            # Final attempt per logical fetch is what matters; count all attempts by outcome.
            st.article_fetches = dict(s.execute(
                select(FetchAttempt.outcome, func.count()).where(FetchAttempt.outlet_id == o.id,
                                                                 FetchAttempt.kind == "article")
                .group_by(FetchAttempt.outcome)).all())
            snap_ids = select(Snapshot.id).where(Snapshot.article_id.in_(art_ids))
            st.archived_ok = s.scalar(select(func.count(func.distinct(ArchiveAttempt.snapshot_id))).where(
                ArchiveAttempt.snapshot_id.in_(snap_ids), ArchiveAttempt.outcome == "ok")) or 0
            st.archive_pending = s.scalar(select(func.count(Job.id)).where(
                Job.kind == "archive", Job.status.in_(("pending", "running")), Job.ref_id.in_(snap_ids))) or 0
            st.archive_failed_jobs = s.scalar(select(func.count(Job.id)).where(
                Job.kind == "archive", Job.status == "failed", Job.ref_id.in_(snap_ids))) or 0
            rows = s.execute(
                select(Snapshot.body_length, Snapshot.extra_meta, Snapshot.fetched_at)
                .where(Snapshot.article_id.in_(art_ids)).order_by(Snapshot.fetched_at.desc())
                .limit(HEALTH_WINDOW)).all()
            bodies = [(n, bool((meta or {}).get("extract_error"))) for n, meta, _ in rows]
            (st.median_body_length, st.anomalous_short, st.anomalous_long, st.empty_bodies,
             st.extract_errors) = _health(bodies)
            st.health_sample = len(bodies)
            if rows:
                st.last_capture = rows[0][2].isoformat()
            out.append(st)
    return out


def totals(stats: list[OutletStats]) -> dict:
    snaps = sum(x.snapshots for x in stats)
    arch = sum(x.archived_ok for x in stats)
    return {
        "outlets_configured": len(stats),
        "outlets_with_sources": sum(x.has_sources for x in stats),
        "articles": sum(x.articles for x in stats),
        "captured": sum(x.captured for x in stats),
        "snapshots": snaps,
        "archived_ok": arch,
        "archive_rate": round(arch / snaps, 4) if snaps else None,
        "generated_at": utcnow().isoformat(),
    }


def render(stats: list[OutletStats]) -> str:
    hdr = (f"{'outlet':17} {'lang':4} {'articles':>8} {'captured':>8} {'snaps':>6} {'archived':>8} "
           f"{'arch%':>6} {'q':>4} {'med_len':>8} {'health':9} {'short':>5} {'err':>4}  fetch outcomes")
    lines = [hdr, "-" * len(hdr)]
    for x in stats:
        rate = f"{x.archived_ok / x.snapshots:.0%}" if x.snapshots else "-"
        med = f"{x.median_body_length:.0f}" if x.median_body_length is not None else "-"
        fetches = " ".join(f"{k}={v}" for k, v in sorted(x.article_fetches.items())) or "-"
        note = "" if x.has_sources else f"  [no sources: {','.join(x.limitations)}]"
        lines.append(f"{x.slug:17} {x.language:4} {x.articles:>8} {x.captured:>8} {x.snapshots:>6} "
                     f"{x.archived_ok:>8} {rate:>6} {x.archive_pending:>4} {med:>8} {x.health:9} "
                     f"{x.anomalous_short:>5} {x.extract_errors:>4}  {fetches}{note}")
    t = totals(stats)
    lines.append("-" * len(hdr))
    rate = f"{t['archive_rate']:.1%}" if t["archive_rate"] is not None else "-"
    lines.append(f"TOTAL  outlets={t['outlets_configured']} (with sources {t['outlets_with_sources']})  "
                 f"articles={t['articles']}  captured={t['captured']}  snapshots={t['snapshots']}  "
                 f"archived={t['archived_ok']}  archive_rate={rate}")
    return "\n".join(lines)


def as_dicts(stats: list[OutletStats]) -> list[dict]:
    return [asdict(x) | {"health": x.health} for x in stats]

