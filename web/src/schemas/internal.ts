/**
 * data/internal/events.json: the M2 event dashboard's data. NOT the open dataset in
 * web/src/schemas/files.ts -- it names outlets and articles directly, which CLAUDE.md permits
 * only for the authenticated internal dashboard (M2-M3), never the public site before M4.
 *
 * This file must never be committed, and the page that reads it must never ship in a public
 * mirror of dist/ -- see pipeline/src/tw/export_internal.py and
 * web/src/pages/internal/events.astro for the caveat.
 */
import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { z } from "zod";
import { timestamp } from "./common.ts";

const SCHEMA_VERSION = "1.0.0" as const;

export const InternalAnnotation = z.strictObject({
  author: z.string().min(1),
  written_at: timestamp,
  body: z.string().min(1),
  review_state: z.enum(["draft", "published", "retracted"]),
});

export const ArticleVersion = z.strictObject({
  fetched_at: timestamp,
  headline: z.string().nullable(),
  body: z.string().nullable(),
  archive_url: z.string().nullable(),
});

export const InternalEvent = z.strictObject({
  id: z.int().positive(),
  type: z.string().min(1),
  detected_at: timestamp,
  confidence: z.enum(["confirmed", "probable", "unverified"]),
  severity: z.int(),
  article_age_at_change: z.number().nonnegative(),
  outlet_slug: z.string().min(1),
  outlet_name: z.string().min(1),
  article_url: z.url(),
  from_headline: z.string().nullable(),
  to_headline: z.string().nullable(),
  from_byline: z.string().nullable(),
  to_byline: z.string().nullable(),
  from_published_at: z.string().nullable(),
  to_published_at: z.string().nullable(),
  from_final_url: z.string().nullable(),
  to_final_url: z.string().nullable(),
  from_fetched_at: timestamp.nullable(),
  to_fetched_at: timestamp.nullable(),
  body_diff: z.string().nullable(),
  from_body: z.string().nullable(),
  to_body: z.string().nullable(),
  from_archive_url: z.string().nullable(),
  to_archive_url: z.string().nullable(),
  reviewed_by: z.string().nullable(),
  review_decision: z.string().nullable(),
  published: z.boolean(),
  annotations: z.array(InternalAnnotation),
  article_change_count: z.int().nonnegative(),
  article_versions: z.array(ArticleVersion),
});

export const InternalEvents = z.strictObject({
  schema_version: z.literal(SCHEMA_VERSION),
  generated_at: timestamp,
  events: z.array(InternalEvent),
});

export type InternalEvent = z.infer<typeof InternalEvent>;
export type InternalEvents = z.infer<typeof InternalEvents>;

export class InternalDataError extends Error {
  constructor(message: string) {
    super(`\n\n[internal data] ${message}\n`);
    this.name = "InternalDataError";
  }
}

const RUN = "Run the pipeline first:\n  cd pipeline && uv run tw export-internal\n" +
  "(or set TW_DATA_DIR to a directory containing internal/events.json)";

export function internalDataDir(): string {
  return process.env.TW_DATA_DIR ?? resolve(process.cwd(), "..", "data");
}

export function loadInternalEvents(dir: string = internalDataDir()): InternalEvents {
  const path = join(dir, "internal", "events.json");
  if (!existsSync(path)) throw new InternalDataError(`missing ${path}\n${RUN}`);
  const raw = JSON.parse(readFileSync(path, "utf-8"));
  const result = InternalEvents.safeParse(raw);
  if (!result.success) {
    throw new InternalDataError(`events.json does not match its schema:\n${z.prettifyError(result.error)}`);
  }
  return result.data;
}
