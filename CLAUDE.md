# Takedown Watch

Monitoring system for the integrity of Bangladesh's online news record. Captures every article published by a set of Bangladeshi outlets, archives it independently, rechecks it on a schedule, and logs removals and silent edits as structured events.

Run by Activate Rights (activaterights.org). Successor to Shutdown Watch.

---

## Capture everything. Filter at read time, never at write time.

No article is skipped. No change is too small to record. No event is discarded because it looks like noise.

- Every article from every configured outlet is captured, with no relevance or topic filtering.
- Every detected change is written as an event, including one-character typo fixes.
- Severity is a **sort key, not a gate**. It controls what a human sees first. It never controls what is stored.
- Any suppression, thresholding or triage happens in queries and interfaces, downstream of the database. The raw record stays complete.

Rationale: thresholds applied at write time are unrecoverable. If the severity model turns out to be wrong — and the first version will be — a complete record can be re-scored, while a filtered one is gone. Disk is cheap; missing evidence is not.

---

## Non-negotiable invariants

### 1. Observations and conclusions live in separate tables
Machine-generated records hold **only what was mechanically observed**: this hash changed, this URL returned 410, this byline emptied, here is the archive URL.

Interpretation is not excluded from the system — it is captured in a separate `annotation` table (Milestone 3) that references events, carries a named human author, a timestamp, and a review state.

- No `reason`, `motive`, `cause` or `is_censorship` field on `event`, `snapshot` or `article`.
- No heuristic that labels an event political, suspicious or state-linked.
- Analysts can say anything they can evidence — in `annotation`, signed, and reviewable.

Rationale: Bangladesh's Cyber Security (Amendment) Act 2026 §26A criminalises publishing "rumours" with penalties to 10 years. "This article was removed" is a defensible fact. "This article was removed under pressure" is a claim requiring separate human evidence. Keeping them in different tables means the evidentiary record survives a challenge to the analysis, and the analysis is always attributable to a person rather than to a script. This costs nothing in coverage.

### 2. Independent archival is mandatory
Every captured URL is pushed to the Internet Archive. If we later assert an article was removed, a third party must hold a copy. Our own database is not sufficient evidence.

### 3. Three-valued confidence
Every event carries `confidence`: `confirmed` | `probable` | `unverified`. All three are stored. Confidence describes evidential strength; it is not a filter.

### 4. No event from a single failed fetch
An article is never marked `GONE` on one bad response. Requires N consecutive failures across M hours (configurable, default N=3, M=6), and ideally corroboration from a second vantage point. Transient 5xx, Cloudflare challenges, timeouts and rate-limit responses are recorded as fetch results but do not on their own produce a `GONE` event.

### 5. Polite crawling is a hard requirement
Honest User-Agent with a contact URL. Per-host rate limits enforced in code, not by convention. Default 1 request per 2 seconds per host. We are monitoring newsrooms, many of which are allies — being a bad crawler is both unethical and an existential risk to the project.

### 6. Extractor versioning, and never mutate history
Every snapshot records `extractor_version`. When extraction improves, we must be able to distinguish real content changes from artifacts of our own upgrade. Historical snapshots are append-only: never edited, never backfilled, never deleted.

---

## Core design principle: age at change

Editing an article two hours after publication is routine journalism. Editing or deleting a six-month-old article is anomalous.

Articles are captured at discovery, then rechecked on exponential backoff:

```
T+1h → T+6h → T+24h → T+3d → T+7d → T+30d → T+90d → T+365d
```

`article_age_at_change` is recorded on every event and is the primary severity multiplier. Both a T+90min diff and a T+30d diff are stored; age determines only where they land in the review ordering.

---

## Stack

- Python 3.11+
- PostgreSQL in production, SQLite for local dev — use SQLAlchemy 2.x so both work
- Alembic for migrations
- `httpx` (async) for fetching
- `trafilatura` for article extraction and metadata — handles Bangla better than readability-lxml
- `selectolax` or `lxml` for targeted parsing where trafilatura is insufficient
- `pydantic-settings` for config
- `structlog` for logging
- `pytest` for tests
- Playwright **only** as a per-outlet fallback, never the default fetch path

**Queue: use a Postgres/SQLite table with `SELECT ... FOR UPDATE SKIP LOCKED`.** Do not add Redis, Celery or RQ. At ~16k fetches/day a DB-backed queue is simpler, more durable, and has fewer moving parts for a one-developer team.

---

## Bangla text handling

This is the highest-risk technical area. Get it wrong and the system produces a 100% false-positive rate.

- **Always apply Unicode NFC normalisation** before hashing or diffing. Identical rendered Bangla text has multiple valid encodings; without NFC you get phantom diffs at scale.
- Normalise whitespace, quote characters and dash variants.
- Be careful with ZWJ/ZWNJ (U+200D / U+200C) — they are semantic in Bangla conjuncts. Normalise, do not strip.
- Normalisation applies to the **hashing and diffing path only**. `body_text` is always stored raw as extracted, so normalisation can be revised later without data loss.
- Test fixtures must include real Bangla article text, not Latin placeholders.

---

## Event taxonomy

```
FIRST_SEEN          new article captured
HEADLINE_CHANGED    h1 / og:title differs
BODY_CHANGED        normalised body hash differs
BYLINE_REMOVED      author field emptied (high significance)
BYLINE_CHANGED      author field differs
DATE_CHANGED        published_at moved
DEINDEXED           absent from both RSS and sitemap
UNPUBLISHED         dropped from sitemap, URL still resolves
REDIRECTED          now 3xx to homepage or section index
GONE_404 / GONE_410 hard delete
GONE_SOFT           200 but content replaced with a not-found page
ROBOTS_BLOCKED      new robots.txt Disallow covering a tracked URL
GEO_BLOCKED         differs by vantage point
RESTORED            previously-gone URL returns
```

Every occurrence of every type is recorded, regardless of magnitude.

---

## Data model

```
outlet     (id, name, language, base_url, cms, rss_urls[], sitemap_urls[],
            tier, rate_limit_seconds, needs_js, retain_html, active)

article    (id, outlet_id, canonical_url, url_hash, first_seen, last_seen, status)

snapshot   (id, article_id, fetched_at, http_status, vantage,
            headline, byline, published_at, modified_at,
            body_text, body_hash, headline_hash, byline_hash,
            raw_html_ref, archive_url, extractor_version)

event      (id, article_id, type, detected_at, from_snapshot_id, to_snapshot_id,
            severity, confidence, article_age_at_change,
            reviewed_by, reviewed_at, review_decision, published)     # M2

annotation (id, event_id, author, written_at, body, review_state)      # M3
```

`retain_html` is per-outlet: `always` (default) or `on_change`. Full HTML retention is a storage decision, not a filtering one — default to keeping it and downgrade specific outlets only if disk becomes a real constraint.

---

## Milestones

1. **Capture** ← current. Discovery, fetch, extract, store, archive. Public status site. No diffing yet.
2. **Recheck and diff.** Scheduler, backoff, normalisation, event generation. Internal event dashboard behind auth.
3. **Review queue and annotation.** Triage ordering, severity calibration, human analysis layer.
4. **Public event data.** Released only after the editorial policy below is settled.

Do not build ahead of the current milestone.

## Public site

The site is built from the start, but **what it publishes is staged**:

| Stage | Public | Internal |
|---|---|---|
| M1 | Outlets monitored, articles captured, archive coverage, methodology | — |
| M2–M3 | Same | Full event dashboard, authenticated |
| M4 | Event data, after editorial sign-off | Everything |

### Stack

Monorepo, two halves, one typed contract between them.

```
takedown-watch/
  pipeline/    Python — crawl, extract, archive, store
  data/        versioned JSON the pipeline emits, the site consumes
  web/         Astro 5 — public site and internal dashboard
```

**Frontend: Astro 5, TypeScript (strict), Tailwind CSS 4.** Static output for public routes; per-route SSR (`export const prerender = false`) for the authenticated internal dashboard. Astro's built-in i18n routing for `bn` and `en`. Islands only where a page genuinely needs interactivity — filterable tables, the diff viewer. Everything else ships zero JS.

**The data contract is the important part.** The Python pipeline never talks to the web app directly. It writes versioned JSON into `data/`; the Astro build reads it through Zod schemas defined in `web/src/schemas/`. If the pipeline changes shape, the site build fails loudly instead of rendering wrong numbers. Treat those schemas as the interface between the two halves and version them.

The JSON in `data/` **is** the open dataset. One pipeline serves the site and the release; there is no separate export path.

**Deploy:** Cloudflare Pages. Also push the built output to a public git repo — this project monitors censorship in a country that blocks sites, so the whole thing must be rehostable by anyone in minutes.

Charts render as server-generated SVG wherever the data is static. Reach for a client-side chart library only for something genuinely interactive.

Bangla and English from the first page, with Noto Sans Bengali. Do not retrofit i18n.

### Why event data is not public before M4

The outlets monitored here are the press this project exists to defend. A headline reading "Prothom Alo deleted 40 articles" is trivially weaponisable, and both Prothom Alo and The Daily Star were physically attacked in December 2025 following online incitement. Publishing event data before the severity model can distinguish routine editorial correction from anomalous removal — and before the organisation has settled whether individual outlets are named — turns a press-freedom tool into a weapon against the press. Capture everything now; publish nothing about specific outlets until that policy exists.

---

## Do not

- Put interpretation in a machine-generated table — it goes in `annotation` (invariant 1)
- Add Redis, Celery or RQ
- Use Playwright as the default fetch path
- Drop, threshold or deduplicate events at write time
- Mutate, backfill or delete historical snapshots
- Commit API keys, archive.org credentials or `.env`
- Serve the public site live from the database — it is statically generated
- Publish event data or name individual outlets on the public site before Milestone 4

---

## Operational notes

- Internet Archive Save Page Now is rate-limited and slow. Queue archival as a **separate job**; never block capture on it. Authenticated S3-style keys from an archive.org account give much better throughput than anonymous SPN.
- The Wayback CDX API (`web.archive.org/cdx/search/cdx`) supports historical backfill — useful for reconstructing baselines predating this system.
- robots.txt: fetch and store it per outlet, log changes as events. Compliance policy for already-tracked URLs is a configurable flag (`respect_retroactive_robots`), defaulting to `false`, pending an organisational decision. Do not hardcode either behaviour.