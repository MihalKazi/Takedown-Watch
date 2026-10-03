# M1 proposal — awaiting review

Status: proposed, NOT confirmed. No code written. Git repo initialised, nothing committed.

## Open decisions (need answers before code)

1. **Site stack.** CLAUDE.md says Astro 5 + TS + Tailwind + Zod, monorepo `pipeline/ data/ web/`. kickoff-prompt.md says Jinja2 → `dist/`, no JS toolchain. CLAUDE.md edited later. Recommendation: monorepo; pipeline emits `data/v1/*.json`; Astro builds with relative asset paths so `dist/` opens from disk.
2. **`archive_url` on `snapshot` breaks invariant 6** (append-only) — SPN completes minutes/hours after capture. Recommendation: separate `archive_attempt` table keyed by `snapshot_id`; coverage gap = snapshot with no `ok` row.
3. **`check` table** (kickoff only, not in CLAUDE.md; `CHECK` is a SQL reserved word). Proposal: name it `fetch_attempt` — one row per HTTP attempt of any kind, retries included.
4. **Snapshot vs fetch.** Snapshot only for 2xx HTML documents. 404/5xx/timeout/CF challenge live in `fetch_attempt` only; M2 GONE detection reads that.
5. Dependency manager: `uv` (default).

## Module layout

```
takedown-watch/
  CLAUDE.md
  outlets.yaml                 source of truth; synced into outlet table each run
  pipeline/
    pyproject.toml             uv-managed
    alembic.ini
    migrations/
    src/tw/
      config.py                pydantic-settings
      logging.py               structlog
      blobs.py                 content-addressed raw HTML/XML store (sha256, gzip)
      db/models.py  session.py  queue.py   (SKIP LOCKED on PG; BEGIN IMMEDIATE on SQLite)
      outlets.py               yaml load/validate/sync, write-back from discover
      discover/probe.py        feed/sitemap candidate probing + verification
      discover/listings.py     RSS + sitemap/sitemap-index parsing
      discover/canon.py        tracking-param strip, normalise, rel=canonical
      fetch/ratelimit.py       per-host async gate
      fetch/client.py          httpx, UA, retry policy
      fetch/classify.py        outcome: ok / cf_challenge / rate_limited / timeout ...
      extract/extractor.py     trafilatura wrapper, EXTRACTOR_VERSION
      extract/normalise.py     NFC, whitespace/quote/dash, ZWJ/ZWNJ-preserving, NORMALISER_VERSION
      extract/hashing.py
      archive/spn.py           SPN2 auth + anon
      stats.py                 incl. rolling-median extraction health (read-time)
      export.py                → data/v1/*.json
      cli.py                   typer: discover / crawl / archive / stats / build-site
    tests/fixtures/bn/, en/    real saved article HTML
  data/v1/                     open dataset = site input
  web/                         Astro (if decision 1 confirmed)
```

## Models (SQLAlchemy 2.x)

```python
class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True), dict: JSON, list: JSON}


class Outlet(Base):
    __tablename__ = "outlet"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)   # yaml key
    name: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(8))             # "bn" | "en"
    base_url: Mapped[str] = mapped_column(Text)
    cms: Mapped[str | None] = mapped_column(Text)
    rss_urls: Mapped[list] = mapped_column(default=list)         # JSON, not PG ARRAY → SQLite-safe
    sitemap_urls: Mapped[list] = mapped_column(default=list)
    tier: Mapped[str] = mapped_column(String(32))
    rate_limit_seconds: Mapped[float] = mapped_column(default=2.0)
    needs_js: Mapped[bool] = mapped_column(default=False)
    retain_html: Mapped[str] = mapped_column(String(16), default="always")  # always | on_change
    active: Mapped[bool] = mapped_column(default=True)
    limitations: Mapped[list] = mapped_column(default=list)      # from discover: "cf_challenge", "timeout", ...


class Article(Base):
    __tablename__ = "article"
    id: Mapped[int] = mapped_column(primary_key=True)
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlet.id"), index=True)
    canonical_url: Mapped[str] = mapped_column(Text)
    url_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256(canonical_url)
    first_seen: Mapped[datetime]
    last_seen: Mapped[datetime]                                  # last seen in any listing
    status: Mapped[str] = mapped_column(String(16), default="discovered")  # discovered | captured
    merged_into_id: Mapped[int | None] = mapped_column(ForeignKey("article.id"))


class ArticleUrl(Base):
    """Every URL form seen for an article: feed link, sitemap loc, rel=canonical, redirect target."""
    __tablename__ = "article_url"
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("article.id"), index=True)
    url: Mapped[str] = mapped_column(Text)
    url_hash: Mapped[str] = mapped_column(String(64), unique=True)
    source: Mapped[str] = mapped_column(String(16))              # rss | sitemap | canonical | redirect
    first_seen: Mapped[datetime]


class FetchAttempt(Base):
    __tablename__ = "fetch_attempt"
    id: Mapped[int] = mapped_column(primary_key=True)
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlet.id"), index=True)
    article_id: Mapped[int | None] = mapped_column(ForeignKey("article.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))                # article | rss | sitemap | robots | probe
    url: Mapped[str] = mapped_column(Text)
    final_url: Mapped[str | None] = mapped_column(Text)
    vantage: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(index=True)
    elapsed_ms: Mapped[int | None]
    attempt: Mapped[int] = mapped_column(default=1)              # retry number within one logical fetch
    outcome: Mapped[str] = mapped_column(String(16))             # ok | http_error | timeout | conn_error | cf_challenge | rate_limited
    http_status: Mapped[int | None]
    content_type: Mapped[str | None] = mapped_column(Text)
    response_bytes: Mapped[int | None]
    error: Mapped[str | None] = mapped_column(Text)


class Snapshot(Base):
    """Append-only. Never updated."""
    __tablename__ = "snapshot"
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("article.id"), index=True)
    fetch_attempt_id: Mapped[int] = mapped_column(ForeignKey("fetch_attempt.id"), unique=True)
    fetched_at: Mapped[datetime] = mapped_column(index=True)
    http_status: Mapped[int]
    vantage: Mapped[str] = mapped_column(String(32))
    final_url: Mapped[str] = mapped_column(Text)
    canonical_link: Mapped[str | None] = mapped_column(Text)    # <link rel=canonical> as found
    headline: Mapped[str | None] = mapped_column(Text)          # raw as extracted
    byline: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[str | None] = mapped_column(Text)      # raw string as extracted, no lossy parse
    modified_at: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)         # raw, NOT normalised
    body_length: Mapped[int]                                     # len(body_text), for health check
    body_hash: Mapped[str] = mapped_column(String(64))          # sha256(normalise(body))
    headline_hash: Mapped[str] = mapped_column(String(64))
    byline_hash: Mapped[str] = mapped_column(String(64))
    extra_meta: Mapped[dict] = mapped_column(default=dict)       # full trafilatura metadata dump
    raw_html_ref: Mapped[str | None] = mapped_column(String(64)) # blob sha256; null only if retain_html=on_change & unchanged
    extractor_version: Mapped[str] = mapped_column(String(32))
    normaliser_version: Mapped[str] = mapped_column(String(32)) # hashes depend on it; M2 compares like with like


class ArchiveAttempt(Base):
    __tablename__ = "archive_attempt"
    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshot.id"), index=True)
    requested_at: Mapped[datetime]
    completed_at: Mapped[datetime | None]
    mode: Mapped[str] = mapped_column(String(8))                 # auth | anon
    outcome: Mapped[str] = mapped_column(String(16))             # ok | error | rate_limited | timeout
    spn_job_id: Mapped[str | None] = mapped_column(Text)
    archive_url: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)


class Listing(Base):
    """One fetched RSS/sitemap document. Full URL set kept for M2 unpublish diffing."""
    __tablename__ = "listing"
    id: Mapped[int] = mapped_column(primary_key=True)
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlet.id"), index=True)
    fetch_attempt_id: Mapped[int] = mapped_column(ForeignKey("fetch_attempt.id"), unique=True)
    kind: Mapped[str] = mapped_column(String(16))                # rss | sitemap | sitemap_index | news_sitemap
    source_url: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(index=True)
    entry_count: Mapped[int]
    raw_ref: Mapped[str] = mapped_column(String(64))             # blob of raw XML


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
    ref_id: Mapped[int]                                          # article.id or snapshot.id
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | running | done | failed
    run_after: Mapped[datetime] = mapped_column(index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=5)
    locked_by: Mapped[str | None] = mapped_column(Text)
    locked_at: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime]
    __table_args__ = (
        Index("uq_job_open", "kind", "ref_id", unique=True,
              sqlite_where=text("status IN ('pending','running')"),
              postgresql_where=text("status IN ('pending','running')")),
    )
```

## Forward-compat notes

- M2 `event`: `from_snapshot_id` / `to_snapshot_id` → immutable int PKs. GONE-type events add nullable `fetch_attempt_id` on the new table. No existing-table migration.
- M3 `annotation` → `event.id`. Snapshot untouched.
- Re-crawl dedupe: discovered URL looked up in `article_url` first. `rel=canonical` hit on existing article → alias row. Proven duplicates → `merged_into_id`; nothing deleted.
- Extraction health computed at read time; no stored flag.
- All timestamps UTC. Extracted dates kept as raw strings.

## Next steps after confirmation

schema + Alembic → outlets.yaml + `tw discover` against 3 outlets (prothomalo, thedailystar, bdnews24) → stop, show results → fetch → extract → archive → CLI → site.
