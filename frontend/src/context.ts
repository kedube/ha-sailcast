/** What the views need from the panel: its data, formatting and actions. */
import type { TemplateResult } from "lit";

import type { Api } from "./api";
import { ms, type Formatter } from "./format";
import type { Translate } from "./text";
import type {
  Boat,
  Day,
  DayHours,
  Forecast,
  HomeAssistant,
  PlannedList,
  PlannedSail,
  SailCastConfig,
  Sailor,
  Spot,
  Window,
} from "./types";

export interface Actions {
  /** Open the day view on a day of the week. */
  openDay(index: number): void;
  /** Add a window to a calendar, or show it if it's in one already. */
  openWindow(day: number, window: number): void;
  openPlanned(sail: PlannedSail): void;
  removePlanned(sail: PlannedSail): void;
  openAuto(sailor: string): void;
  /** Change the sailor's hours on a day of the week, for that date only. */
  openHours(index: number): void;
  /** Go back to the sailor's usual hours on a day of the week. */
  resetHours(index: number): void;
  editSpot(id?: string): void;
  editSailor(id?: string): void;
  editBoat(id?: string): void;
  setCalendar(entityId: string): void;
  showTip(target: Element, content: TemplateResult | string): void;
  showTipAt(x: number, y: number, content: TemplateResult | string): void;
  hideTip(): void;
  /** Say briefly that something happened. */
  toast(message: string): void;
  /** Ask the AI for a summary of a day of the week. */
  summarize(index: number): void;
}

export interface Ctx {
  hass: HomeAssistant;
  api: Api;
  fmt: Formatter;
  t: Translate;
  config: SailCastConfig;
  /** The selected sailor's week, once it's loaded. */
  forecast?: Forecast;
  planned?: PlannedList;
  spot?: Spot;
  sailor?: Sailor;
  boat?: Boat;
  /** The day the day view shows, as an index into the week. */
  day: number;
  admin: boolean;
  /** The calendar windows go into unless someone picks another. */
  calendar?: string;
  /** The date whose AI summary is being written, and the last one that failed. */
  aiBusy?: string;
  aiError?: { date: string; text: string };
  act: Actions;
}

/** Return the planned sail that overlaps a window for this boat at this spot. */
export function plannedFor(ctx: Ctx, window: Window): PlannedSail | undefined {
  return ctx.forecast?.planned.find(
    (sail) =>
      sail.boat === ctx.boat?.id &&
      sail.spot === ctx.spot?.id &&
      ms(sail.start) < ms(window.end) &&
      ms(sail.end) > ms(window.start),
  );
}

/** Return whether a day is today, at the spot. */
export function isToday(ctx: Ctx, day: Day): boolean {
  return ctx.forecast?.days[0]?.date === day.date;
}

/** Name a day with its date, such as "Saturday, Nov 7" or "Today, Nov 3". */
export function dayAndDate(ctx: Ctx, day: Day): string {
  return ctx.t("week.day_date", {
    day: isToday(ctx, day) ? ctx.t("week.today") : ctx.fmt.weekday(day.date, "long"),
    date: ctx.fmt.shortDate(day.date),
  });
}

/** Whether this user can change the chosen sailor's hours: admins, or the sailor's own. */
export function canSetHours(ctx: Ctx): boolean {
  const user = ctx.sailor?.user;
  return ctx.admin || (!!user && user === ctx.hass.user?.id);
}

/**
 * A day's hours in words, such as "5 PM to sunset", "Sunrise to sunset" or
 * "Not sailing". In a boat with lights, a missing time is no limit.
 */
export function hoursText(ctx: Ctx, date: string, hours: DayHours | null, lights: boolean): string {
  const { t, fmt } = ctx;
  if (!hours) return t("week.not_sailing");
  if (!hours.start && !hours.end) return t(lights ? "hours.any_time" : "hours.daylight");
  const time = (value: string | null, fallback: string): string =>
    value
      ? fmt.hourOf(date, Number(value.slice(0, 2)) + Number(value.slice(3, 5)) / 60)
      : t(fallback);
  return t("hours.span", {
    start: time(hours.start, lights ? "hours.midnight" : "settings.sunrise"),
    end: time(hours.end, lights ? "hours.midnight" : "settings.sunset"),
  });
}
