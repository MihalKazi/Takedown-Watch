# M1 proposal — implemented

Status: confirmed and built. Pipeline, schema, and site exist and run locally. Committed to
`github.com/MihalKazi/Takedown-Watch`. Not yet deployed publicly (deploy deferred until local
is solid — see Known gaps below). No diffing/events yet (that's M2, out of scope here).

## Current state (as of 2026-10-03)

Last local crawl: 7,071 articles discovered, 6,285 captured, across 13 of 18 configured outlets.
Full breakdown: `cd pipeline && uv run tw stats`.

### Known gaps (tracked, not blocking M2)

- **4 of 18 outlets capture 0 articles**, each a genuine outlet-side or anti-bot issue, not a
  config bug:
  - `dailynayadiganta` — outlet's own sitemap index points to a vendor demo domain
    (`demo.ccdrbd.org`) that does not resolve. Not fixable on our end.
  - `jagonews24`, `kalerkantho` — sitemap/homepage return 403 even with an honest UA
    (Cloudflare challenge). Flagged `needs_js: true` in `outlets.yaml`; real fix needs a
    Playwright fallback fetch path, which does not exist yet. Deferred — low priority relative
    to finishing M1 basics.
  - `thedissent` — no RSS, no sitemap, robots.txt lists none. Would need homepage/category
    listing-page scraping (a new discovery mode), not a config fix. Deferred.
  - `bssnews` was in this state too; fixed by adding its sitemap URL (it was discoverable, just
    missing from `outlets.yaml`).
- **bn capture rate is nominally lower than en** (~83% vs ~100% in the aggregate `coverage.json`
  numbers), but this is **not a bug**: it's accounted for entirely by two outlets —
  `bd-pratidin` (robots.txt itself returns 403 behind a Cloudflare challenge; per RFC 9309
  §2.3.1.4 the fetcher correctly treats an unreachable robots.txt as disallow-all — this is
  invariant 5, polite crawling, working as intended) and `jugantor` (intermittent
  `cf_challenge` outcomes on article fetches, already retried). All other bn outlets capture at
  or near 100%. No code change warranted; bypassing robots.txt to "fix" this would violate the
  crawling-ethics invariant.
- **Public deploy not done yet** — no Cloudflare Pages config, no public mirror repo. Deferred
  on purpose: build and verify locally first.

## Decisions made (previously open)

1. **Site stack**: monorepo confirmed — `pipeline/ data/ web/`. Pipeline emits `data/v1/*.json`;
   Astro (5, TS strict, Tailwind 4) reads it through Zod schemas in `web/src/schemas/`.
2. **`archive_url` vs invariant 6**: resolved via separate `archive_attempt` table keyed by
   `snapshot_id`. Coverage gap = snapshot with no `ok` row. `Snapshot` stays append-only.
3. **`check` → `fetch_attempt`**: implemented as proposed — one row per HTTP attempt, retries
   included.
4. **Snapshot vs fetch**: implemented as proposed. `Snapshot` only for 2xx HTML; everything else
   lives in `fetch_attempt` for M2's GONE detection to read.
5. **Dependency manager**: `uv`, as proposed.

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

## Next steps

Local build is done (schema, discover, fetch, extract, archive, CLI, site all working against the
real 18-outlet cohort). Remaining before M1 is fully closed out:

1. Deploy: Cloudflare Pages + public git mirror (deferred until local is verified solid).
2. Revisit the 3 deferred outlet gaps (`jagonews24`, `kalerkantho`, `thedissent`) if/when a
   Playwright fallback or listing-page scraper is worth building.
3. Then, and only then, start M2 (scheduler, diff, event generation) — per CLAUDE.md, don't
   build ahead of the current milestone.
