/**
 * Loads and validates the whole dataset at build time. Any mismatch throws: the build fails
 * rather than rendering partial, coerced or internally inconsistent numbers.
 */
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { z } from "zod";
import { DATASET_DIR, SCHEMA_VERSION } from "./common.ts";
import { FILES, type CaptureVolume, type Coverage, type ExtractionHealth, type FileName, type Meta, type Outlets } from "./files.ts";

export interface Dataset {
  meta: Meta;
  coverage: Coverage;
  outlets: Outlets;
  health: ExtractionHealth;
  volume: CaptureVolume;
}

export class DataContractError extends Error {
  constructor(message: string) {
    super(`\n\n[data contract] ${message}\n`);
    this.name = "DataContractError";
  }
}

const RUN_PIPELINE =
  "Run the pipeline first:\n  cd pipeline && uv run tw crawl && uv run tw export\n" +
  "(or set TW_DATA_DIR to a directory containing v1/*.json)";

function parseFile<N extends FileName>(dir: string, name: N): z.infer<(typeof FILES)[N]> {
  const path = join(dir, name);
  if (!existsSync(path)) throw new DataContractError(`missing ${path}\n${RUN_PIPELINE}`);
  let raw: unknown;
  try {
    raw = JSON.parse(readFileSync(path, "utf-8"));
  } catch (e) {
    throw new DataContractError(`${path} is not valid JSON: ${(e as Error).message}`);
  }
  const version = (raw as { schema_version?: unknown })?.schema_version;
  if (version !== SCHEMA_VERSION) {
    throw new DataContractError(
      `${name}: schema_version ${JSON.stringify(version)} but this site expects "${SCHEMA_VERSION}". ` +
        "Update web/src/schemas/ and pipeline/src/tw/export.py together.",
    );
  }
  const result = FILES[name].safeParse(raw);
  if (!result.success) {
    throw new DataContractError(`${name} does not match its schema:\n${z.prettifyError(result.error)}`);
  }
  return result.data as z.infer<(typeof FILES)[N]>;
}

function check(cond: boolean, message: string): void {
  if (!cond) throw new DataContractError(`dataset inconsistent: ${message}`);
}

function sum<T>(rows: T[], f: (r: T) => number): number {
  return rows.reduce((a, r) => a + f(r), 0);
}

/** Cross-file invariants: totals add up, suppression follows the rule, files describe the same groups. */
function crossCheck(d: Dataset): void {
  const outlets = d.outlets.outlets;
  const slugs = outlets.map((o) => o.slug);
  check(new Set(slugs).size === slugs.length, "duplicate outlet slugs in outlets.json");
  check(d.coverage.outlets_monitored === outlets.length, "coverage.outlets_monitored != outlets.json length");
  check(d.coverage.outlets_contributing <= d.coverage.outlets_with_sources, "more outlets contributing than have sources");

  const min = d.meta.min_group_outlets;
  const keyOf = (g: { group: string; key: string }) => `${g.group}:${g.key}`;
  const covKeys = d.coverage.groups.map(keyOf);
  check(new Set(covKeys).size === covKeys.length, "duplicate group rows");
  check(
    JSON.stringify(covKeys) === JSON.stringify(d.health.groups.map(keyOf)),
    "coverage.json and extraction-health.json describe different groups",
  );

  for (const g of d.coverage.groups) {
    const members =
      g.group === "all" ? outlets : outlets.filter((o) => (g.group === "language" ? o.language : o.tier) === g.key);
    check(g.outlets_monitored === members.length, `${keyOf(g)}: outlets_monitored != its members in outlets.json`);
    check(g.suppressed || g.outlets_contributing! >= min, `${keyOf(g)}: published with fewer than min_group_outlets contributing`);
    if (!g.suppressed) {
      check(g.articles_captured! <= g.articles_discovered!, `${keyOf(g)}: captured > discovered`);
      check(g.snapshots_archived! <= g.snapshots!, `${keyOf(g)}: archived > snapshots`);
    }
  }
  const reasons = new Map(d.coverage.groups.map((g) => [keyOf(g), g.suppression_reason]));
  for (const h of d.health.groups) {
    check(reasons.get(keyOf(h)) === h.suppression_reason, `health ${keyOf(h)}: suppression differs from coverage.json`);
    check(h.suppressed || h.outlets_contributing! >= min, `health ${keyOf(h)}: published with fewer than min_group_outlets contributing`);
  }

  const all = d.coverage.groups.find((g) => g.group === "all");
  if (!all) throw new DataContractError("coverage.json has no 'all' group");
  check(d.volume.suppressed === all.suppressed, "capture-volume suppression disagrees with the 'all' group");
  if (!all.suppressed) {
    const series = sum(d.volume.series, (p) => p.snapshots);
    check(series === all.snapshots, `capture-volume sums to ${series}, 'all' group has ${all.snapshots} snapshots`);
  }
  for (const kind of ["language", "tier"] as const) {
    const rows = d.coverage.groups.filter((g) => g.group === kind);
    check(sum(rows, (g) => g.outlets_monitored) === outlets.length, `${kind} groups do not partition the outlets`);
    if (!all.suppressed && rows.every((g) => !g.suppressed)) {
      check(sum(rows, (g) => g.snapshots!) === all.snapshots, `${kind} snapshots do not sum to the total`);
    }
  }
  const expected = Object.keys(FILES).sort();
  check(JSON.stringify([...d.meta.files].sort()) === JSON.stringify(expected), `meta.files != ${expected.join(", ")}`);
}

export function dataDir(): string {
  const base = process.env.TW_DATA_DIR ?? resolve(process.cwd(), "..", "data");
  return join(base, DATASET_DIR);
}

let cached: Dataset | undefined;

export function loadDataset(dir: string = dataDir()): Dataset {
  if (cached && dir === dataDir()) return cached;
  if (!existsSync(dir) || readdirSync(dir).filter((f) => f.endsWith(".json")).length === 0) {
    throw new DataContractError(`no dataset at ${dir}\n${RUN_PIPELINE}`);
  }
  const d: Dataset = {
    meta: parseFile(dir, "meta.json"),
    coverage: parseFile(dir, "coverage.json"),
    outlets: parseFile(dir, "outlets.json"),
    health: parseFile(dir, "extraction-health.json"),
    volume: parseFile(dir, "capture-volume.json"),
  };
  crossCheck(d);
  if (dir === dataDir()) cached = d;
  return d;
}
