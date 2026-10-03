# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Astro 5 (static output for public routes), TypeScript strict, Tailwind CSS 4, Zod data contract in `web/src/schemas/`. Preact islands only where interactivity is genuinely required. Self-hosted fonts via `@fontsource` (Noto Sans Bengali + a Latin face). Deploy: Cloudflare Pages, plus a public git mirror so anyone can rehost. Source: CLAUDE.md and the web kickoff prompt.

## Users

All four audiences were confirmed; none is secondary:

- **Researchers and journalists** (press-freedom researchers, fact-checkers) read the methodology closely and pull the JSON dataset.
- **The Bangladeshi public**, largely on phones, many reading in Bangla first.
- **Funders and partner organisations** checking that the project is credible and actually running.
- **The monitored newsrooms themselves**, checking what is crawled and how politely.

## Product Purpose

Takedown Watch, run by Activate Rights (activaterights.org), successor to Shutdown Watch, monitors the integrity of Bangladesh's online news record: it captures every article a set of Bangladeshi outlets publishes, archives each independently with the Internet Archive, rechecks on a schedule, and records removals and silent edits as structured events.

The public site at Milestone 1 publishes only: the outlets monitored (as a plain list), aggregate capture and archive coverage, extraction health, and the methodology. Publishing the method before any findings is what protects it from being accused of fitting a conclusion.

## Positioning

A mechanical, evidence-first record: observations (this URL returned 410, this hash changed, here is the third-party archive copy) are kept separate from interpretation, which only ever appears signed by a named human. Capture is complete and unfiltered; severity orders review, never storage.

## Operating Context

- The site is statically generated from versioned JSON in `data/v1/`, which is also the open dataset. No live database behind the public site.
- Bangladesh blocks sites; the built output must work from any plain static file server so it can be mirrored in minutes.
- Bangla and English from the first page. `bn` is the default locale.

## Capabilities and Constraints

- **No event data and no per-outlet figures on the public site before Milestone 4.** Outlets appear as a plain monitored list. Every figure is an aggregate over a group (all outlets, a language, a tier), and any group with fewer than `min_group_outlets` (3) contributing outlets is published suppressed. Reason: the outlets monitored are the press this project defends; "Outlet X deleted 40 articles" is weaponisable, and two monitored outlets were physically attacked in December 2025 after online incitement.
- Cyber Security (Amendment) Act 2026 §26A criminalises publishing "rumours": copy states mechanical facts only. Never imply motive, pressure or censorship.
- Figures are operational, not findings, and are presented plainly.
- **Licence: undecided.** The site must say the licence is pending and make no licence claim.
- **Contact: activaterights.org only.** No email address is published.
- Recheck schedule (T+1h … T+365d) and diffing are Milestone 2 and not yet running; the methodology may describe them only as planned.

## Brand Commitments

- Name: Takedown Watch. Operator: Activate Rights. Predecessor: Shutdown Watch.
- Register named in the brief: a monitoring instrument, not a startup landing page. Dense, legible, quiet, fast. Reference points: OONI Explorer and the Internet Archive.

## Evidence on Hand

- Real pipeline output in `data/v1/*.json` (small: first crawls ran 2026-09-24).
- No logo, no photography, no testimonials, no press coverage, no partner list. None may be invented.

## Product Principles

1. Observation, not accusation: every sentence on the site must be defensible as a mechanical fact.
2. Protect the press being monitored: aggregate, suppress small groups, name no outlet in any figure.
3. Method before findings: the methodology is a first-class page, published ahead of any data about change.
4. Rehostable anywhere: static, dependency-light, works offline from a file server.
5. Bangla is not a translation layer: both languages are designed, not retrofitted.

## Accessibility & Inclusion

Lighthouse accessibility ≥ 95; works at 400px with no horizontal scroll; state encoded in form as well as colour; Bangla conjuncts must render correctly at every weight used.
