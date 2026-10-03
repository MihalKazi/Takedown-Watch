"""`tw export`: write the open dataset to data/v1/. The public site is built from exactly these files.

Coverage and operational figures only (CLAUDE.md, M1 public stage). No events, no per-article data,
and no per-outlet figures: outlets are published as a plain monitored list, and every figure is an
aggregate over a group (all outlets, a language, a tier).

An aggregate over one outlet is that outlet's figure, so any group with fewer than MIN_GROUP_OUTLETS
outlets contributing data is published with `suppressed: true` and null figures ("small_group").
Suppression is also complementary: if a published group minus any set of disjoint published
subgroups would leave a residual with fewer than MIN_GROUP_OUTLETS contributing outlets, one of the
subgroups is withheld as well ("complementary"), so no figure can be recovered by subtraction.

Each file carries `schema_version`. The pydantic models below validate before anything is written;
web/src/schemas/ holds the Zod mirror the site validates against. Change both together and bump
SCHEMA_VERSION (major for breaking changes).
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, distinct, func, select

from tw import __version__
from tw.config import Settings
from tw.db.models import ArchiveAttempt, Article, FetchAttempt, Listing, Outlet, Snapshot
from tw.db.session import session_scope
from tw.db.types import utcnow
from tw.extract.extractor import EXTRACTOR_VERSION
from tw.extract.normalise import NORMALISER_VERSION
from tw.stats import HEALTH_WINDOW, LOW_RATIO, MIN_BODY, _health

SCHEMA_VERSION = "1.0.0"
DATASET_DIR = "v1"
DHAKA = timezone(timedelta(hours=6))  # Bangladesh has no DST
MIN_GROUP_OUTLETS = 3

Health = Literal["ok", "degraded", "failing", "no_data"]
Language = Literal["bn", "en"]
Tier = Literal["bangla_mass", "bangla_other", "english", "online_native", "state_wire", "independent"]
DEGRADED_AT, FAILING_AT = 0.1, 0.4
TIERS: tuple[str, ...] = Tier.__args__  # type: ignore[attr-defined]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _File(_Strict):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    generated_at: datetime


class Meta(_File):
    pipeline_version: str
    extractor_version: str
    normaliser_version: str
    vantages: list[str]
    capture_window_hours: float
    min_group_outlets: int
    first_capture_at: datetime | None
    last_capture_at: datetime | None
    last_listing_fetch_at: datetime | None
    files: list[str]


class GroupCoverage(_Strict):
    group: Literal["all", "language", "tier"]
    key: str  # "all", a language code, or a tier id
    outlets_monitored: int
    # Outlets with at least one snapshot. Null when suppressed: in a small group the count itself
    # says which named outlet is not being captured.
    outlets_contributing: int | None
    suppressed: bool
    suppression_reason: Literal["small_group", "complementary"] | None
    articles_discovered: int | None
    articles_captured: int | None
    snapshots: int | None
    snapshots_archived: int | None
    capture_success_rate: float | None = Field(ge=0, le=1)
    archive_rate: float | None = Field(ge=0, le=1)


class Coverage(_File):
    outlets_monitored: int
    outlets_with_sources: int
    outlets_contributing: int
    groups: list[GroupCoverage]


class MonitoredOutlet(_Strict):
    slug: str
    name: str
    language: Language
    tier: Tier
    base_url: str


class Outlets(_File):
    outlets: list[MonitoredOutlet]


class GroupHealth(_Strict):
    group: Literal["all", "language", "tier"]
    key: str
    outlets_contributing: int | None  # null when suppressed, as in GroupCoverage
    suppressed: bool
    suppression_reason: Literal["small_group", "complementary"] | None
    status: Health | None
    sample_size: int | None
    median_body_chars: float | None
    short_bodies: int | None
    extract_errors: int | None


class ExtractionHealth(_File):
    window_snapshots: int
    short_ratio: float
    min_body_chars: int
    degraded_at: float
    failing_at: float
    groups: list[GroupHealth]


class VolumePoint(_Strict):
    date: date
    snapshots: int
    articles_first_seen: int


class CaptureVolume(_File):
    interval: Literal["day"] = "day"
    timezone: Literal["Asia/Dhaka"] = "Asia/Dhaka"
    suppressed: bool
    series: list[VolumePoint]


@dataclass
class _OutletFigures:
    """Internal only: never written."""

    slug: str
    name: str
    language: str
    tier: str
    base_url: str
    active: bool
    has_sources: bool
    discovered: int = 0
    attempted: int = 0
    captured: int = 0
    snapshots: int = 0
    archived: int = 0
    lengths: list[int] = field(default_factory=list)
    health_sample: int = 0
    short: int = 0
    errors: int = 0


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def _status(sample: int, short: int, errors: int) -> Health:
    if sample == 0:
        return "no_data"
    bad = (short + errors) / sample
    return "ok" if bad < DEGRADED_AT else "degraded" if bad < FAILING_AT else "failing"


def _utc(dt: datetime | None) -> datetime | None:
    return dt.astimezone(UTC) if dt else None


def _collect(s) -> list[_OutletFigures]:
    out = []
    for o in s.scalars(select(Outlet).where(Outlet.active.is_(True)).order_by(Outlet.slug)):
        live = select(Article.id).where(Article.outlet_id == o.id, Article.merged_into_id.is_(None))
        snaps = select(Snapshot.id).where(Snapshot.article_id.in_(live))
        f = _OutletFigures(o.slug, o.name, o.language, o.tier, o.base_url, o.active, bool(o.rss_urls or o.sitemap_urls))
        f.discovered = s.scalar(select(func.count()).select_from(live.subquery())) or 0
        f.attempted = s.scalar(select(func.count(distinct(FetchAttempt.article_id))).where(
            FetchAttempt.article_id.in_(live), FetchAttempt.kind == "article")) or 0
        f.captured = s.scalar(select(func.count(distinct(Snapshot.article_id))).where(Snapshot.article_id.in_(live))) or 0
        f.snapshots = s.scalar(select(func.count()).select_from(snaps.subquery())) or 0
        f.archived = s.scalar(select(func.count(distinct(ArchiveAttempt.snapshot_id))).where(
            ArchiveAttempt.snapshot_id.in_(snaps), ArchiveAttempt.outcome == "ok")) or 0
        recent = s.execute(select(Snapshot.body_length, Snapshot.extra_meta).where(Snapshot.article_id.in_(live))
                           .order_by(Snapshot.fetched_at.desc()).limit(HEALTH_WINDOW)).all()
        # Short bodies are judged against each outlet's own median, then pooled.
        _med, f.short, _long, _empty, f.errors = _health([(n, bool((m or {}).get("extract_error"))) for n, m in recent])
        f.lengths = [n for n, _ in recent]
        f.health_sample = len(recent)
        out.append(f)
    return out


def _groups(figs: list[_OutletFigures]) -> list[tuple[str, str, list[_OutletFigures]]]:
    groups = [("all", "all", figs)]
    groups += [("language", lang, [f for f in figs if f.language == lang]) for lang in ("bn", "en")]
    groups += [("tier", t, [f for f in figs if f.tier == t]) for t in TIERS]
    return groups


Reason = Literal["small_group", "complementary"]
GroupDef = tuple[str, str, list[_OutletFigures]]


def _contributing(fs) -> int:
    return sum(1 for f in fs if f.snapshots > 0)


def suppression_plan(groups: list[GroupDef], k: int = MIN_GROUP_OUTLETS) -> dict[tuple[str, str], Reason]:
    """Which groups to withhold, and why.

    1. small_group: fewer than k contributing outlets.
    2. complementary: repeat until stable. For each published group A and each family F of pairwise
       disjoint published proper subgroups of A, the residual A minus the union of F is derivable by
       subtraction; if it holds 1..k-1 contributing outlets (or is a non-empty set of fewer than k
       outlets with none contributing), withhold the member of F with the fewest contributing outlets.
       The "all" group is never withheld this way.
    """
    sets = {(g, key): frozenset(f.slug for f in fs) for g, key, fs in groups}
    contrib = {f.slug for _, _, fs in groups for f in fs if f.snapshots > 0}
    plan: dict[tuple[str, str], Reason] = {
        (g, key): "small_group" for g, key, fs in groups if _contributing(fs) < k
    }

    def leaks(residual: frozenset[str]) -> bool:
        if not residual:
            return False
        c = len(residual & contrib)
        return 0 < c < k or (c == 0 and len(residual) < k)

    changed = True
    while changed:
        changed = False
        published = [gk for gk in sets if gk not in plan]
        for a in published:
            subs = [b for b in published if b != a and sets[b] < sets[a]]
            for mask in range(1, 1 << len(subs)):
                fam = [subs[i] for i in range(len(subs)) if mask >> i & 1]
                union: frozenset[str] = frozenset()
                disjoint = True
                for b in fam:
                    if union & sets[b]:
                        disjoint = False
                        break
                    union |= sets[b]
                if not disjoint or not leaks(sets[a] - union):
                    continue
                victim = min((b for b in fam if b[0] != "all"),
                             key=lambda b: (len(sets[b] & contrib), b), default=None)
                if victim is not None:
                    plan[victim] = "complementary"
                    changed = True
                    break
            if changed:
                break
    return plan


def _coverage_row(group: str, key: str, fs: list[_OutletFigures], reason: Reason | None) -> GroupCoverage:
    suppressed = reason is not None
    base = dict(group=group, key=key, outlets_monitored=len(fs),
                outlets_contributing=None if suppressed else _contributing(fs), suppressed=suppressed,
                suppression_reason=reason)
    if suppressed:
        return GroupCoverage(**base, articles_discovered=None, articles_captured=None, snapshots=None,
                             snapshots_archived=None, capture_success_rate=None, archive_rate=None)
    att, cap = sum(f.attempted for f in fs), sum(f.captured for f in fs)
    snaps, arch = sum(f.snapshots for f in fs), sum(f.archived for f in fs)
    return GroupCoverage(**base, articles_discovered=sum(f.discovered for f in fs), articles_captured=cap,
                         snapshots=snaps, snapshots_archived=arch, capture_success_rate=_rate(cap, att),
                         archive_rate=_rate(arch, snaps))


def _health_row(group: str, key: str, fs: list[_OutletFigures], reason: Reason | None) -> GroupHealth:
    if reason is not None:
        return GroupHealth(group=group, key=key, outlets_contributing=None, suppressed=True,
                           suppression_reason=reason, status=None, sample_size=None, median_body_chars=None,
                           short_bodies=None, extract_errors=None)
    contributing = [f for f in fs if f.snapshots > 0]
    sample = sum(f.health_sample for f in contributing)
    short = sum(f.short for f in contributing)
    errors = sum(f.errors for f in contributing)
    lengths = [n for f in contributing for n in f.lengths]
    return GroupHealth(group=group, key=key, outlets_contributing=len(contributing), suppressed=False,
                       suppression_reason=None, status=_status(sample, short, errors), sample_size=sample,
                       median_body_chars=statistics.median(lengths) if lengths else None,
                       short_bodies=short, extract_errors=errors)


def build(engine: Engine, settings: Settings) -> dict[str, BaseModel]:
    now = utcnow()
    with session_scope(engine) as s:
        figs = _collect(s)

        # Same population as the group figures: live (unmerged) articles of active outlets.
        live = (select(Article.id).join(Outlet, Article.outlet_id == Outlet.id)
                .where(Outlet.active.is_(True), Article.merged_into_id.is_(None)))
        by_day: dict[date, list[int]] = {}
        for (fetched_at,) in s.execute(select(Snapshot.fetched_at).where(Snapshot.article_id.in_(live))):
            by_day.setdefault(fetched_at.astimezone(DHAKA).date(), [0, 0])[0] += 1
        for (first_seen,) in s.execute(select(Article.first_seen).where(Article.id.in_(live))):
            by_day.setdefault(first_seen.astimezone(DHAKA).date(), [0, 0])[1] += 1

        first_cap, last_cap = s.execute(select(func.min(Snapshot.fetched_at), func.max(Snapshot.fetched_at))).one()
        last_listing = s.scalar(select(func.max(Listing.fetched_at)))
        vantages = sorted(v for (v,) in s.execute(select(distinct(Snapshot.vantage))))

    contributing = sum(1 for f in figs if f.snapshots > 0)
    volume_suppressed = contributing < MIN_GROUP_OUTLETS
    series: list[VolumePoint] = []
    if by_day and not volume_suppressed:
        day, end = min(by_day), max(by_day)
        while day <= end:
            snaps, first = by_day.get(day, [0, 0])
            series.append(VolumePoint(date=day, snapshots=snaps, articles_first_seen=first))
            day += timedelta(days=1)

    groups = _groups(figs)
    plan = suppression_plan(groups)
    rows = [(g, key, fs, plan.get((g, key))) for g, key, fs in groups]
    files: dict[str, BaseModel] = {
        "coverage.json": Coverage(
            generated_at=now, outlets_monitored=len(figs), outlets_with_sources=sum(f.has_sources for f in figs),
            outlets_contributing=contributing, groups=[_coverage_row(*r) for r in rows],
        ),
        "outlets.json": Outlets(generated_at=now, outlets=[
            MonitoredOutlet(slug=f.slug, name=f.name, language=f.language, tier=f.tier, base_url=f.base_url)
            for f in figs
        ]),
        "extraction-health.json": ExtractionHealth(
            generated_at=now, window_snapshots=HEALTH_WINDOW, short_ratio=LOW_RATIO, min_body_chars=MIN_BODY,
            degraded_at=DEGRADED_AT, failing_at=FAILING_AT, groups=[_health_row(*r) for r in rows],
        ),
        "capture-volume.json": CaptureVolume(generated_at=now, suppressed=volume_suppressed, series=series),
    }
    files["meta.json"] = Meta(
        generated_at=now, pipeline_version=__version__, extractor_version=EXTRACTOR_VERSION,
        normaliser_version=NORMALISER_VERSION, vantages=vantages,
        capture_window_hours=settings.capture_window_hours, min_group_outlets=MIN_GROUP_OUTLETS,
        first_capture_at=_utc(first_cap), last_capture_at=_utc(last_cap), last_listing_fetch_at=_utc(last_listing),
        files=sorted([*files, "meta.json"]),
    )
    return files


def write(files: dict[str, BaseModel], data_dir: Path) -> Path:
    out = data_dir / DATASET_DIR
    out.mkdir(parents=True, exist_ok=True)
    for name, model in files.items():
        text = json.dumps(model.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        tmp = out / f"{name}.tmp"
        tmp.write_text(text, encoding="utf-8", newline="\n")
        tmp.replace(out / name)
    return out
