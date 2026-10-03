/**
 * Shared primitives for the data contract between pipeline/ (writer) and web/ (reader).
 *
 * Kept flat and boring on purpose: every schema here maps 1:1 to a pydantic model in
 * pipeline/src/tw/export.py, and should stay mechanically translatable into Python types.
 * Change both sides together and bump SCHEMA_VERSION.
 */
import { z } from "zod";

export const SCHEMA_VERSION = "1.0.0" as const;
export const DATASET_DIR = "v1" as const;

export const schemaVersion = z.literal(SCHEMA_VERSION);

/** ISO 8601 UTC timestamp as the pipeline writes it, e.g. 2026-09-23T20:53:43.834464Z */
export const timestamp = z.iso.datetime({ offset: true });

/** Calendar date, e.g. 2026-09-24 */
export const calendarDate = z.iso.date();

export const count = z.int().nonnegative();

/** A proportion in [0, 1]; null when the denominator is zero (nothing to measure yet). */
export const rate = z.number().min(0).max(1).nullable();

export const language = z.enum(["bn", "en"]);

export const tier = z.enum(["bangla_mass", "bangla_other", "english", "online_native", "state_wire", "independent"]);

export const suppressionReason = z.enum(["small_group", "complementary"]);

export const health = z.enum(["ok", "degraded", "failing", "no_data"]);

/** Fields every file carries. */
export const fileHeader = {
  schema_version: schemaVersion,
  generated_at: timestamp,
};
