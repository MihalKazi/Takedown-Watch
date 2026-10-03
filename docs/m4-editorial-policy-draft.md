# M4 editorial policy — DRAFT, awaiting sign-off

Status: proposed. Not a decision. M4 (public event data) stays blocked until Activate Rights'
leadership explicitly approves a version of this document, in writing, with a named approver and
date below. Until then, event data stays internal (M2/M3 dashboard, authenticated) per
CLAUDE.md.

This is a draft because the two open questions below are not mine to answer: they trade off a
press-freedom tool's usefulness against the real physical safety of the newsrooms it monitors.
That's an organisational call, not an engineering one.

---

## Why this exists

CLAUDE.md states the risk plainly: Prothom Alo and The Daily Star were both physically attacked
in December 2025 following online incitement. A headline reading "Prothom Alo deleted 40
articles" is trivially weaponisable against the outlet named in it — regardless of whether the
underlying removal was routine housekeeping or something worth real scrutiny. Publishing before
this policy exists risks turning a press-freedom tool into a weapon against the press it exists
to protect.

## Open question 1: are individual outlets named?

| Option | What it means | Risk | Value |
|---|---|---|---|
| **A. Named** | Public data attributes each event to its outlet by name, as the internal dashboard already does. | Highest. A single flagged event becomes a headline against a named outlet, true or not, calibrated or not. | Highest. This is the only version that lets the public or press-freedom orgs hold a *specific* outlet accountable, or defend a specific outlet against bad-faith claims with evidence. |
| **B. Anonymised / aggregated** | Public data reports counts and patterns across groups (language, tier, cohort-wide), the way `coverage.json` already does for capture figures. No outlet is individually identifiable. | Low. Mirrors what's already public in M1. | Limited. Shows systemic patterns ("removals cluster in week X across the cohort") but can't answer "did outlet Y take this story down." |
| **C. Named, but delayed and reviewed** | Same as A, but only after a human-reviewed annotation exists (M3) and a cooling-off period has passed (e.g. 90 days), and only for `confirmed` confidence events above a severity floor. | Moderate. Narrows exposure to reviewed, aged, high-confidence cases only. | High for the cases it covers; slower, and still eventually names outlets. |

**Recommendation if asked:** start with B, revisit C once the review backlog (M3) has enough
real, human-annotated cases to know whether the severity model is trustworthy at all. A is not
recommended as a starting point given the stated physical-safety risk.

## Open question 2: how much do we trust the severity model?

`tw.events.compute_severity` (shipped in M2/M3) is a first-pass heuristic: event type × age-at-
change. CLAUDE.md says plainly "the first version will be wrong." Before any event crosses into
public data, decide:

- Does an event need a **human-reviewed annotation** (M3 `tw review` / `tw annotate`) before it
  can ever be published, or can the raw severity score alone qualify it?
- What **confidence** floor is required — `confirmed` only, or is `probable` acceptable with
  review?
- Is there a **minimum age of the event itself** (not just the article) before publication, so a
  just-detected removal isn't published before an outlet has had a chance to explain or correct
  it?

**Recommendation if asked:** require `confirmed` confidence AND a `published`-state annotation
AND `review_decision = confirmed` from a named human reviewer, for any event to leave the
internal dashboard. This is already exactly what the `annotation.review_state` and
`event.published` fields (M2/M3 schema) are for — no new columns needed, just a publish-gate
query that only ever selects rows meeting this bar.

## What M4 code work looks like once this is signed off

Not started, and shouldn't be until the above is answered:

1. A publish-gate export (new `tw export-events-public` or similar), filtering on whichever rule
   this policy settles on, writing to `data/v1/` (or a new versioned directory) in the *outlet
   naming* this policy chooses (named, aggregated, or both).
2. New Zod schema + public Astro page(s) rendering it.
3. A documented, reversible "unpublish" path: CLAUDE.md invariant 6 keeps snapshots
   append-only, but a public *event* that's later found wrong must be retractable from the public
   site without rewriting history — `annotation.review_state = "retracted"` plus a published-set
   diff, not a database edit.

None of this is built. This document exists so that when leadership signs off, the "what to
build" question is already answered and only the "may we build it" question was ever open.

---

## Sign-off

| Field | Value |
|---|---|
| Approved by | Mihal Kazi |
| Date | 2026-10-03 |
| Option chosen (Q1) | B — anonymised/aggregated. No outlet individually identifiable in public data; counts by group (all/language/tier) only, same suppression rule as `coverage.json` (groups with fewer than `min_group_outlets` contributing are withheld). |
| Severity/review bar (Q2) | An event is eligible for publication only if **all** of: `confidence = "confirmed"` AND it has an `annotation` with `review_state = "published"` AND `event.review_decision = "confirmed"` from a named human reviewer. |
| Review cycle | Revisit every 6 months, or sooner if a published figure is later found wrong (see unpublish path below) or the org decides naming policy should change. |

M4 is unblocked under this policy. Any later change to Q1 or Q2 requires updating this table,
not just the code.
