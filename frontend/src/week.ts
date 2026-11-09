/**
 * The week view: the AI briefing with AI on, the week's best sailing window,
 * this hour's forecast and any official warnings, then a seven-day calendar
 * with sailing windows drawn as events. Its columns show dawn to dusk. In a
 * boat with navigation lights they hold the whole day, opening on dawn to dusk
 * and scrolling to the rest.
 */
import { html, nothing, svg, type TemplateResult } from "lit";

import { briefingCard } from "./briefing";
import { canSetHours, dayAndDate, hoursText, isToday, plannedFor, type Ctx } from "./context";
import { band, localHours, localTime, ms, WEEKDAYS } from "./format";
import { arrow, dial, icon, ring, weather, type IconName } from "./glyphs";
import {
  ageText,
  compass,
  eventText,
  heightRange,
  heightText,
  reasonsText,
  savedSourceText,
  sourceText,
  temperatureText,
} from "./text";
import type { Day, Hour, Level, PlannedSail, SizeClass, Window } from "./types";

export const SIZES: SizeClass[] = ["dinghy", "small_keelboat", "cruiser", "large_cruiser"];
const HOUR_MS = 3_600_000;
/** A week that starts on a Monday, to name weekdays in the user's language. */
const MONDAY_WEEK: Record<string, string> = Object.fromEntries(
  WEEKDAYS.map((day, index) => [day, `2026-11-0${2 + index}`]),
);
/** The calendar's track height in pixels, for deciding how much a window can show. */
const TRACK = 300;

/** The icon for a window: added to a calendar, added automatically, or neither. */
export function addIcon(sail?: PlannedSail): IconName {
  return sail ? (sail.auto ? "calSync" : "calCheck") : "calPlus";
}

export function addText(ctx: Ctx, sail?: PlannedSail): string {
  return ctx.t(sail ? (sail.auto ? "planned.added_auto" : "planned.in_calendar") : "planned.add");
}

/** A planned sail's forecast now, in a few words. */
export function plannedStatus(ctx: Ctx, sail: PlannedSail): string {
  const { t, fmt } = ctx;
  const status = sail.status;
  if (status.rating === null || status.score === null) return t("planned.status_none");
  if (status.rating !== "good") {
    const why = reasonsText(fmt, t, status.reasons);
    return t(why ? "planned.status_rating_why" : "planned.status_rating", {
      rating: t(`level_word.${status.rating}`),
      why,
    });
  }
  if (status.score < 60) {
    return t("planned.status_score", { score: status.score, was: sail.score ?? "–" });
  }
  return t(sail.auto ? "planned.status_auto" : "planned.status_ok", {
    band: t(`band_word.${band(status.score)}`),
    score: status.score,
  });
}

/** The hours of a day, at the spot. */
export function hoursOf(ctx: Ctx, day: Day): Hour[] {
  const zone = ctx.fmt.zone;
  return (ctx.forecast?.hours ?? []).filter((hour) => localTime(hour.time, zone).date === day.date);
}

/** Whether an hour is over. */
export function isPast(ctx: Ctx, hour: Hour): boolean {
  return Date.parse(hour.time) + HOUR_MS <= Date.parse(ctx.forecast?.now ?? "");
}

/** The class that shades an hour: its rating if it isn't good, otherwise its score. */
function shade(hour: Hour): string {
  if (hour.rating !== "good") return `h-${hour.rating}`;
  const score = hour.score ?? 0;
  return score >= 60 ? "h-good" : score >= 40 ? "h-fair" : "h-poor";
}

export function weekView(ctx: Ctx): TemplateResult {
  const forecast = ctx.forecast;
  if (!forecast) return html``;
  const windows = forecast.days.flatMap((day, index) =>
    day.windows.map((window, number) => ({ day, index, window, number })),
  );
  const best = [...windows].sort(
    (a, b) => b.window.score - a.window.score || b.window.hours - a.window.hours,
  )[0];
  return html`
    ${briefingCard(ctx)}
    <div class="top">
      ${hero(ctx, best, windows[0])}
      <div class="side">${nowCard(ctx)} ${warningsCard(ctx)}</div>
    </div>
    ${calendarCard(ctx)}
  `;
}

interface Found {
  day: Day;
  index: number;
  window: Window;
  number: number;
}

function dayName(ctx: Ctx, day: Day, width: "short" | "long" = "long"): string {
  return isToday(ctx, day) ? ctx.t("week.today") : ctx.fmt.weekday(day.date, width);
}

function hero(ctx: Ctx, best: Found | undefined, next: Found | undefined): TemplateResult {
  const { t, fmt } = ctx;
  const who = `${ctx.sailor?.name} · ${ctx.boat?.name}`;
  if (!best) {
    const top = [...(ctx.forecast?.days ?? [])]
      .filter((day) => day.score !== null)
      .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))[0];
    return html`<section class="hero" aria-label=${t("week.best_label")}>
      <div class="hero-main">
        <span class="eyebrow">${t("week.best_eyebrow", { who })}</span>
        <div class="hero-time hero-none">${t("week.no_window")}</div>
        <p class="hero-note">
          ${
            top
              ? t("week.best_day", {
                  day: fmt.weekday(top.date, "long"),
                  score: top.score ?? 0,
                  band: t(`band_word.${band(top.score ?? 0)}`),
                })
              : nothing
          }
          ${t("week.window_rule")}
        </p>
      </div>
      <div class="hero-score">${ring(top?.score ?? null)}</div>
    </section>`;
  }
  const { day, index, window, number } = best;
  const sail = plannedFor(ctx, window);
  const summary = day.summary;
  const tides = day.tides.filter(
    (turn) => ms(turn.time) >= ms(window.start) && ms(turn.time) <= ms(window.end),
  );
  return html`<section class="hero" aria-label=${t("week.best_label")}>
    ${heroWave(ctx, day, window)}
    <div class="hero-main">
      <span class="eyebrow">${t("week.best_eyebrow", { who })}</span>
      <div class="hero-day">${dayAndDate(ctx, day)} · ${ctx.spot?.name}</div>
      <div class="hero-time">${fmt.span(window.start, window.end)}</div>
      <div class="hero-facts">
        ${
          window.wind_low !== null && window.wind_high !== null
            ? html`<span
                >${arrow(window.direction ?? 0, 15)}${compass(t, window.direction ?? 0)}
                ${fmt.range(window.wind_low, window.wind_high)} ${t("unit.knots_short")}</span
              >`
            : nothing
        }
        ${
          window.gust !== null
            ? html`<span>${t("week.gusts", { gust: fmt.number(window.gust) })}</span>`
            : nothing
        }
        ${
          summary?.waves
            ? html`<span
                >${icon("waves")}${heightRange(fmt, t, summary.waves[0], summary.waves[1])}</span
              >`
            : nothing
        }
        ${
          summary?.temperature
            ? html`<span
                >${weather(summary.weather_code)}${fmt.range(
                  fmt.temperature(summary.temperature[0]),
                  fmt.temperature(summary.temperature[1]),
                )}${fmt.fahrenheit ? "°F" : "°C"}</span
              >`
            : nothing
        }
        ${tides.map(
          (turn) =>
            html`<span
              >${icon(turn.high ? "tideUp" : "tideDown")}${t(turn.high ? "week.high" : "week.low", {
                time: fmt.clock(turn.time),
              })}</span
            >`,
        )}
      </div>
      <div class="hero-actions">
        <button type="button" class="btn btn-sea" @click=${() => ctx.act.openWindow(index, number)}>
          ${icon(addIcon(sail))}${addText(ctx, sail)}
        </button>
        <button type="button" class="btn btn-sea-ghost" @click=${() => ctx.act.openDay(index)}>
          ${
            isToday(ctx, day)
              ? t("week.open_today")
              : t("week.open_day", { day: fmt.weekday(day.date, "long") })
          }${icon("chevR")}
        </button>
      </div>
      ${
        next && next.window !== window
          ? html`<div class="hero-next">
              ${
                isToday(ctx, next.day)
                  ? t("week.next_window_today", {
                      span: fmt.span(next.window.start, next.window.end),
                    })
                  : t("week.next_window", {
                      day: fmt.weekday(next.day.date, "long"),
                      span: fmt.span(next.window.start, next.window.end),
                    })
              }
            </div>`
          : nothing
      }
    </div>
    <div class="hero-score">
      ${ring(window.score, t("week.score_label", { score: window.score }))}
      <span>${t(`band.${band(window.score)}`)}</span>
    </div>
  </section>`;
}

/** Smooth a line through points with Catmull-Rom curves. */
export function smoothPath(points: [number, number][]): string {
  if (!points.length) return "";
  let d = `M${points[0][0].toFixed(1)},${points[0][1].toFixed(1)}`;
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i - 1] ?? points[i];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[i + 2] ?? p2;
    d +=
      `C${(p1[0] + (p2[0] - p0[0]) / 6).toFixed(1)},${(p1[1] + (p2[1] - p0[1]) / 6).toFixed(1)} ` +
      `${(p2[0] - (p3[0] - p1[0]) / 6).toFixed(1)},${(p2[1] - (p3[1] - p1[1]) / 6).toFixed(1)} ` +
      `${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
  }
  return d;
}

/**
 * The day's tide curve behind the best window, with the window as the
 * brighter band, and a softer copy three hours ahead behind it. A spot
 * without tides gets a gentle swell.
 */
function heroWave(ctx: Ctx, day: Day, window: Window): TemplateResult {
  const width = 1000;
  const height = 100;
  const hours = hoursOf(ctx, day);
  const all = ctx.forecast?.hours ?? [];
  const first = hours.length ? all.indexOf(hours[0]) : -1;
  const tide = (k: number): number => {
    const hour = all[Math.min(Math.max(first + k, 0), all.length - 1)];
    return hour?.tide_height ?? Math.sin((k / 24) * Math.PI * 4) * 0.5;
  };
  const values = Array.from({ length: 28 }, (_, k) => tide(k));
  const low = Math.min(...values);
  const high = Math.max(...values);
  const y = (value: number, amplitude: number, lift: number): number =>
    height - 8 - lift - ((value - low) / Math.max(0.5, high - low)) * (height - 38) * amplitude;
  const line = smoothPath(
    Array.from({ length: 25 }, (_, k) => [(k / 24) * width, y(tide(k), 1, 0)] as [number, number]),
  );
  const back = smoothPath(
    Array.from(
      { length: 25 },
      (_, k) => [(k / 24) * width, y(tide(k + 3), 0.8, 16)] as [number, number],
    ),
  );
  const close = `L${width},${height}L0,${height}Z`;
  const zone = ctx.fmt.zone;
  const a = (localHours(window.start, zone) / 24) * width;
  const b = (localHours(window.end, zone) / 24) * width;
  return html`<svg
    class="hero-wave"
    viewBox="0 0 ${width} ${height}"
    preserveAspectRatio="none"
    aria-hidden="true"
  >
    ${svg`<defs><clipPath id="hw-clip"><rect x=${a.toFixed(1)} y="0" width=${(b - a).toFixed(1)} height=${height}></rect></clipPath></defs>
    <path d="${back}${close}" fill="var(--sc-sea-wave3)"></path>
    <path d="${line}${close}" fill="var(--sc-sea-wave)"></path>
    <path d="${line}${close}" fill="var(--sc-sea-wave2)" clip-path="url(#hw-clip)"></path>
    <path d=${line} fill="none" stroke="var(--sc-sea-wave2)" stroke-width="2" vector-effect="non-scaling-stroke"></path>`}
  </svg>`;
}

/**
 * What's read at the spot now: each value from its freshest reading, with who
 * read it and when, and this hour's forecast for anything not read.
 */
function nowCard(ctx: Ctx): TemplateResult {
  const { t, fmt } = ctx;
  const forecast = ctx.forecast;
  const now = Date.parse(forecast?.now ?? "");
  const hour = forecast?.hours.find(
    (item) => Date.parse(item.time) <= now && now < Date.parse(item.time) + HOUR_MS,
  );
  if (!forecast || !hour) return html``;
  const read = forecast.readings.fields;
  const reading = forecast.readings.sources.length > 0;
  const from = (key: string): TemplateResult | typeof nothing => {
    const item = read[key];
    if (item) {
      return html`<span class="src"
        >${sourceText(t, item.kind, item.station)} · ${ageText(t, forecast.now, item.time)}</span
      >`;
    }
    return reading ? html`<span class="src">${t("now.forecast")}</span>` : nothing;
  };
  const wind = read.wind?.value ?? hour.wind;
  const direction = read.wind_direction?.value ?? hour.direction;
  const gust = read.gust?.value ?? (read.wind ? null : hour.gust);
  const waves = read.wave_height?.value ?? hour.wave_height;
  const period = read.wave_height ? read.wave_period?.value : hour.wave_period;
  const water = read.water_temperature?.value ?? hour.water_temperature;
  const air = read.temperature?.value ?? hour.temperature;
  const visibility = read.visibility?.value;
  return html`<section class="card">
    <div class="eyebrow">${t(read.wind ? "now.title" : "now.forecast_title")}</div>
    <div class="now-main">
      ${dial(direction)}
      <div>
        <div class="now-big">${fmt.number(wind)}<small>${t("unit.knots_short")}</small></div>
        <div class="now-sub">
          ${t(gust === null ? "now.sub_no_gust" : "now.sub", {
            direction: compass(t, direction),
            gust: fmt.number(gust ?? 0),
            time: fmt.clock(read.wind?.time ?? hour.time),
          })}
        </div>
        ${read.wind ? html`<div class="now-sub">${from("wind")}</div>` : nothing}
      </div>
    </div>
    <dl class="kv">
      ${
        waves !== null
          ? html`<dt>${t("now.waves")}</dt>
              <dd>
                ${
                  period
                    ? t("now.waves_every", {
                        height: heightText(fmt, t, waves),
                        // Short chop on sheltered water needs a decimal.
                        period: fmt.number(period, period < 5 ? 1 : 0),
                      })
                    : heightText(fmt, t, waves)
                }
                ${from("wave_height")}
              </dd>`
          : nothing
      }
      ${
        water !== null
          ? html`<dt>${t("now.water")}</dt>
              <dd>${temperatureText(fmt, t, water)} ${from("water_temperature")}</dd>`
          : nothing
      }
      ${
        air !== null
          ? html`<dt>${t("now.air")}</dt>
              <dd>${temperatureText(fmt, t, air)} ${from("temperature")}</dd>`
          : nothing
      }
      ${
        visibility !== undefined
          ? html`<dt>${t("now.visibility")}</dt>
              <dd>
                ${
                  // Airports report ten statute miles or more as 10+.
                  visibility >= 16_000
                    ? t("now.visibility_good")
                    : t("now.visibility_value", { value: fmt.number(visibility / 1852, 1) })
                }
                ${from("visibility")}
              </dd>`
          : nothing
      }
      ${
        hour.tide_height !== null
          ? html`<dt>${t("now.tide")}</dt>
              <dd>
                ${t(hour.tide_rising ? "now.tide_rising" : "now.tide_falling", {
                  height: heightText(fmt, t, hour.tide_height),
                })}${
                  ctx.forecast?.tide?.provider === "model"
                    ? html` <span class="src">${t("now.tide_rough")}</span>`
                    : nothing
                }
              </dd>`
          : nothing
      }
    </dl>
    <p class="small">
      ${t(reading ? "now.note" : ctx.admin ? "now.note_no_sources_admin" : "now.note_no_sources")}
    </p>
  </section>`;
}

/** Who a spot's warnings come from, such as "National Weather Service, marine zone PZZ740". */
export function warningSource(ctx: Ctx): string | null {
  const forecast = ctx.forecast;
  const saved = forecast?.sources.marine_zone;
  const warnings = forecast?.warnings;
  if (!saved || !warnings) return null;
  const key = warnings.provider === "nws" && warnings.at_pin ? "nws_pin" : warnings.provider;
  return ctx.t(`sources.warnings_by.${key}`, {
    zone: savedSourceText(saved.id, saved.name),
    services: warnings.services.join(ctx.t("advice.list_separator")),
  });
}

/** Official warnings this week. */
function warningsCard(ctx: Ctx): TemplateResult {
  const { t, fmt } = ctx;
  const spot = ctx.spot;
  const now = ctx.forecast?.now ?? "";
  // Warnings still in effect or still to come.
  const alerts = (ctx.forecast?.alerts ?? []).filter((alert) => ms(alert.end) > ms(now));
  const source = warningSource(ctx);
  return html`<section class="card">
    <div class="eyebrow">${t("warnings.title")}</div>
    ${
      alerts.length
        ? alerts.map(
            (alert) =>
              html`<div class="warn-status on">
                ${icon("flag")}
                <span
                  >${eventText(t, alert.event)}${alert.issued && alert.headline ? ` · ${alert.headline}` : ""}
                  <small
                    >${
                      ms(alert.start) <= ms(now)
                        ? t("warnings.until", {
                            end: `${fmt.weekday(localTime(alert.end, fmt.zone).date)} ${fmt.clock(alert.end)}`,
                          })
                        : t("warnings.from", {
                            start: `${fmt.weekday(localTime(alert.start, fmt.zone).date)} ${fmt.clock(alert.start)}`,
                            end: `${fmt.weekday(localTime(alert.end, fmt.zone).date)} ${fmt.clock(alert.end)}`,
                          })
                    }${
                      alert.issued
                        ? ` · ${t("warnings.issued", {
                            time: `${fmt.weekday(localTime(alert.issued, fmt.zone).date)} ${fmt.clock(alert.issued)}`,
                            issuer: alert.issuer ?? "",
                          })}`
                        : ""
                    }</small
                  >${alert.details ? html`<small class="warn-text">${alert.details}</small>` : nothing}</span
                >
              </div>`,
          )
        : html`<div class="warn-status ok">
            ${icon("ok")}<span>${t(spot?.marine_zone ? "warnings.none" : "warnings.no_zone")}</span>
          </div>`
    }
    ${alerts.length ? html`<p class="small">${t("warnings.meaning")}</p>` : nothing}
    ${
      alerts.length && ctx.forecast?.warnings?.provider === "eccc"
        ? html`<p class="small">${t("warnings.no_end")}</p>`
        : nothing
    }
    <p class="small">${source ?? t("warnings.no_zone_hint")}</p>
    ${
      ctx.forecast?.warnings?.provider === "meteoalarm"
        ? html`<p class="small">
            ${t("warnings.meteoalarm_note")}
            <a href="https://meteoalarm.org/en/live/" target="_blank" rel="noreferrer"
              >www.meteoalarm.org</a
            >
          </p>`
        : nothing
    }
  </section>`;
}

/** Hours from a day's local midnight to a time, such as 24 for the midnight that ends it. */
function sinceMidnight(iso: string, date: string, zone: string): number {
  const time = localTime(iso, zone);
  const hours = time.hour + time.minute / 60;
  return time.date > date ? hours + 24 : time.date < date ? hours - 24 : hours;
}

/**
 * The calendar's hours, counted from midnight. It shows from an hour before
 * the week's earliest sunrise to an hour after its latest sunset at once
 * (`start` to `end`). A boat with navigation lights lays out the whole day
 * around them (`first` to `last`), to scroll through, and opens at `start`,
 * or at the earliest window if that starts sooner. Without lights, only the
 * hours shown are laid out.
 */
export function calendarHours(
  days: Day[],
  zone: string,
  lights: boolean,
): { first: number; last: number; start: number; end: number; open: number } {
  const since = (iso: string, day: Day): number => sinceMidnight(iso, day.date, zone);
  const start = Math.max(
    0,
    Math.floor(Math.min(...days.map((day) => since(day.sunrise, day)))) - 1,
  );
  const end = Math.max(
    start + 1,
    Math.min(24, Math.ceil(Math.max(...days.map((day) => since(day.sunset, day)))) + 1),
  );
  if (!lights) return { first: start, last: end, start, end, open: start };
  const windows = days.flatMap((day) => day.windows.map((window) => since(window.start, day)));
  return {
    first: 0,
    last: 24,
    start,
    end,
    open: Math.max(0, Math.floor(Math.min(start, ...windows))),
  };
}

/**
 * Scroll the calendar's hours to where they open, once for each week shown.
 * `data-open` is how far along the laid-out hours that is. Hours the other
 * layout hides wait until they're shown.
 */
export function placeCalendar(root: ParentNode): void {
  for (const hours of root.querySelectorAll<HTMLElement>("[data-shown]")) {
    const shown = hours.dataset.shown ?? "";
    if (hours.dataset.placed === shown || !hours.clientWidth) continue;
    const at = Number(hours.dataset.open);
    if (hours.classList.contains("cal-hours")) hours.scrollTop = at * hours.scrollHeight;
    else hours.scrollLeft = at * hours.scrollWidth;
    hours.dataset.placed = shown;
  }
}

function calendarCard(ctx: Ctx): TemplateResult {
  const { t, fmt } = ctx;
  const forecast = ctx.forecast!;
  const sailor = ctx.sailor!;
  const zone = fmt.zone;
  const { first, last, start, end, open } = calendarHours(forecast.days, zone, forecast.lights);
  const span = end - start;
  const laid = last - first;
  // Places along the hours laid out.
  const pos = (hour: number): string => Math.min(1, Math.max(0, (hour - first) / laid)).toFixed(4);
  const date = forecast.days[0].date;
  const gutter = [];
  for (let hour = first + 1; hour < last; hour++) {
    if (hour % 2 === 0) {
      gutter.push(html`<span style="--t:${pos(hour)}">${fmt.hourOf(date, hour)}</span>`);
    }
  }
  const ticks: TemplateResult[] = [];
  for (let hour = first; hour <= last; hour++) {
    if (hour % 3 === 0 || hour === last) {
      ticks.push(html`<span style="--s:${pos(hour)}">${fmt.hourOf(date, hour)}</span>`);
    }
  }
  // The week on show, so its hours open in the right place once.
  const shown = [forecast.spot, forecast.sailor, forecast.boat, date].join(" ");
  const opening = ((open - first) / laid).toFixed(4);
  const tracks = forecast.days.map((day, index) => dayTrack(ctx, day, index, pos, span));
  const anyOff = forecast.hours.some(
    (hour) => (hour.daylight || forecast.lights) && !hour.available,
  );
  const auto = sailor.auto_calendar;
  const planned = [...forecast.planned].sort((a, b) => ms(a.start) - ms(b.start));
  return html`<section class="card cal-card" aria-labelledby="week-cal-h">
    <div class="cal-head">
      <h2 id="week-cal-h">${t("week.calendar_title", { spot: ctx.spot?.name ?? "" })}</h2>
      <p class="small">
        ${t("week.calendar_sub", {
          sailor: sailor.name,
          skill: t(`skill_word.${sailor.skill}`),
          boat: ctx.boat?.name ?? "",
        })}
      </p>
    </div>
    <div class="cal-tools" aria-label=${t("week.your_calendars")}>
      ${
        ctx.admin
          ? html`<button
              type="button"
              class="auto-chip ${auto ? "on" : ""}"
              @click=${() => ctx.act.openAuto(sailor.id)}
            >
              ${icon("calSync")}
              <span
                >${
                  auto
                    ? t("auto.on_summary", { summary: autoSummary(ctx, auto) })
                    : t("auto.off_chip")
                }</span
              >
              <b>${t(auto ? "auto.change" : "auto.set_up")}</b>
            </button>`
          : auto
            ? html`<span class="auto-chip on"
                >${icon("calSync")}<span
                  >${t("auto.on_summary", { summary: autoSummary(ctx, auto) })}</span
                ></span
              >`
            : nothing
      }
      ${planned.map(
        (sail) =>
          html`<button
            type="button"
            class="pl ${sail.status.worse ? "worse" : ""}"
            @click=${() => ctx.act.openPlanned(sail)}
          >
            ${icon(sail.status.worse ? "calAlert" : addIcon(sail))}
            <span
              ><b
                >${fmt.weekday(localTime(sail.start, zone).date)}
                ${fmt.span(sail.start, sail.end)}</b
              >
              · ${ctx.config.spots.find((spot) => spot.id === sail.spot)?.name ?? ""} ·
              ${plannedStatus(ctx, sail)}</span
            >
          </button>`,
      )}
    </div>
    <div class="cal-wrap">
      <div class="cal" style="--span:${span};--laid:${laid}">
        ${forecast.days.map((day, index) =>
          dayColumn(ctx, day, index, tracks[index], ticks, shown, opening),
        )}
        <div class="cal-hours" data-shown=${shown} data-open=${opening}>
          <div class="cal-day">
            <div class="cal-gutter" aria-hidden="true">${gutter}</div>
            ${tracks.map((track) => html`<div class="cd-track">${track}</div>`)}
          </div>
        </div>
      </div>
    </div>
    <div class="legend">
      <span class="lg"><i class="sw sw-pill"></i>${t("legend.window")}</span>
      <span class="lg">${icon("calCheck")}${t("legend.in_calendar")}</span>
      <span class="lg">${icon("calSync")}${t("legend.added_auto")}</span>
      ${(
        [
          ["h-good", "legend.good"],
          ["h-fair", "legend.fair"],
          ["h-poor", "legend.poor"],
          ["h-caution", "level.caution"],
          ["h-not_recommended", "level.not_recommended"],
          ["h-dangerous", "level.dangerous"],
        ] as const
      ).map(([cls, key]) => html`<span class="lg"><i class="sw ${cls}"></i>${t(key)}</span>`)}
      ${
        anyOff
          ? html`<span class="lg"
              ><i class="sw h-poor off"></i>${t("legend.off", { sailor: sailor.name })}</span
            >`
          : nothing
      }
      <span class="lg"><i class="sw night"></i>${t("legend.dark")}</span>
      <span class="lg"><i class="sw past"></i>${t("legend.past")}</span>
    </div>
    <p class="legend-note small">
      ${t("legend.sizes", { sailor: sailor.name })}
      ${SIZES.map(
        (size, index) =>
          html`${index ? " · " : ""}<b>${t(`size_letter.${size}`)}</b> ${t(`size_class.${size}`)}`,
      )}.
      ${t("legend.mine", { boat: ctx.boat?.name ?? "" })}
    </p>
  </section>`;
}

/** A sailor's automatic adding in a few words. */
export function autoSummary(
  ctx: Ctx,
  auto: { calendar: string; days: string[]; min_score: number; ahead: number },
): string {
  const { t } = ctx;
  const calendar = ctx.config.calendars.find((item) => item.entity_id === auto.calendar);
  return t("auto.summary", {
    days: daysText(ctx, auto.days),
    score: auto.min_score,
    ahead: t(`ahead_word.${auto.ahead}`),
    calendar: calendar ? `${calendar.name} (${calendar.via})` : auto.calendar,
  });
}

/** Days such as "weekends", "weekdays", "every day" or "Sat, Sun". */
export function daysText(ctx: Ctx, days: string[]): string {
  const { t, fmt } = ctx;
  const set = new Set(days);
  if (set.size === 7) return t("days.every_day");
  if (set.size === 2 && set.has("sat") && set.has("sun")) return t("days.weekends");
  if (set.size === 5 && ["mon", "tue", "wed", "thu", "fri"].every((day) => set.has(day))) {
    return t("days.weekdays");
  }
  return WEEKDAYS.filter((day) => set.has(day))
    .map((day) => fmt.weekday(MONDAY_WEEK[day]))
    .join(t("advice.list_separator"));
}

/**
 * A day's hours on the calendar, midnight to midnight: night, each hour
 * shaded by its rating or score, the windows and the time now. With
 * navigation lights every hour counts, so night is a veil over the hours.
 */
function dayTrack(
  ctx: Ctx,
  day: Day,
  index: number,
  pos: (hour: number) => string,
  span: number,
): TemplateResult[] {
  const { t, fmt } = ctx;
  const zone = fmt.zone;
  const lights = ctx.forecast!.lights;
  const sunrise = sinceMidnight(day.sunrise, day.date, zone);
  const sunset = sinceMidnight(day.sunset, day.date, zone);
  const hours = hoursOf(ctx, day);
  const veil = lights ? "veil" : "";
  const night = [
    html`<div class="seg night dawn ${veil}" style="--s:0;--e:${pos(sunrise)}">
      <span>${icon("sunrise")}${fmt.clock(day.sunrise)}</span>
    </div>`,
    html`<div class="seg night dusk ${veil}" style="--s:${pos(sunset)};--e:1">
      <span>${icon("sunset")}${fmt.clock(day.sunset)}</span>
    </div>`,
  ];
  const shaded = (hour: Hour, a: number, b: number): TemplateResult => {
    const past = isPast(ctx, hour);
    const cls = past ? "past" : `${shade(hour)}${hour.available ? "" : " off"}`;
    return html`<div
      class="seg ${cls}"
      style="--s:${pos(a)};--e:${pos(b)}"
      data-hour=${hour.time}
      @pointerenter=${(event: PointerEvent) =>
        ctx.act.showTip(event.currentTarget as Element, hourTip(ctx, day, hour))}
      @pointerleave=${() => ctx.act.hideTip()}
    ></div>`;
  };
  const segments: TemplateResult[] = [];
  if (lights) {
    for (const hour of hours) {
      const at = sinceMidnight(hour.time, day.date, zone);
      segments.push(shaded(hour, at, at + 1));
    }
    segments.push(...night);
  } else {
    segments.push(night[0]);
    const lit = hours.filter((hour) => hour.daylight);
    const firstLit = lit.length ? localTime(lit[0].time, zone).hour : sunrise;
    if (firstLit > sunrise) {
      segments.push(
        html`<div class="seg twilight" style="--s:${pos(sunrise)};--e:${pos(firstLit)}"></div>`,
      );
    }
    let litEnd = sunrise;
    for (const hour of lit) {
      const at = localTime(hour.time, zone).hour;
      const a = Math.max(at, sunrise);
      const b = Math.min(at + 1, sunset);
      if (b <= a) continue;
      litEnd = b;
      segments.push(shaded(hour, a, b));
    }
    if (sunset > litEnd) {
      segments.push(
        html`<div class="seg twilight" style="--s:${pos(litEnd)};--e:${pos(sunset)}"></div>`,
      );
    }
    segments.push(night[1]);
  }
  const multiple = day.windows.length > 1;
  day.windows.forEach((window, number) => {
    const sail = plannedFor(ctx, window);
    const top = multiple && number === day.best;
    const a = sinceMidnight(window.start, day.date, zone);
    const b = sinceMidnight(window.end, day.date, zone);
    const pixels = ((b - a) / span) * TRACK;
    const label = t("week.window_label", {
      day: dayName(ctx, day),
      span: fmt.span(window.start, window.end),
      score: window.score,
      action: addText(ctx, sail),
    });
    segments.push(
      html`<button
        type="button"
        class="pill ${top ? "best" : ""} ${sail ? "added" : ""} ${
          sail?.status.worse ? "worse" : ""
        } ${pixels < 50 ? "short" : ""} ${pixels < 36 ? "tiny" : ""}"
        style="--s:${pos(a)};--e:${pos(b)}"
        aria-label=${label}
        @click=${() => ctx.act.openWindow(index, number)}
        @pointerenter=${(event: PointerEvent) =>
          ctx.act.showTip(event.currentTarget as Element, windowTip(ctx, day, window, sail))}
        @pointerleave=${() => ctx.act.hideTip()}
        @focus=${(event: FocusEvent) =>
          ctx.act.showTip(event.currentTarget as Element, windowTip(ctx, day, window, sail))}
        @blur=${() => ctx.act.hideTip()}
      >
        <span class="pt"
          >${top ? icon("star", "pstar") : nothing}${fmt.span(window.start, window.end)}</span
        >
        <span class="ps">${window.score} · ${t(`band.${band(window.score)}`)}</span>
        <span class="pn">${window.score}</span>
        ${icon(addIcon(sail), "pc")}
      </button>`,
    );
  });
  if (isToday(ctx, day)) {
    segments.push(
      html`<div class="nowline" style="--s:${pos(localHours(ctx.forecast!.now, zone))}"></div>`,
    );
  }
  return segments;
}

/**
 * A day's column: its head, its hours for the narrow layout, which scroll
 * on their own, and the day's conditions. The wide layout puts every day's
 * hours side by side in one scrolling area instead.
 */
function dayColumn(
  ctx: Ctx,
  day: Day,
  index: number,
  track: TemplateResult[],
  ticks: TemplateResult[],
  shown: string,
  open: string,
): TemplateResult {
  const { t, fmt } = ctx;
  const today = isToday(ctx, day);
  const summary = day.summary;
  const best = day.best !== null ? day.windows[day.best] : undefined;
  const status =
    day.score === null
      ? t(day.over ? "week.day_over" : "week.not_sailing_day")
      : t("week.day_score", { score: day.score, band: t(`band_word.${band(day.score)}`) });
  const head = html`<button
    type="button"
    class="cd-head"
    aria-label=${t("week.day_label", {
      day: dayAndDate(ctx, day),
      status,
      best: best
        ? t("week.day_best", { span: fmt.span(best.start, best.end) })
        : t("week.no_window_short"),
    })}
    @click=${() => ctx.act.openDay(index)}
  >
    <span class="cd-wd">${today ? t("week.today_short") : fmt.weekday(day.date)}</span>
    <span class="cd-date">${fmt.dayOfMonth(day.date)}</span>
    <span class="cd-wx"
      >${
        summary?.temperature
          ? html`${weather(summary.weather_code)}<span
                >${fmt.range(
                  fmt.temperature(summary.temperature[0]),
                  fmt.temperature(summary.temperature[1]),
                )}°</span
              >`
          : nothing
      }</span
    >
    <span class="cd-score"
      >${
        day.score === null
          ? html`<span class="cd-off"
              >${t(day.over ? "week.day_over_short" : "week.not_sailing")}</span
            >`
          : html`${ring(day.score)}<span
                ><b>${t(`band.${band(day.score)}`)}</b
                ><small
                  >${
                    day.windows.length
                      ? t(day.windows.length > 1 ? "week.windows" : "week.one_window", {
                          count: day.windows.length,
                        })
                      : t("week.no_window_short")
                  }</small
                ></span
              >`
      }</span
    >
  </button>`;
  let info: TemplateResult = html`<p class="small">${t("week.sunset_passed")}</p>`;
  if (summary) {
    const now = ctx.forecast!.now;
    // The tides still to come while the boat can sail: in daylight, or at any hour with lights.
    const tides = day.tides.filter(
      (turn) =>
        (ctx.forecast!.lights ||
          (ms(turn.time) >= ms(day.sunrise) && ms(turn.time) <= ms(day.sunset))) &&
        ms(turn.time) >= ms(now),
    );
    info = html`
      ${hoursLine(ctx, day, index)}
      <div class="ci cd-wins">
        ${icon("clock")}${
          best
            ? t("week.day_best", { span: fmt.span(best.start, best.end) })
            : t("week.no_window_short")
        }
      </div>
      <div class="ci">
        ${arrow(summary.direction, 15)}
        <span
          >${compass(t, summary.direction)} ${fmt.range(summary.wind_low, summary.wind_high)}
          ${t("unit.knots_short")}
          <span class="muted"
            >${t("week.gust_short", { gust: fmt.number(summary.gust) })}</span
          ></span
        >
      </div>
      <div class="ci">
        ${icon("waves")}<span
          >${summary.waves ? heightRange(fmt, t, summary.waves[0], summary.waves[1]) : "—"}</span
        >
      </div>
      ${
        summary.water_temperature !== null
          ? html`<div class="ci">
              ${icon("water")}<span
                >${t("week.water", { temperature: temperatureText(fmt, t, summary.water_temperature) })}</span
              >
            </div>`
          : nothing
      }
      ${tides.map(
        (turn) =>
          html`<div class="ci">
            ${icon(turn.high ? "tideUp" : "tideDown")}<span
              >${t(turn.high ? "week.high" : "week.low", { time: fmt.clock(turn.time) })}</span
            >
          </div>`,
      )}
      <div class="sizes" role="list" aria-label=${t("week.sizes_label")}>
        ${SIZES.map((size) => {
          const rating = day.sizes[size]?.best ?? "good";
          const label = `${t(`size_class.${size}`)}: ${t(`level.${rating}`)}`;
          return html`<span
            role="listitem"
            class="sz lvl-${rating} ${size === ctx.boat?.size_class ? "mine" : ""}"
            title=${label}
            aria-label=${label}
            >${t(`size_letter.${size}`)}</span
          >`;
        })}
      </div>
      ${
        day.confidence
          ? html`<div
              class="conf"
              title=${t("week.confidence_title", { spread: fmt.number(day.spread ?? 0, 1) })}
            >
              ${dots(day.confidence)}${t(`confidence.${day.confidence}`)}
            </div>`
          : nothing
      }
    `;
  }
  return html`<div class="cd ${today ? "today" : ""}" style="--col:${index + 2}">
    ${head}
    <div class="cd-scroll" data-shown=${shown} data-open=${open}>
      <div class="cd-hours">
        <div class="cd-track">${track}</div>
        <div class="cd-axis" aria-hidden="true">${ticks}</div>
      </div>
    </div>
    <div class="cd-info">${info}</div>
  </div>`;
}

/**
 * The sailor's hours on a day. Admins and the sailor themselves can change
 * them for that date, and undo a change.
 */
function hoursLine(ctx: Ctx, day: Day, index: number): TemplateResult {
  const { t } = ctx;
  const text = hoursText(ctx, day.date, day.hours, ctx.forecast!.lights);
  const label = day.changed ? t("hours.changed", { hours: text }) : text;
  const cls = `ci hrs ${day.changed ? "changed" : ""}`;
  if (!canSetHours(ctx)) {
    return html`<div class=${cls}>${icon("account")}<span>${label}</span></div>`;
  }
  return html`<div class=${cls}>
    <button
      type="button"
      class="hrs-set"
      aria-label=${t("hours.change_label", { day: dayAndDate(ctx, day), hours: label })}
      @click=${() => ctx.act.openHours(index)}
    >
      ${icon("account")}<span>${label}</span>
    </button>
    ${
      day.changed
        ? html`<button
            type="button"
            class="icon-btn hrs-undo"
            aria-label=${t("hours.undo_label", { day: dayAndDate(ctx, day) })}
            @click=${() => ctx.act.resetHours(index)}
          >
            ${icon("close")}
          </button>`
        : nothing
    }
  </div>`;
}

export function dots(confidence: string): TemplateResult {
  return html`<span class="dots" aria-hidden="true"
    ><i class="on"></i><i class=${confidence !== "low" ? "on" : ""}></i
    ><i class=${confidence === "high" ? "on" : ""}></i
  ></span>`;
}

export function chip(ctx: Ctx, level: Level): TemplateResult {
  return html`<span class="chip lvl-${level}">${ctx.t(`level.${level}`)}</span>`;
}

function hourTip(ctx: Ctx, day: Day, hour: Hour): TemplateResult {
  const { t, fmt } = ctx;
  const why = reasonsText(fmt, t, hour.reasons);
  return html`<b>${t("week.day_time", { day: dayName(ctx, day), time: fmt.clock(hour.time) })}</b>
    <div>${chip(ctx, hour.rating)}${t("tip.score", { score: hour.score ?? "–" })}</div>
    <div>
      ${compass(t, hour.direction)}
      ${t("tip.wind", { wind: fmt.number(hour.wind), gust: fmt.number(hour.gust) })}
      ${hour.wave_height !== null ? ` · ${t("tip.waves", { height: heightText(fmt, t, hour.wave_height) })}` : ""}
    </div>
    ${why ? html`<div class="muted">${why}</div>` : nothing}
    ${
      hour.available
        ? nothing
        : html`<div class="muted">${t("legend.off", { sailor: ctx.sailor?.name ?? "" })}</div>`
    }`;
}

function windowTip(ctx: Ctx, day: Day, window: Window, sail?: PlannedSail): TemplateResult {
  const { t, fmt } = ctx;
  const when = fmt.span(window.start, window.end);
  return html`<b>${t("week.day_time", { day: dayName(ctx, day), time: when })}</b>
    <div>
      ${t("tip.window_score", {
        score: window.score,
        band: t(`band_word.${band(window.score)}`),
      })}
    </div>
    ${
      window.wind_low !== null && window.wind_high !== null
        ? html`<div>
            ${compass(t, window.direction ?? 0)}
            ${t("tip.window_wind", {
              range: fmt.range(window.wind_low, window.wind_high),
              gust: fmt.number(window.gust ?? 0),
            })}
          </div>`
        : nothing
    }
    <div class="muted">
      ${sail ? t("tip.take_out", { status: addText(ctx, sail) }) : t("tip.add")}
    </div>`;
}
