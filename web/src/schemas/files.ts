/**
 * One schema per JSON file in data/v1/. Mirrors pipeline/src/tw/export.py.
 * z.strictObject: an unexpected key is a contract change and fails the build.
 *
 * Publication policy (M1): outlets are a plain monitored list; every figure is an aggregate over a
 * group of outlets, and a group with fewer than meta.min_group_outlets contributing outlets is
 * published suppressed, with null figures ("small_group"). A group whose figures could be recovered
 * by subtracting published groups is suppressed too ("complementary").
 */
import { z } from "zod";
import { calendarDate, count, fileHeader, health, language, rate, suppressionReason, tier, timestamp } from "./common.ts";

/** meta.json: run metadata. */
export const Meta = z.strictObject({
  ...fileHeader,
  pipeline_version: z.string().min(1),
  extractor_version: z.string().min(1),
  normaliser_version: z.string().min(1),
  vantages: z.array(z.string().min(1)),
  capture_window_hours: z.number().positive(),
  /** Groups with fewer contributing outlets than this are published suppressed. */
  min_group_outlets: z.int().positive(),
  first_capture_at: timestamp.nullable(),
  last_capture_at: timestamp.nullable(),
  last_listing_fetch_at: timestamp.nullable(),
  files: z.array(z.string()),
});

export const groupKind = z.enum(["all", "language", "tier"]);

/** Figures for a group of outlets. Never one outlet. */
export const GroupCoverage = z
  .strictObject({
    group: groupKind,
    key: z.string().min(1),
    outlets_monitored: count,
    /** Null when suppressed: in a small group the count itself would identify an outlet. */
    outlets_contributing: count.nullable(),
    suppressed: z.boolean(),
    suppression_reason: suppressionReason.nullable(),
    articles_discovered: count.nullable(),
    articles_captured: count.nullable(),
    snapshots: count.nullable(),
    snapshots_archived: count.nullable(),
    capture_success_rate: rate,
    archive_rate: rate,
  })
  .refine(
    (g) =>
      g.suppressed
        ? [g.outlets_contributing, g.articles_discovered, g.articles_captured, g.snapshots, g.snapshots_archived, g.capture_success_rate, g.archive_rate].every((v) => v === null)
        : g.outlets_contributing !== null && g.snapshots !== null && g.articles_captured !== null && g.articles_discovered !== null && g.snapshots_archived !== null,
    { message: "figures must be null exactly when suppressed" },
  )
  .refine((g) => g.suppressed === (g.suppression_reason !== null), { message: "suppression_reason must be set exactly when suppressed" });

/** coverage.json: operational totals by group. */
export const Coverage = z.strictObject({
  ...fileHeader,
  outlets_monitored: count,
  outlets_with_sources: count,
  outlets_contributing: count,
  groups: z.array(GroupCoverage),
});

/** outlets.json: the monitored cohort as a plain list. No per-outlet figures, by policy. */
export const MonitoredOutlet = z.strictObject({
  slug: z.string().regex(/^[a-z0-9-]+$/),
  name: z.string().min(1),
  language,
  tier,
  base_url: z.url(),
});

export const Outlets = z.strictObject({
  ...fileHeader,
  outlets: z.array(MonitoredOutlet),
});

/** Pooled extraction health for a group. */
export const GroupHealth = z
  .strictObject({
    group: groupKind,
    key: z.string().min(1),
    outlets_contributing: count.nullable(),
    suppressed: z.boolean(),
    suppression_reason: suppressionReason.nullable(),
    status: health.nullable(),
    sample_size: count.nullable(),
    median_body_chars: z.number().nonnegative().nullable(),
    short_bodies: count.nullable(),
    extract_errors: count.nullable(),
  })
  .refine((g) => g.suppressed === (g.status === null) && g.suppressed === (g.outlets_contributing === null) && g.suppressed === (g.suppression_reason !== null), {
    message: "status and outlets_contributing must be null exactly when suppressed",
  });

/** extraction-health.json: thresholds used, and pooled health per group. */
export const ExtractionHealth = z.strictObject({
  ...fileHeader,
  window_snapshots: count,
  short_ratio: z.number().positive(),
  min_body_chars: count,
  degraded_at: z.number().min(0).max(1),
  failing_at: z.number().min(0).max(1),
  groups: z.array(GroupHealth),
});

export const VolumePoint = z.strictObject({
  date: calendarDate,
  snapshots: count,
  articles_first_seen: count,
});

/** capture-volume.json: daily series, Bangladesh local days, gaps zero-filled. */
export const CaptureVolume = z
  .strictObject({
    ...fileHeader,
    interval: z.literal("day"),
    timezone: z.literal("Asia/Dhaka"),
    suppressed: z.boolean(),
    series: z.array(VolumePoint),
  })
  .refine((v) => !v.suppressed || v.series.length === 0, { message: "suppressed series must be empty" });

export const FILES = {
  "meta.json": Meta,
  "coverage.json": Coverage,
  "outlets.json": Outlets,
  "extraction-health.json": ExtractionHealth,
  "capture-volume.json": CaptureVolume,
} as const;

export type FileName = keyof typeof FILES;
export type Meta = z.infer<typeof Meta>;
export type Coverage = z.infer<typeof Coverage>;
export type GroupCoverage = z.infer<typeof GroupCoverage>;
export type Outlets = z.infer<typeof Outlets>;
export type MonitoredOutlet = z.infer<typeof MonitoredOutlet>;
export type ExtractionHealth = z.infer<typeof ExtractionHealth>;
export type GroupHealth = z.infer<typeof GroupHealth>;
export type CaptureVolume = z.infer<typeof CaptureVolume>;
export type Health = z.infer<typeof health>;
export type Tier = z.infer<typeof tier>;
export type Language = z.infer<typeof language>;
