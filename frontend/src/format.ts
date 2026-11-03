import type { HomeAssistant } from "./types";

export const FEET_PER_METER = 3.28084;
export const METERS_PER_NAUTICAL_MILE = 1852;
export const KM_PER_MILE = 1.609344;

/** The 16 compass points, as translation keys. */
const COMPASS = [
  "n",
  "nne",
  "ne",
  "ene",
  "e",
  "ese",
  "se",
  "sse",
  "s",
  "ssw",
  "sw",
  "wsw",
  "w",
  "wnw",
  "nw",
  "nnw",
] as const;

/** Home Assistant's weekday keys, Monday first, as profiles store them. */
export const WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

export type Band = "great" | "good" | "fair" | "poor";

/**
 * A time in milliseconds, for comparing. Times come with different offsets
 * (warnings keep their issuer's), so they're never compared as text.
 */
export function ms(iso: string): number {
  return Date.parse(iso);
}

/** How a score reads: 80 and up is great, 60 good, 40 fair, then poor. */
export function band(score: number): Band {
  return score >= 80 ? "great" : score >= 60 ? "good" : score >= 40 ? "fair" : "poor";
}

/** The compass point's translation key for a direction in degrees. */
export function compassKey(degrees: number): string {
  return COMPASS[Math.round((((degrees % 360) + 360) % 360) / 22.5) % 16];
}

/** The local date, hour and minute of a time, in a time zone. */
export interface LocalTime {
  /** As YYYY-MM-DD. */
  date: string;
  hour: number;
  minute: number;
}

const partsFormats = new Map<string, Intl.DateTimeFormat>();

/** Return a time's local date and clock time in a time zone. */
export function localTime(iso: string, zone: string): LocalTime {
  let format = partsFormats.get(zone);
  if (!format) {
    format = new Intl.DateTimeFormat("en-CA", {
      timeZone: zone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    });
    partsFormats.set(zone, format);
  }
  const parts: Record<string, string> = {};
  for (const part of format.formatToParts(new Date(iso))) parts[part.type] = part.value;
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    hour: Number(parts.hour) % 24,
    minute: Number(parts.minute),
  };
}

/** Return a time as hours since local midnight, such as 13.5 for 1:30 PM. */
export function localHours(iso: string, zone: string): number {
  const time = localTime(iso, zone);
  return time.hour + time.minute / 60;
}

/** Return the weekday key ("mon" to "sun") of a YYYY-MM-DD date. */
export function weekdayKey(date: string): (typeof WEEKDAYS)[number] {
  const day = new Date(`${date}T12:00:00Z`).getUTCDay();
  return WEEKDAYS[(day + 6) % 7];
}

const NUMBER_LOCALES: Record<string, string | undefined> = {
  comma_decimal: "en-US",
  decimal_comma: "de",
  space_comma: "fr",
  system: undefined,
};

/**
 * Formats numbers, units and times for one user. Times are shown in the
 * spot's time zone, which is Home Assistant's: sailing times are local to the
 * water, wherever the phone is.
 */
export class Formatter {
  readonly zone: string;
  readonly language: string;
  /** Heights in feet with US units, otherwise meters. */
  readonly feet: boolean;
  readonly fahrenheit: boolean;
  /** Distances in miles with US units, otherwise kilometers. */
  readonly miles: boolean;
  private readonly numberLocale: string | undefined;
  private readonly hour12: boolean | undefined;
  /** Whether times read like "1 PM" rather than "13:00". */
  private readonly twelveHour: boolean;
  private readonly cache = new Map<string, Intl.NumberFormat | Intl.DateTimeFormat>();

  constructor(hass: HomeAssistant) {
    this.zone = hass.config.time_zone;
    this.language = hass.locale?.language ?? hass.language;
    this.feet = hass.config.unit_system.length === "mi";
    this.miles = this.feet;
    this.fahrenheit = hass.config.unit_system.temperature === "°F";
    const numbers = hass.locale?.number_format ?? "language";
    this.numberLocale = numbers in NUMBER_LOCALES ? NUMBER_LOCALES[numbers] : this.language;
    const clock = hass.locale?.time_format ?? "language";
    this.hour12 =
      clock === "12"
        ? true
        : clock === "24"
          ? false
          : clock === "system"
            ? /h1[12]/.test(new Intl.DateTimeFormat().resolvedOptions().hourCycle ?? "")
            : undefined;
    this.twelveHour = Boolean(
      new Intl.DateTimeFormat(this.language, { hour: "numeric", hour12: this.hour12 })
        .resolvedOptions()
        .hourCycle?.startsWith("h1"),
    );
  }

  private numberFormat(digits: number): Intl.NumberFormat {
    const key = `n${digits}`;
    let format = this.cache.get(key) as Intl.NumberFormat | undefined;
    if (!format) {
      format = new Intl.NumberFormat(this.numberLocale, {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      });
      this.cache.set(key, format);
    }
    return format;
  }

  private dateFormat(key: string, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
    let format = this.cache.get(key) as Intl.DateTimeFormat | undefined;
    if (!format) {
      format = new Intl.DateTimeFormat(this.language, options);
      this.cache.set(key, format);
    }
    return format;
  }

  /** A number with a fixed count of decimals. */
  number(value: number, digits = 0): string {
    // Round first, then add 0, so -0.04 reads 0.0 rather than -0.0.
    const scale = 10 ** digits;
    return this.numberFormat(digits).format(Math.round(value * scale) / scale + 0);
  }

  /** A range such as "8–12", or one number when both ends round alike. */
  range(low: number, high: number, digits = 0): string {
    const a = this.number(low, digits);
    const b = this.number(high, digits);
    return a === b ? a : `${a}–${b}`;
  }

  /** A height in the user's units: feet or meters. */
  height(meters: number): number {
    return this.feet ? meters * FEET_PER_METER : meters;
  }

  /** A temperature in the user's units. */
  temperature(celsius: number): number {
    return this.fahrenheit ? (celsius * 9) / 5 + 32 : celsius;
  }

  /** A temperature the user typed, in °C. */
  celsius(value: number): number {
    return this.fahrenheit ? ((value - 32) * 5) / 9 : value;
  }

  /** A distance in the user's units: miles or kilometers. */
  distance(km: number): number {
    return this.miles ? km / KM_PER_MILE : km;
  }

  /** A time of day, such as "1 PM" or "4:53 PM", or "13:00" on a 24-hour clock. */
  clock(iso: string | Date): string {
    const when = typeof iso === "string" ? new Date(iso) : iso;
    if (this.twelveHour && localTime(when.toISOString(), this.zone).minute === 0) {
      return this.dateFormat("hour", {
        hour: "numeric",
        hour12: this.hour12,
        timeZone: this.zone,
      }).format(when);
    }
    return this.dateFormat("clock", {
      hour: "numeric",
      minute: "2-digit",
      hour12: this.hour12,
      timeZone: this.zone,
    }).format(when);
  }

  /** A start and end time, such as "1 PM–4:53 PM". */
  span(start: string, end: string): string {
    return `${this.clock(start)}–${this.clock(end)}`;
  }

  /** An hour of a local date for chart axes, such as "6 AM". */
  hourOf(date: string, hour: number): string {
    return this.clock(this.at(date, hour));
  }

  /** The moment a local date reaches a clock time, in the spot's time zone. */
  at(date: string, hours: number): Date {
    // Start from the UTC moment and correct by the zone's offset then.
    const guess = new Date(`${date}T00:00:00Z`).getTime() + hours * 3_600_000;
    let when = guess;
    for (let step = 0; step < 2; step++) {
      const local = localTime(new Date(when).toISOString(), this.zone);
      const shown =
        new Date(`${local.date}T00:00:00Z`).getTime() +
        (local.hour + local.minute / 60) * 3_600_000;
      when += guess - shown;
    }
    return new Date(when);
  }

  /** A weekday's name, short ("Sat") or long ("Saturday"), for a YYYY-MM-DD date. */
  weekday(date: string, width: "short" | "long" = "short"): string {
    return this.dateFormat(`wd-${width}`, { weekday: width, timeZone: "UTC" }).format(
      new Date(`${date}T12:00:00Z`),
    );
  }

  /** A date's day of the month, such as "7". */
  dayOfMonth(date: string): string {
    return String(Number(date.slice(8, 10)));
  }

  /** A short date, such as "Nov 7". */
  shortDate(date: string): string {
    return this.dateFormat("md", { month: "short", day: "numeric", timeZone: "UTC" }).format(
      new Date(`${date}T12:00:00Z`),
    );
  }

  /** A weekday and date, such as "Saturday, Nov 7". */
  longDate(date: string): string {
    return this.dateFormat("wmd", {
      weekday: "long",
      month: "short",
      day: "numeric",
      timeZone: "UTC",
    }).format(new Date(`${date}T12:00:00Z`));
  }
}
