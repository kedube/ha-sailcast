/**
 * Sentences from the backend's translation keys: why an hour got its rating,
 * and the day's advice. Values arrive in knots, meters and °C, and come out
 * in the user's units and language.
 */
import { compassKey, METERS_PER_NAUTICAL_MILE, ms, type Formatter } from "./format";
import type { Advice, ReadingKind, Reason } from "./types";

export type Translate = (key: string, values?: Record<string, string | number>) => string;

const LEVELS = ["good", "caution", "not_recommended", "dangerous"];

function num(value: unknown): number {
  return typeof value === "number" ? value : Number(value);
}

/** A height with its unit, such as "1.4 ft". */
export function heightText(fmt: Formatter, t: Translate, meters: number): string {
  return t(fmt.feet ? "unit.feet" : "unit.meters", { value: fmt.number(fmt.height(meters), 1) });
}

/** A range of heights with its unit, such as "0.8–1.4 ft". */
export function heightRange(fmt: Formatter, t: Translate, low: number, high: number): string {
  return t(fmt.feet ? "unit.feet" : "unit.meters", {
    value: fmt.range(fmt.height(low), fmt.height(high), 1),
  });
}

/** A temperature with its unit, such as "55 °F". */
export function temperatureText(fmt: Formatter, t: Translate, celsius: number): string {
  return t(fmt.fahrenheit ? "unit.fahrenheit" : "unit.celsius", {
    value: fmt.number(fmt.temperature(celsius)),
  });
}

/** How long ago something was read, such as "12 min ago". */
export function ageText(t: Translate, now: string, time: string): string {
  const minutes = Math.max(0, Math.round((ms(now) - ms(time)) / 60_000));
  if (minutes < 1) return t("age.now");
  return minutes < 60
    ? t("age.minutes", { value: minutes })
    : t("age.hours", { value: Math.round(minutes / 60) });
}

/** Sources asked about the pin itself, whose IDs say nothing to people. */
const AT_PIN = new Set(["kartverket", "worldtides", "model", "nws"]);

/**
 * A spot's saved source, such as "SAN DIEGO (9410170)". Regional sources and
 * those at the pin show their name alone, since their IDs are long codes or
 * positions.
 */
export function savedSourceText(id: string, name: string | null | undefined): string {
  if (id.includes(":") || AT_PIN.has(id)) return name ?? id;
  const code = id.split("_")[0];
  return name ? `${name} (${code})` : code;
}

/** What tide heights are measured from, such as "mean lower low water". */
export function datumText(t: Translate, datum: string | null | undefined): string {
  if (!datum) return t("datum.MLLW");
  const key = `datum.${datum}`;
  const text = t(key);
  return text === key ? datum : text;
}

/** Who took a reading, such as "Buoy 46258" or "Your sensors". */
export function sourceText(t: Translate, kind: ReadingKind, station: string | null): string {
  return t(`reading_source.${kind}`, { id: station ?? "" });
}

// SailCast names MeteoAlarm's warnings itself, as "Yellow wind warning".
const METEOALARM = /^(yellow|orange|red) (.+) warning$/i;

/**
 * An official warning's name in the user's language. Services such as the
 * National Weather Service name their warnings themselves, in English, so
 * those stay as they are; MeteoAlarm's are put together from their level and
 * kind.
 */
export function eventText(t: Translate, event: string): string {
  const match = METEOALARM.exec(event);
  if (!match) return event;
  const kind = `meteoalarm.kind.${match[2].toLowerCase().replace(/ /g, "_")}`;
  const kindText = t(kind);
  if (kindText === kind) return event;
  return t(`meteoalarm.${match[1].toLowerCase()}`, { kind: kindText });
}

/** A position such as "32.715° N, 117.180° W", with the language's compass letters. */
export function positionText(
  fmt: Formatter,
  t: Translate,
  latitude: number,
  longitude: number,
  digits: number,
): string {
  const north = t(latitude >= 0 ? "compass.n" : "compass.s");
  const east = t(longitude >= 0 ? "compass.e" : "compass.w");
  return [
    `${fmt.number(Math.abs(latitude), digits)}° ${north}`,
    `${fmt.number(Math.abs(longitude), digits)}° ${east}`,
  ].join(t("advice.list_separator"));
}

/** A compass point, such as "WSW". */
export function compass(t: Translate, degrees: number): string {
  return t(`compass.${compassKey(degrees)}`);
}

/** One reason for a rating, such as "gusts 23 kt". */
export function reasonText(fmt: Formatter, t: Translate, reason: Reason): string {
  const values = reason.values;
  switch (reason.key) {
    case "wind_over_limit": {
      // Show a decimal when rounding would make it look within the limit.
      const wind = num(values.wind);
      const limit = num(values.limit);
      return t("reason.wind_over_limit", {
        wind: Math.round(wind) <= limit ? fmt.number(wind, 1) : fmt.number(wind),
        limit: fmt.number(limit),
      });
    }
    case "wind":
    case "offshore_wind":
      return t(`reason.${reason.key}`, { wind: fmt.number(num(values.wind)) });
    case "gusts":
      return t("reason.gusts", { gust: fmt.number(num(values.gust)) });
    case "gusty":
      return t("reason.gusty", { spread: fmt.number(num(values.spread)) });
    case "waves":
      return t("reason.waves", { height: heightText(fmt, t, num(values.height)) });
    case "wind_against_flood":
    case "wind_against_ebb":
      return t(`reason.${reason.key}`, { current: fmt.number(num(values.current), 1) });
    case "wind_chill":
      return t("reason.wind_chill", {
        temperature: temperatureText(fmt, t, num(values.temperature)),
      });
    case "visibility":
    case "visibility_measured":
      return t(`reason.${reason.key}`, {
        visibility: fmt.number(num(values.visibility) / METERS_PER_NAUTICAL_MILE, 1),
      });
    case "warning":
      return eventText(t, String(values.event));
    default:
      return t(`reason.${reason.key}`);
  }
}

/**
 * The reasons worth saying, as in the mockup: those that set the rating, then
 * the ones that made it worse, at most three.
 */
export function reasonsText(fmt: Formatter, t: Translate, reasons: Reason[]): string {
  if (!reasons.length) return "";
  const worst = Math.max(...reasons.map((reason) => LEVELS.indexOf(reason.level)));
  const top = reasons.filter(
    (reason) => !reason.modifier && worst > 0 && LEVELS.indexOf(reason.level) === worst,
  );
  const modifiers = reasons.filter((reason) => reason.modifier);
  return [...top, ...modifiers]
    .slice(0, 3)
    .map((reason) => reasonText(fmt, t, reason))
    .join(t("advice.list_separator"));
}

/** One piece of advice as a sentence. */
export function adviceText(fmt: Formatter, t: Translate, advice: Advice): string {
  const values = advice.values;
  switch (advice.key) {
    case "warning":
    case "warning_dangerous":
    case "warning_caution":
      return t(`advice.${advice.key}`, { event: eventText(t, String(values.event)) });
    case "warning_not_recommended":
      return t("advice.warning_not_recommended", {
        event: eventText(t, String(values.event)),
        size: t(`size_noun.${String(values.size)}`),
      });
    case "wind": {
      const trend = values.trend ? t(`advice.trend_${String(values.trend)}`) : "";
      return t("advice.wind", {
        direction: compass(t, num(values.direction)),
        range: fmt.range(num(values.low), num(values.high)),
        trend,
        gust: fmt.number(num(values.gust)),
      });
    }
    case "over_limit_hour":
      return t("advice.over_limit_hour", {
        limit: fmt.number(num(values.limit)),
        time: fmt.clock(String(values.time)),
      });
    case "over_limit":
      return t("advice.over_limit", {
        limit: fmt.number(num(values.limit)),
        start: fmt.clock(String(values.start)),
        end: fmt.clock(String(values.end)),
      });
    case "near_limit":
      return t("advice.near_limit", { limit: fmt.number(num(values.limit)) });
    case "waves":
      return t("advice.waves", { range: heightRange(fmt, t, num(values.low), num(values.high)) });
    case "against_current":
      return t(`advice.against_${String(values.flow)}`, {
        span: fmt.span(String(values.start), String(values.end)),
      });
    case "water":
      return t("advice.water", { temperature: temperatureText(fmt, t, num(values.temperature)) });
    case "rain":
      return t("advice.rain", { chance: fmt.number(num(values.chance)) });
    case "rain_visibility":
      return t("advice.rain_visibility", {
        chance: fmt.number(num(values.chance)),
        visibility: fmt.number(num(values.visibility) / METERS_PER_NAUTICAL_MILE, 1),
      });
    case "tides": {
      const events = values.events as { time: string; height: number; high: boolean }[];
      const text = events
        .map((event) =>
          t(event.high ? "advice.high_tide" : "advice.low_tide", {
            time: fmt.clock(event.time),
            height: heightText(fmt, t, event.height),
          }),
        )
        .join(t("advice.list_separator"));
      return t("advice.tides", { tides: text.charAt(0).toUpperCase() + text.slice(1) });
    }
    case "sunset":
      return t("advice.sunset", { time: fmt.clock(String(values.time)) });
    default:
      return t(`advice.${advice.key}`);
  }
}
