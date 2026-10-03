import type { Locale } from "./ui.ts";

const TZ = "Asia/Dhaka";
const intlLocale = (l: Locale) => (l === "bn" ? "bn-BD" : "en-GB");

/** Integers with locale digits: ১,০০২ in bn, 1,002 in en. */
export function num(l: Locale, n: number): string {
  return new Intl.NumberFormat(intlLocale(l), { maximumFractionDigits: 0 }).format(n);
}

export function pct(l: Locale, r: number): string {
  const digits = r > 0 && r < 0.1 ? 1 : 0;
  return new Intl.NumberFormat(intlLocale(l), {
    style: "percent",
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(r);
}

export function date(l: Locale, iso: string): string {
  return new Intl.DateTimeFormat(intlLocale(l), { day: "numeric", month: "long", year: "numeric", timeZone: TZ }).format(
    new Date(iso),
  );
}

export function dateTime(l: Locale, iso: string): string {
  return new Intl.DateTimeFormat(intlLocale(l), {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: TZ,
  }).format(new Date(iso)) + (l === "bn" ? " (বাংলাদেশ সময়)" : " BST");
}

export function monthName(l: Locale, year: number, month: number, style: "long" | "short" = "long"): string {
  return new Intl.DateTimeFormat(intlLocale(l), { month: style, year: "numeric", timeZone: "UTC" }).format(
    new Date(Date.UTC(year, month, 1)),
  );
}

export function weekdayInitials(l: Locale): string[] {
  // Saturday-first week, as printed on Bangladeshi calendars.
  const f = new Intl.DateTimeFormat(intlLocale(l), { weekday: "narrow", timeZone: "UTC" });
  return [0, 1, 2, 3, 4, 5, 6].map((i) => f.format(new Date(Date.UTC(2026, 0, 3 + i)))); // 3 Jan 2026 is a Saturday
}

/** Today's calendar date in Dhaka, YYYY-MM-DD. */
export function dhakaDate(iso: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(new Date(iso));
}
