"""M1 schema. See docs/m1-proposal.md.

Machine-observed facts only (CLAUDE.md invariant 1): no reason/motive/cause columns anywhere.
`snapshot` is append-only (invariant 6): rows are inserted, never updated or deleted.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, MetaData, String, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from tw.db.types import UTCDateTime

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {datetime: UTCDateTime(), dict: JSON, list: JSON}


class Outlet(Base):
    __tablename__ = "outlet"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(8))
    base_url: Mapped[str] = mapped_column(Text)
    cms: Mapped[str | None] = mapped_column(Text)
    rss_urls: Mapped[list] = mapped_column(default=list)  # JSON, not PG ARRAY: SQLite-safe
    sitemap_urls: Mapped[list] = mapped_column(default=list)
    tier: Mapped[str] = mapped_column(String(32))
    rate_limit_seconds: Mapped[float] = mapped_column(default=2.0)
    needs_js: Mapped[bool] = mapped_column(default=False)
    retain_html: Mapped[str] = mapped_column(String(16), default="always")  # always | on_change
    active: Mapped[bool] = mapped_column(default=True)
    limitations: Mapped[list] = mapped_column(default=list)


class Article(Base):
    __tablename__ = "article"

    id: Mapped[int] = mapped_column(primary_key=True)
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlet.id"), index=True)
    canonical_url: Mapped[str] = mapped_column(Text)
    url_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256(canonical_url)
    first_seen: Mapped[datetime]
    last_seen: Mapped[datetime]  # last seen in any listing
    status: Mapped[str] = mapped_column(String(16), default="discovered")  # discovered | captured
    merged_into_id: Mapped[int | None] = mapped_column(ForeignKey("article.id"))


class ArticleUrl(Base):
    """Every URL form seen for an article: feed link, sitemap loc, rel=canonical, redirect target."""

    __tablename__ = "article_url"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("article.id"), index=True)
    url: Mapped[str] = mapped_column(Text)
    url_hash: Mapped[str] = mapped_column(String(64), unique=True)
    source: Mapped[str] = mapped_column(String(16))  # rss | sitemap | canonical | redirect
    first_seen: Mapped[datetime]


class FetchAttempt(Base):
    """One row per HTTP attempt of any kind, retries included. Failures live here, not in snapshot."""

    __tablename__ = "fetch_attempt"

    id: Mapped[int] = mapped_column(primary_key=True)
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlet.id"), index=True)
    article_id: Mapped[int | None] = mapped_column(ForeignKey("article.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # article | rss | sitemap | robots | probe
    url: Mapped[str] = mapped_column(Text)
    final_url: Mapped[str | None] = mapped_column(Text)
    vantage: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(index=True)
    elapsed_ms: Mapped[int | None]
    attempt: Mapped[int] = mapped_column(default=1)  # retry number within one logical fetch
    outcome: Mapped[str] = mapped_column(String(16))  # see tw.fetch.classify.Outcome
    http_status: Mapped[int | None]
    content_type: Mapped[str | None] = mapped_column(Text)
    response_bytes: Mapped[int | None]
    error: Mapped[str | None] = mapped_column(Text)


class Snapshot(Base):
    """Append-only. Never updated. Only for 2xx HTML article responses."""

    __tablename__ = "snapshot"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("article.id"), index=True)
    fetch_attempt_id: Mapped[int] = mapped_column(ForeignKey("fetch_attempt.id"), unique=True)
    fetched_at: Mapped[datetime] = mapped_column(index=True)
    http_status: Mapped[int]
    vantage: Mapped[str] = mapped_column(String(32))
    final_url: Mapped[str] = mapped_column(Text)
    canonical_link: Mapped[str | None] = mapped_column(Text)  # <link rel=canonical> as found
    headline: Mapped[str | None] = mapped_column(Text)  # raw as extracted
    byline: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[str | None] = mapped_column(Text)  # raw string, no lossy parse
    modified_at: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)  # raw, NOT normalised
    body_length: Mapped[int]
    body_hash: Mapped[str] = mapped_column(String(64))  # sha256(normalise(body))
    headline_hash: Mapped[str] = mapped_column(String(64))
    byline_hash: Mapped[str] = mapped_column(String(64))
    extra_meta: Mapped[dict] = mapped_column(default=dict)  # full extractor metadata dump
    raw_html_ref: Mapped[str | None] = mapped_column(String(64))  # blob sha256
    extractor_version: Mapped[str] = mapped_column(String(32))
    normaliser_version: Mapped[str] = mapped_column(String(32))


class ArchiveAttempt(Base):
    __tablename__ = "archive_attempt"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshot.id"), index=True)
    requested_at: Mapped[datetime]
    completed_at: Mapped[datetime | None]
    mode: Mapped[str] = mapped_column(String(8))  # auth | anon
    outcome: Mapped[str] = mapped_column(String(16))  # ok | error | rate_limited | timeout
    spn_job_id: Mapped[str | None] = mapped_column(Text)
    archive_url: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)


class Listing(Base):
    """One fetched RSS/sitemap document. Full URL set kept for M2 unpublish diffing."""

    __tablename__ = "listing"

    id: Mapped[int] = mapped_column(primary_key=True)
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlet.id"), index=True)
    fetch_attempt_id: Mapped[int] = mapped_column(ForeignKey("fetch_attempt.id"), unique=True)
    kind: Mapped[str] = mapped_column(String(16))  # rss | atom | sitemap | sitemap_index | news_sitemap
    source_url: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(index=True)
    entry_count: Mapped[int]
    raw_ref: Mapped[str] = mapped_column(String(64))  # blob of raw XML


class ListingEntry(Base):
    __tablename__ = "listing_entry"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listing.id"), index=True)
    url: Mapped[str] = mapped_column(Text)
    url_hash: Mapped[str] = mapped_column(String(64), index=True)
    lastmod: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)


class RobotsSnapshot(Base):
    __tablename__ = "robots_snapshot"

    id: Mapped[int] = mapped_column(primary_key=True)
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlet.id"), index=True)
    fetch_attempt_id: Mapped[int] = mapped_column(ForeignKey("fetch_attempt.id"), unique=True)
    fetched_at: Mapped[datetime]
    body_hash: Mapped[str] = mapped_column(String(64))
    body_text: Mapped[str] = mapped_column(Text)


class Job(Base):
    """DB-backed queue. Kinds in M1: fetch_article, archive."""

    __tablename__ = "job"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    ref_id: Mapped[int]  # article.id or snapshot.id
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | running | done | failed
    run_after: Mapped[datetime] = mapped_column(index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=5)
    locked_by: Mapped[str | None] = mapped_column(Text)
    locked_at: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime]

    __table_args__ = (
        Index(
            "uq_job_open",
            "kind",
            "ref_id",
            unique=True,
            sqlite_where=text("status IN ('pending','running')"),
            postgresql_where=text("status IN ('pending','running')"),
        ),
    )
