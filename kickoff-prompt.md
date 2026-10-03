# Claude Code kickoff prompt — Takedown Watch, Milestone 1

Run `git init` and drop `CLAUDE.md` in the repo root first, then paste everything below the line into Claude Code.

---

We're building **Takedown Watch**, a monitoring system for the integrity of Bangladesh's online news record. Read `CLAUDE.md` first — it contains non-negotiable invariants, particularly the fact/interpretation wall and the Bangla Unicode handling rules. Follow them exactly.

This session covers **Milestone 1: Capture** only. Do not build ahead of it.

## Goal

By the end of this session I want to be able to run one command and have the system discover, fetch, extract, store and queue-for-archival every article published today by a set of Bangladeshi news outlets — with the data going into a schema that Milestone 2 can diff against without migration.

Capture correctness matters far more than capture completeness right now. A pipeline that handles three outlets flawlessly beats one that handles fifteen with silent extraction failures.

## Scope

**1. Project skeleton**
- `pyproject.toml`, dependency management, `.env.example`, `.gitignore`
- `pydantic-settings` config, structlog logging
- pytest set up with real Bangla fixtures, not Latin placeholders

**2. Schema and migrations**
- SQLAlchemy 2.x models for `outlet`, `article`, `snapshot`, `check` exactly as specified in `CLAUDE.md`
- Alembic migration
- SQLite for local dev, Postgres-compatible — no SQLite-only column types
- Leave `event` for Milestone 2, but design the snapshot table so events can reference two snapshots without schema change

**3. Outlet configuration and feed discovery**
- `outlets.yaml` with the cohort below
- A `discover` command that, for each outlet, probes for RSS feeds and news sitemaps, **verifies each candidate URL actually returns valid content**, and writes confirmed feed URLs back to the config
- Report per outlet what was found and what failed. Do not guess or assume feed paths — verify every one.

**4. Discovery layer**
- Pull article URLs from RSS and from news sitemaps
- Canonicalise URLs: strip tracking params, resolve to `<link rel="canonical">` where present, dedupe
- Persist the full sitemap URL set per fetch — Milestone 2's unpublish detection depends on being able to diff these sets, so store them now even though nothing consumes them yet

**5. Fetch layer**
- Async `httpx`, per-host rate limiting enforced in code (default 1 req / 2s, per-outlet override)
- Honest User-Agent with a contact URL
- Retry with backoff on 5xx and timeouts; never retry a 404
- Record HTTP status and a `vantage` label on every snapshot
- Handle Cloudflare challenge responses as a distinct, non-failure outcome

**6. Extraction**
- `trafilatura` for body, headline, byline, publish date, modified date
- Unicode NFC normalisation before any hashing — see the Bangla notes in `CLAUDE.md`, and be careful with ZWJ/ZWNJ
- Separate hashes for normalised body, headline, byline
- Stamp `extractor_version` on every snapshot
- Per-outlet extraction health check: flag when extracted body length is anomalous versus that outlet's rolling median, so redesigns surface immediately rather than as a phantom diff wave in Milestone 2

**7. Archival**
- Push captured URLs to Internet Archive Save Page Now
- **Separate queue, never blocking capture** — SPN is slow and rate-limited
- Support authenticated S3-style archive.org keys via env, fall back to anonymous
- Store the returned archive URL on the snapshot; retry failures, and make unarchived snapshots queryable so we can see coverage gaps

**8. CLI**
```
tw discover              verify feeds for configured outlets
tw crawl [--outlet X]    one discovery + capture pass
tw archive               drain the archival queue
tw stats                 coverage: articles, snapshots, archive rate, extraction health
```

## Explicitly not this session

No diffing, no event generation, no scheduler or recheck backoff, no review queue, no dashboard, no Playwright, no Redis/Celery.

## Acceptance criteria

- `tw crawl` runs end to end against at least three outlets, one of them Bangla-language
- Extracted Bangla text round-trips through normalisation and hashing without phantom changes — prove this with a test that NFC-normalises two differently-encoded but visually identical Bangla strings and asserts equal hashes
- Rate limiting is demonstrably enforced (test it, don't just assert it in a comment)
- Re-running `tw crawl` immediately produces no duplicate articles
- `tw stats` shows a real archive success rate
- Tests pass, including at least one real Bangla extraction fixture

## Outlet cohort

Verify every domain and discover feeds before trusting any of these. Several may have moved, changed CMS, or blocked crawlers.

**Bangla mass-circulation:** prothomalo.com, kalerkantho.com, jugantor.com, samakal.com, bd-pratidin.com
**Bangla, other alignments:** dailynayadiganta.com, dailyinqilab.com, dailyamardesh.com
**English:** thedailystar.net, dhakatribune.com, tbsnews.net, newagebd.net
**Online-native:** bdnews24.com, banglatribune.com, jagonews24.com
**State wire:** bssnews.net
**Independent:** netra.news, thedissent.news

Political balance across this cohort is a methodological requirement, not diplomacy — a monitor covering only liberal English-language papers produces a finding about liberal English-language papers. Keep the spread.

## How to work

Start by proposing the module layout and the exact SQLAlchemy models, and wait for me to confirm before writing the rest. I want to review the schema before there's code depending on it.

Then build in this order: schema → config/discovery → fetch → extract → archive → CLI. Get `tw discover` working against three outlets and show me the results before scaling to all eighteen.

If an outlet blocks us, times out, or needs JS, record that in `outlets.yaml` as a known limitation and move on — don't work around it this session.
