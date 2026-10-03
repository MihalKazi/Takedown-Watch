---
name: Takedown Watch
description: A public ledger of how much of Bangladesh's online news record has been captured and archived.
colors:
  paper: "#ffffff"
  paper-2: "#f5f6f3"
  ink: "#1d1e1b"
  ink-2: "#53564f"
  ink-3: "#6f736a"
  rule: "#d9dbd4"
  rule-strong: "#1d1e1b"
  capture: "#2e6b34"
  link: "#1f4ea3"
  link-hover: "#143878"
  warn: "#8a5a00"
  fail: "#a3261c"
  hatch: "#858a7f"
  focus: "#1f4ea3"
  selection: "#d6e2f7"
typography:
  display:
    fontFamily: "Noto Sans, Noto Sans Bengali, system-ui, sans-serif"
    fontSize: "clamp(1.75rem, 1.2rem + 1.6vw, 2.375rem)"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.012em"
  headline:
    fontFamily: "Noto Sans, Noto Sans Bengali, system-ui, sans-serif"
    fontSize: "1.1875rem"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.004em"
  title:
    fontFamily: "Noto Sans, Noto Sans Bengali, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 650
    lineHeight: 1.25
  body:
    fontFamily: "Noto Sans, Noto Sans Bengali, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.75
  label:
    fontFamily: "Noto Sans, Noto Sans Bengali, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 500
    lineHeight: 1.5
  figure:
    fontFamily: "Noto Sans, Noto Sans Bengali, system-ui, sans-serif"
    fontSize: "1.1875rem"
    fontWeight: 600
    lineHeight: 1.75
    fontFeature: "\"tnum\" 1, \"lnum\" 1"
rounded:
  none: "0"
  hair: "2px"
spacing:
  row: "0.55rem 0.9rem 0.55rem 0"
  ledger-row: "0.7rem"
  section: "clamp(3rem, 2rem + 3vw, 5rem)"
  gutter: "clamp(1rem, 0.5rem + 2.5vw, 2.5rem)"
  measure: "68ch"
  page: "76rem"
components:
  link:
    textColor: "{colors.link}"
  link-hover:
    textColor: "{colors.link-hover}"
  nav-item:
    textColor: "{colors.ink-2}"
    typography: "{typography.label}"
    padding: "0.35rem 0"
  nav-item-current:
    textColor: "{colors.ink}"
  lang-switch:
    textColor: "{colors.link}"
    rounded: "{rounded.hair}"
    padding: "0.2rem 0.6rem"
  ledger-table:
    typography: "{typography.label}"
    padding: "{spacing.row}"
  ledger-row:
    textColor: "{colors.ink-2}"
    padding: "{spacing.ledger-row}"
  code-inline:
    backgroundColor: "{colors.paper-2}"
    rounded: "{rounded.hair}"
    padding: "0.05em 0.3em"
---

# Design System: Takedown Watch

## Overview

**Creative North Star: "The Capture Ledger"**

Takedown Watch looks like a well-kept register: white paper, near-black ink, hairline rules, and figures set on one tabular grid. The signature is the Capture Calendar. Each day is a cell, and the area of a green disc shows how many captures that day had. The system shows density and continuity, not dashboards. There are no stat tiles, no line charts, no cards, and no shadows. Structure comes from rules and alignment alone.

Two accents do two different jobs. Ink-green means "captured": the calendar marks, the healthy-state glyph, the current-page underline and list markers. Archive blue means "you can press this": links, the language switch and the focus ring. A withheld figure is never left blank or replaced by a dash. It gets a hatched ghost cell, drawn as deliberately as a real number, and the reason is stated once in words.

The site is bilingual (Bangla and English) from the root. Both scripts share one vertical rhythm, with Bangla set slightly larger so it reads at the same weight as Latin. Every page is static HTML with server-rendered SVG and zero JavaScript. Light and dark themes follow the operating system's preference, and there is no toggle.

**Key Characteristics:**
- White ground, near-black ink, 1px hairline rules; no shadows, no cards, radius 2px at most.
- Ink-green for capture, archive blue for actions. Neither colour is used for decoration.
- Tabular lining figures everywhere; Bangla digits in the bn locale.
- One line-height rhythm (1.75) for both scripts.
- Withheld figures are drawn as hatched ghosts with a stated reason.
- State is never shown by colour alone: form and a text label always come with it.
- Zero JavaScript; charts are server-rendered SVG.

## Colors

A near-monochrome ledger palette with a slight green cast in the neutrals. Two functional accents and two state colours sit on top of it.

### Primary
- **Capture Ink-Green**: the colour of a captured day. It fills calendar discs, the wordmark's dot grid, the healthy-state disc, the current-nav underline and prose list markers. It is never used for links or buttons.

### Secondary
- **Archive Blue**: reserved for links, the language switch and the focus ring (`focus` matches `link`). Links carry a 1px underline at 45% of the link colour, which goes to full colour on hover along with the darker `link-hover`.

### Tertiary
- **Degraded Amber** (`warn`) and **Failing Brick** (`fail`): used only inside health marks, and always paired with a distinct glyph shape and a text label.

### Neutral
- **Paper**: page ground.
- **Paper Tint** (`paper-2`): inline code background only.
- **Ink**: body text, headings, the calendar's latest-day frame and the heavy rules (`rule-strong` matches ink).
- **Ink Secondary** (`ink-2`): ledger labels, table heads, notes, withheld row names, the colophon.
- **Ink Tertiary** (`ink-3`): weekday initials, zero-capture rings, before-monitoring dots, the no-data glyph.
- **Hairline** (`rule`): row dividers, masthead and colophon borders, month-name underlines.
- **Hatch Grey** (`hatch`): stripes and border of the withheld ghost cell.
- **Selection Blue** (`selection`): text selection background.

A full dark set is defined under `prefers-color-scheme: dark` with the same token names. The paper is a green-black (#121411), the capture green is lightened (#8cc98f) and the link is lightened (#9cbcf5). Dark values are recorded in the sidecar.

### Named Rules
**The Two Jobs Rule.** Green means captured; blue means pressable. A green link or a blue data mark breaks the system.

**The Not By Colour Alone Rule.** Every state encoded in colour also has a shape and a text label. Health uses a filled disc, half disc, struck ring or dotted ring next to its label. Calendar days use a sized disc, an empty ring or a faint dot.

## Typography

**Display Font:** Noto Sans (variable, weights 100 to 900), with system-ui fallback
**Body Font:** Noto Sans plus Noto Sans Bengali, loaded as one stack and split by unicode-range
**Label/Mono Font:** none distinct; figures use the tabular and lining features of the same family

**Character:** One humanist sans family covers both scripts with matched metrics, so a bilingual page reads as one voice. Hierarchy comes from weight (650 for headings) and rules, not from large jumps in size.

### Hierarchy
- **Display** (650, clamp 1.75 to 2.375rem, 1.25, -0.012em): page h1 only.
- **Headline** (650, 1.1875rem, 1.25): section h2. It sits on a 1px ink rule with 0.5rem clearance.
- **Title** (650, 1rem, 1.25): h3 and note headings.
- **Body** (400, 1rem, 1.75): prose and ledes, with a maximum measure of 68ch.
- **Label** (500 or 600, 0.8125rem, 1.5 to 1.6): nav, table text, legends, month names, notes.
- **Figure** (600, 1.1875rem, tabular lining): headline totals in the ledger.
- Calendar weekday initials are 0.6875rem in ink-3. They are the smallest text on the site.

### Named Rules
**The One Rhythm Rule.** The root line-height is 1.75 for both scripts. `html:lang(bn)` scales the root to 106.25% instead of switching to a separate rhythm.

**The Tabular Figures Rule.** Every figure uses `tabular-nums lining-nums`, and numeric columns are end-aligned. Numbers go through `Intl` with the page locale, so bn shows Bangla digits.

## Layout

The page is a single centred column with a maximum width of 76rem and a fluid gutter (1 to 2.5rem). Sections are separated by a fluid gap (3 to 5rem), and each opens with an h2 on a heavy ink rule. Breakpoints are 64rem (the calendar goes from 6 to 4 columns, two-column page grids collapse, the outlets tier grid goes from 3 to 2), 48rem (the two-column totals ledger and data notes collapse to one) and 40rem (phone). On phones the masthead nav wraps to a full-width second line. The calendar shows only the latest four months, newest first, in a 2x2 grid. Group tables drop their header row and become stacked label/value blocks, with labels drawn from `data-label`. Wide tables otherwise sit in a horizontal scroll container. The methodology page pairs a prose column with a sticky 17rem state rail.

### Named Rules
**The Stack, Don't Scroll Rule.** At 40rem and below, a data table becomes one block per row, with each label and value on one line. It never becomes a sideways scroll on a phone.

## Elevation & Depth

The system is flat. It has no box-shadows, no layered surfaces and no cards. Depth and grouping come from two rule weights: a 1px `rule` hairline between rows, and a 1px `rule-strong` ink line under section heads, table heads and subheads. The only tinted surface is inline code on `paper-2`.

### Named Rules
**The Rules Not Boxes Rule.** Group content with horizontal rules and alignment. Never enclose it in a shadowed or filled container.

## Shapes

The shape language is square and hairline. The corner radius is 0 everywhere except the language switch and inline code (2px) and the focus outline (1px). Circles are reserved for data: calendar discs, health glyphs and the wordmark's dot grid. A square frame marks the latest day in the calendar, the legend and the wordmark, and it never touches the disc inside it. The withheld ghost is a 2.75em x 0.85em rectangle with a 1px hatch border and a 135deg stripe (1.25px line, 4.5px repeat).

## Components

### Navigation
- **Style:** a masthead row with the wordmark on the left (dot-grid SVG mark plus the name, weight 700) and the nav and language switch on the right. A hairline sits below.
- **Items:** 0.8125rem, weight 500, ink-2. Hover changes the colour to ink. The current page is ink with a 2px ink-green underline.
- **Language switch:** blue text in a 1px hairline box with a 2px radius. On hover the border turns blue.

### Links
- Archive blue, with a 1px underline offset 0.22em at 45% opacity. On hover the text darkens and the underline goes to full colour, over a 120ms ease-out transition. The focus ring is a 2px blue outline offset 3px.

### Ledger Table
- Dense and ruled: 0.8125rem text at 1.5 line-height, hairline row dividers, and an ink rule under the head. Head cells are ink-2 at weight 600. Numeric columns are end-aligned tabular figures. Subhead rows (group sections) are ink-2 at 600 with an ink rule.

### Totals Ledger
- A definition list in two columns (one below 48rem). Each row has an ink-2 label on the left and a 1.1875rem weight-600 figure on the right, separated by a hairline. An optional note sits under the label. The last-run time sits at the right of the section heading.

### Capture Calendar (signature)
- Twelve month grids, each drawn as SVG with 24 x 19 cells and weeks starting on Saturday. Days with captures get an ink-green disc whose area scales with volume (radius 2.2 to 6.8). Monitored days with no captures get an empty ink-3 ring. Days before monitoring began get a faint ink-3 dot. The latest day carries an ink frame. Each month has a name and a tabular total on a hairline. The legend below a hairline shows a three-step size key, the other key marks and the "monitoring began" note.

### Health Mark
- A 12px SVG glyph plus a text label. The glyph is a filled disc for ok (green), a half disc for degraded (amber), a struck ring for failing (brick) and a dotted ring for no data (ink-3).

### Withheld Ghost
- The hatched rectangle fills every withheld figure cell, and screen readers get a "withheld" text alternative. The reason (small group or complementary) appears once, at 0.75rem in ink-2, under the group name and never in each cell.

## Do's and Don'ts

### Do:
- **Do** show coverage as marks on a calendar, with area proportional to volume and a size key in the legend.
- **Do** draw withheld figures as hatched ghost cells and state the reason once, under the row name.
- **Do** pair every coloured state with a glyph shape and a text label.
- **Do** set every figure in tabular lining numerals, end-aligned, formatted for the page locale.
- **Do** use one 1.75 rhythm for both scripts and scale the bn root to 106.25%.
- **Do** render charts as static SVG and ship zero JavaScript on public pages.
- **Do** define every colour for both light and dark schemes through the same custom-property names.

### Don't:
- **Don't** use archive blue for data marks or ink-green for links and actions.
- **Don't** use rows of stat tiles, line charts, cards or shadows. Structure is rules and alignment.
- **Don't** leave a withheld figure blank, zero or dashed. It gets a hatch.
- **Don't** convey health, capture state or any status through colour alone.
- **Don't** make phone tables scroll sideways. Stack them as label/value blocks at 40rem and below.
- **Don't** round corners beyond 2px.
