/**
 * The day view: the verdict and advice, a rating for each boat size, wind
 * and tide charts with a readout under the pointer, the hours in a table, and
 * where the numbers come from.
 */
import { html, nothing, svg, type SVGTemplateResult, type TemplateResult } from "lit";

import { isToday, plannedFor, type Ctx } from "./context";
import { band, localHours, localTime } from "./format";
import { arrow, icon, ring, type IconName } from "./glyphs";
import {
  adviceText,
  ageText,
  compass,
  datumText,
  heightText,
  reasonsText,
  savedSourceText,
  sourceText,
} from "./text";
import type { Day, Hour, Level } from "./types";
import { addIcon, addText, chip, hoursOf, isPast, SIZES, smoothPath, warningSource } from "./week";
import { windColor } from "./wind-field";

const ADVICE_ICONS: Record<string, IconName> = {
  alert: "alert",
  beach: "beach",
  current: "current",
  flag: "flag",
  rain: "rain",
  sail: "sail",
  sunset: "sunset",
  tide: "tideUp",
  water: "water",
  waves: "waves",
  windy: "windy",
};

function windCell(knots: number): string {
  const [r, g, b] = windColor(knots);
  const light = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
  return `background:rgb(${r},${g},${b});color:${light > 0.5 ? "#0e171d" : "#ffffff"}`;
}

const LEVEL_INDEX: Record<Level, number> = {
  good: 0,
  caution: 1,
  not_recommended: 2,
  dangerous: 3,
};

/**
 * The AI summary, with AI on: the summary written for the day, or a button
 * to ask for one. The ratings above always come from SailCast's own rules.
 */
function aiSummary(ctx: Ctx, day: Day, index: number): TemplateResult | typeof nothing {
  const { t, fmt } = ctx;
  if (!ctx.config.ai || day.over) return nothing;
  const summary = day.ai;
  if (summary?.current) {
    return html`<div class="ai">
      <div class="ai-head">
        ${icon("ai")}<b>${t("ai.title")}</b>
        <span class="small">${t("ai.written", { time: fmt.clock(summary.made) })}</span>
      </div>
      <p class="ai-text">${summary.text}</p>
      <p class="small">${t("ai.note")}</p>
    </div>`;
  }
  const busy = ctx.aiBusy === day.date;
  const failed = ctx.aiError?.date === day.date ? ctx.aiError.text : undefined;
  return html`<div class="ai ai-ask">
    ${summary ? html`<p class="small">${t("ai.changed")}</p>` : nothing}
    ${failed ? html`<p class="small ai-failed" role="alert">${failed}</p>` : nothing}
    <button
      type="button"
      class="btn btn-tonal"
      ?disabled=${busy}
      aria-busy=${busy ? "true" : "false"}
      @click=${() => ctx.act.summarize(index)}
    >
      ${icon("ai")}${busy ? t("ai.writing") : summary ? t("ai.again") : t("ai.button")}
    </button>
  </div>`;
}

export function dayView(ctx: Ctx, width: number): TemplateResult {
  const { t, fmt } = ctx;
  const forecast = ctx.forecast;
  if (!forecast) return html``;
  const index = Math.min(ctx.day, forecast.days.length - 1);
  const day = forecast.days[index];
  const strip = html`<div class="dstrip" role="group" aria-label=${t("day.strip_label")}>
    ${forecast.days.map(
      (item, number) =>
        html`<button
          type="button"
          class="ds ${item.score === null ? "" : `s-${band(item.score)}`}"
          aria-pressed=${number === index ? "true" : "false"}
          aria-label=${`${isToday(ctx, item) ? t("week.today") : fmt.weekday(item.date, "long")}, ${fmt.shortDate(item.date)}${item.score === null ? "" : `, ${t("week.score_label", { score: item.score })}`}`}
          @click=${() => ctx.act.openDay(number)}
        >
          <span class="ds-wd"
            >${isToday(ctx, item) ? t("week.today_short") : fmt.weekday(item.date)}</span
          >
          <span class="ds-d">${fmt.dayOfMonth(item.date)}</span>
          <span class="ds-sc"><i></i><span>${item.score ?? "–"}</span></span>
        </button>`,
    )}
  </div>`;
  if (!day.summary) {
    return html`${strip}
      <div class="card">${t("day.over")}</div>`;
  }
  const best = day.best !== null ? day.windows[day.best] : undefined;
  const mine = ctx.boat ? day.sizes[ctx.boat.size_class] : undefined;
  const hours = hoursOf(ctx, day);
  return html`
    ${strip}
    <div class="dayview">
      <section class="card">
        <div class="verdict">
          ${ring(day.score, day.score === null ? undefined : t("week.score_label", { score: day.score }))}
          <div>
            <span class="eyebrow">${fmt.longDate(day.date)} · ${ctx.spot?.name}</span>
            <h2 class="v-title">
              ${
                best
                  ? t("day.best", { span: fmt.span(best.start, best.end) })
                  : day.available
                    ? t("day.no_window")
                    : t("day.not_sailing", { sailor: ctx.sailor?.name ?? "" })
              }
            </h2>
            <p class="v-sub">
              ${t("day.who", { sailor: ctx.sailor?.name ?? "", boat: ctx.boat?.name ?? "" })}
              ${mine ? chip(ctx, mine.best) : nothing}
              ${
                day.confidence
                  ? html`<span
                      >${t("day.confidence", {
                        confidence: t(`confidence_word.${day.confidence}`),
                        spread: fmt.number(day.spread ?? 0, 1),
                      })}</span
                    >`
                  : nothing
              }
            </p>
          </div>
        </div>
        ${
          day.windows.length
            ? html`<div class="v-wins">
                ${day.windows.map((window, number) => {
                  const sail = plannedFor(ctx, window);
                  return html`<button
                    type="button"
                    class="win-btn ${sail ? "added" : ""}"
                    @click=${() => ctx.act.openWindow(index, number)}
                  >
                    ${icon(addIcon(sail))}<b>${fmt.span(window.start, window.end)}</b>
                    <span>${window.score} · ${t(`band_word.${band(window.score)}`)}</span>
                    <span class="act">${addText(ctx, sail)}</span>
                  </button>`;
                })}
              </div>`
            : nothing
        }
        <ul class="advice">
          ${day.advice.map(
            (advice) =>
              html`<li class=${advice.hot ? "hot" : ""}>
                ${
                  advice.icon === "wind"
                    ? arrow(day.summary?.direction ?? 0, 18)
                    : icon(ADVICE_ICONS[advice.icon] ?? "info")
                }
                <span>${adviceText(fmt, t, advice)}</span>
              </li>`,
          )}
        </ul>
        ${aiSummary(ctx, day, index)}
      </section>
      <section class="card">
        <div class="card-head">
          <h2>${t("day.sizes")}</h2>
          <span class="small"
            >${t("day.sizes_sub", {
              sailor: ctx.sailor?.name ?? "",
              skill: t(`skill_word.${ctx.sailor?.skill ?? "beginner"}`),
            })}</span
          >
        </div>
        <div class="sizes-list">${SIZES.map((size) => sizeRow(ctx, day, size))}</div>
      </section>
    </div>
    ${windChart(ctx, day, hours, width)} ${tideChart(ctx, day, hours, width)}
    <section class="card">
      <div class="card-head">
        <h2>${t("day.hours")}</h2>
        <span class="small">${t("day.hours_sub")}</span>
      </div>
      <div class="tbl-wrap">
        ${hourTable(
          ctx,
          hours.filter((hour) => hour.daylight),
        )}
      </div>
    </section>
    ${sourcesCard(ctx)}
  `;
}

function sizeRow(ctx: Ctx, day: Day, size: (typeof SIZES)[number]): TemplateResult {
  const { t, fmt } = ctx;
  const rating = day.sizes[size];
  if (!rating) return html``;
  const why = reasonsText(fmt, t, rating.reasons);
  let text: string;
  if (rating.best === rating.worst) {
    text =
      LEVEL_INDEX[rating.worst] > 0
        ? t("day.size_all_day", { rating: t(`level.${rating.worst}`), why })
        : t("day.size_within");
  } else {
    text = t("day.size_changes", {
      best: t(`level.${rating.best}`),
      worst: t(`level_word.${rating.worst}`),
      time: fmt.clock(rating.worst_at),
      why,
    });
  }
  const mine = size === ctx.boat?.size_class;
  return html`<div class="size">
    <span class="nm"
      >${t(`size_class.${size}`)}${mine ? html`<span class="tag">${t("day.your_boat")}</span>` : nothing}</span
    >
    ${chip(ctx, rating.best)}
    <span class="why">${text}</span>
  </div>`;
}

interface Frame {
  width: number;
  height: number;
  left: number;
  right: number;
  top: number;
  bottom: number;
}

/** X for a local hour of the day, 0 to 23. */
function xScale(frame: Frame): (hour: number) => number {
  return (hour) => frame.left + (hour / 23) * (frame.width - frame.left - frame.right);
}

/** Night before sunrise and after sunset, the past hatched, and the hours along the bottom. */
function background(ctx: Ctx, day: Day, frame: Frame, id: string): SVGTemplateResult {
  const { fmt } = ctx;
  const x = xScale(frame);
  const zone = fmt.zone;
  const sunrise = localHours(day.sunrise, zone);
  const sunset = localHours(day.sunset, zone);
  const top = frame.top;
  const height = frame.height - frame.top - frame.bottom;
  const now = localHours(ctx.forecast!.now, zone);
  const labels = [];
  for (let hour = 0; hour <= 21; hour += 3) {
    labels.push(
      svg`<text class="ax" x=${x(hour)} y=${frame.height - 6} text-anchor="middle">${fmt.hourOf(day.date, hour)}</text>`,
    );
  }
  return svg`
    <defs><pattern id="hatch-${id}" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
      <line x1="0" y1="0" x2="0" y2="6" stroke="var(--sc-h-hatch)" stroke-width="3"></line></pattern></defs>
    <rect x=${x(0)} y=${top} width=${Math.max(0, x(sunrise) - x(0))} height=${height} fill="var(--sc-h-night)" opacity=".75"></rect>
    <rect x=${x(sunset)} y=${top} width=${Math.max(0, x(23) - x(sunset))} height=${height} fill="var(--sc-h-night)" opacity=".75"></rect>
    ${
      isToday(ctx, day)
        ? svg`<rect x=${x(0)} y=${top} width=${Math.max(0, x(now) - x(0))} height=${height} fill="url(#hatch-${id})"></rect>
          <line x1=${x(now)} x2=${x(now)} y1=${top - 4} y2=${frame.height - frame.bottom} stroke="var(--sc-now)" stroke-width="2"></line>`
        : svg``
    }
    ${labels}`;
}

/** Follow the pointer with a line and a readout of that hour. */
function crosshair(
  ctx: Ctx,
  frame: Frame,
  hours: Hour[],
  readout: (hour: Hour) => TemplateResult,
): (event: PointerEvent) => void {
  const zone = ctx.fmt.zone;
  return (event) => {
    const chart = event.currentTarget as SVGSVGElement;
    const box = chart.getBoundingClientRect();
    const position = ((event.clientX - box.left) / box.width) * frame.width;
    const span = frame.width - frame.left - frame.right;
    const target = Math.min(23, Math.max(0, Math.round(((position - frame.left) / span) * 23)));
    const hour = hours.find((item) => localTime(item.time, zone).hour === target);
    const line = chart.querySelector(".xh");
    if (!hour || !line) return;
    const x = frame.left + (target / 23) * span;
    line.setAttribute("x1", String(x));
    line.setAttribute("x2", String(x));
    line.setAttribute("opacity", "1");
    ctx.act.showTipAt(
      box.left + (x / frame.width) * box.width,
      box.top + (frame.top / frame.width) * box.width,
      readout(hour),
    );
  };
}

function hideCrosshair(ctx: Ctx): (event: PointerEvent) => void {
  return (event) => {
    (event.currentTarget as SVGSVGElement).querySelector(".xh")?.setAttribute("opacity", "0");
    ctx.act.hideTip();
  };
}

function windChart(ctx: Ctx, day: Day, hours: Hour[], width: number): TemplateResult {
  const { t, fmt } = ctx;
  if (!hours.length) return html``;
  const frame: Frame = {
    width: Math.max(320, width),
    height: 240,
    left: 30,
    right: 12,
    top: 34,
    bottom: 26,
  };
  const x = xScale(frame);
  const zone = fmt.zone;
  const at = (hour: Hour): number => localTime(hour.time, zone).hour;
  const models = (hour: Hour): number[] =>
    hour.models.filter((value): value is number => value !== null);
  const peak = Math.max(...hours.map((hour) => Math.max(hour.gust, ...models(hour))));
  const top = Math.max(15, Math.ceil((peak + 2) / 5) * 5);
  const y = (value: number): number =>
    frame.top + (1 - value / top) * (frame.height - frame.top - frame.bottom);
  const best = day.best !== null ? day.windows[day.best] : undefined;
  const grid = [];
  for (let value = 0; value <= top; value += 5) {
    grid.push(svg`<line x1=${frame.left} x2=${frame.width - frame.right} y1=${y(value)} y2=${y(value)} stroke="var(--sc-line2)"></line>
      <text class="ax" x=${frame.left - 6} y=${y(value) + 4} text-anchor="end">${value}</text>`);
  }
  const upper = hours.map((hour) => [x(at(hour)), y(Math.max(...models(hour), hour.wind))]);
  const lower = hours
    .map((hour) => [x(at(hour)), y(Math.min(...models(hour), hour.wind))])
    .reverse();
  const spread = `M${[...upper, ...lower].map((point) => `${point[0].toFixed(1)},${point[1].toFixed(1)}`).join("L")}Z`;
  const wind = smoothPath(hours.map((hour) => [x(at(hour)), y(hour.wind)]));
  const first = x(at(hours[0]));
  const last = x(at(hours[hours.length - 1]));
  const arrows = hours
    .filter((hour) => at(hour) % 2 === 0)
    .map(
      (hour) =>
        svg`<g transform="translate(${x(at(hour)).toFixed(1)},${frame.top - 8}) rotate(${(hour.direction + 180) % 360})"><path d="M0,-6 L-4,2 L-1.3,2 L-1.3,6 L1.3,6 L1.3,2 L4,2 Z" fill="var(--sc-fg2)"></path></g>`,
    );
  const window = best
    ? svg`<rect x=${x(localHours(best.start, zone))} y=${frame.top} width=${Math.max(0, x(localHours(best.end, zone)) - x(localHours(best.start, zone)))} height=${frame.height - frame.top - frame.bottom} fill="var(--sc-window)"></rect>
      <text class="ax-strong" x=${x(localHours(best.start, zone))} y=${frame.top - 20} dx="2">${t("day.best", { span: fmt.span(best.start, best.end) })}</text>`
    : svg``;
  const readout = (hour: Hour): TemplateResult => {
    const values = models(hour);
    return html`<b>${fmt.clock(hour.time)}</b>
      <div>
        ${compass(t, hour.direction)}
        ${t("tip.wind", { wind: fmt.number(hour.wind), gust: fmt.number(hour.gust) })}
      </div>
      ${
        values.length
          ? html`<div class="muted">
              ${t("day.models", { range: fmt.range(Math.min(...values), Math.max(...values)) })}
            </div>`
          : nothing
      }
      ${
        hour.daylight
          ? html`<div>
              ${chip(ctx, hour.rating)}${t("tip.score", { score: hour.score ?? "–" })}
            </div>`
          : html`<div class="muted">${t("legend.dark")}</div>`
      }`;
  };
  return html`<section class="card">
    <div class="card-head">
      <h2>${t("day.wind")}</h2>
      <div class="key">
        <span><i style="background:var(--sc-chart-wind)"></i>${t("day.key_wind")}</span>
        <span><i style="background:var(--sc-chart-gust)"></i>${t("day.key_gusts")}</span>
        <span
          ><i style="background:var(--sc-chart-spread);height:9px"></i>${t("day.key_spread")}</span
        >
        <span><i style="background:var(--sc-window);height:9px"></i>${t("day.key_window")}</span>
      </div>
    </div>
    <div class="chart">
      <svg
        viewBox="0 0 ${frame.width} ${frame.height}"
        width=${frame.width}
        height=${frame.height}
        role="img"
        aria-label=${t("day.wind_label")}
        @pointermove=${crosshair(ctx, frame, hours, readout)}
        @pointerleave=${hideCrosshair(ctx)}
      >
        ${background(ctx, day, frame, "w")} ${window} ${grid}
        ${svg`<path d=${spread} fill="var(--sc-chart-spread)"></path>
          <path d="${wind}L${last.toFixed(1)},${y(0).toFixed(1)}L${first.toFixed(1)},${y(0).toFixed(1)}Z" fill="var(--sc-chart-fill)"></path>
          <path d=${smoothPath(hours.map((hour) => [x(at(hour)), y(hour.gust)]))} fill="none" stroke="var(--sc-chart-gust)" stroke-width="1.5"></path>
          <path d=${wind} fill="none" stroke="var(--sc-chart-wind)" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"></path>
          ${arrows}
          <text class="ax" x=${frame.left} y=${frame.top - 22} dx="-28">${t("unit.knots_short")}</text>
          <line class="xh" y1=${frame.top} y2=${frame.height - frame.bottom} opacity="0"></line>`}
      </svg>
    </div>
  </section>`;
}

function tideChart(ctx: Ctx, day: Day, hours: Hour[], width: number): TemplateResult {
  const { t, fmt } = ctx;
  const forecast = ctx.forecast!;
  const tides = hours.filter((hour) => hour.tide_height !== null);
  const currents = hours.filter((hour) => hour.current !== null);
  if (!tides.length && !currents.length) return html``;
  const currentHeight = currents.length ? 70 : 0;
  const frame: Frame = {
    width: Math.max(320, width),
    height: 200 + currentHeight,
    left: 30,
    right: 12,
    top: 22,
    bottom: 26 + currentHeight,
  };
  const x = xScale(frame);
  const zone = fmt.zone;
  const at = (iso: string): number => localHours(iso, zone);
  const week = forecast.hours
    .map((hour) => hour.tide_height)
    .filter((value): value is number => value !== null)
    .map((value) => fmt.height(value));
  const low = Math.floor(Math.min(...week, 0)) - 1;
  const high = Math.ceil(Math.max(...week, 1)) + 1;
  const y = (value: number): number =>
    frame.top + (1 - (value - low) / (high - low)) * (frame.height - frame.top - frame.bottom);
  const turns = day.tides.filter((turn) => at(turn.time) > 0 && at(turn.time) < 23);
  const points = [
    ...tides.map((hour) => [at(hour.time), fmt.height(hour.tide_height!)] as [number, number]),
    ...turns.map((turn) => [at(turn.time), fmt.height(turn.height)] as [number, number]),
  ].sort((a, b) => a[0] - b[0]);
  const grid = [];
  const step = high - low > 8 ? 2 : 1;
  for (let value = Math.ceil(low / step) * step; value <= high; value += step) {
    grid.push(svg`<line x1=${frame.left} x2=${frame.width - frame.right} y1=${y(value)} y2=${y(value)} stroke="var(--sc-line2)"></line>
      <text class="ax" x=${frame.left - 6} y=${y(value) + 4} text-anchor="end">${value}</text>`);
  }
  const line = points
    .map(([hour, value]) => `${x(hour).toFixed(1)},${y(value).toFixed(1)}`)
    .join("L");
  const curve = points.length
    ? svg`<path d="M${x(points[0][0]).toFixed(1)},${y(low).toFixed(1)}L${line}L${x(points[points.length - 1][0]).toFixed(1)},${y(low).toFixed(1)}Z" fill="var(--sc-tide-fill)"></path>
      <path d="M${line}" fill="none" stroke="var(--sc-tide)" stroke-width="2.4"></path>`
    : svg``;
  const markers = turns.map((turn) => {
    const cx = x(at(turn.time));
    const cy = y(fmt.height(turn.height));
    // Labels near either end line up with the edge rather than spill past it.
    const anchor =
      cx > frame.width - frame.right - 70 ? "end" : cx < frame.left + 70 ? "start" : "middle";
    return svg`<circle cx=${cx.toFixed(1)} cy=${cy.toFixed(1)} r="4" fill="var(--sc-tide)" stroke="var(--sc-card)" stroke-width="2"></circle>
      <text class="ax-strong" x=${cx.toFixed(1)} y=${(turn.high ? cy - 10 : cy + 18).toFixed(1)} text-anchor=${anchor}>${t(
        turn.high ? "day.tide_high" : "day.tide_low",
        { height: heightText(fmt, t, turn.height), time: fmt.clock(turn.time) },
      )}</text>`;
  });
  let current = svg``;
  if (currents.length) {
    const base = frame.height - 22 - currentHeight / 2;
    const scale = (currentHeight / 2 - 6) / 1.5;
    const barWidth = Math.max(3, (x(1) - x(0)) * 0.6);
    const peaks = forecast.current_events.filter(
      (event) =>
        localTime(event.time, zone).date === day.date &&
        Math.abs(event.speed) >= 0.2 &&
        at(event.time) > 0 &&
        at(event.time) < 23,
    );
    current = svg`<line x1=${frame.left} x2=${frame.width - frame.right} y1=${base} y2=${base} stroke="var(--sc-line)"></line>
      <text class="ax" x=${frame.left - 6} y=${base + 4} text-anchor="end">0</text>
      ${currents.map((hour) => {
        const speed = hour.current!;
        return svg`<rect x=${(x(at(hour.time)) - barWidth / 2).toFixed(1)} y=${(speed >= 0 ? base - speed * scale : base).toFixed(1)} width=${barWidth.toFixed(1)} height=${Math.max(0.5, Math.abs(speed) * scale).toFixed(1)} rx="1.5" fill=${speed >= 0 ? "var(--sc-flood)" : "var(--sc-ebb)"}></rect>`;
      })}
      ${peaks.map(
        (event) =>
          svg`<text class="ax" x=${x(at(event.time)).toFixed(1)} y=${(event.speed >= 0 ? base - event.speed * scale - 5 : base - event.speed * scale + 13).toFixed(1)} text-anchor="middle">${t("day.current_peak", { speed: fmt.number(Math.abs(event.speed), 1) })}</text>`,
      )}
      <text class="ax" x=${frame.width - frame.right} y=${frame.height - 4} text-anchor="end">${t("day.current_axis", { station: forecast.sources.current_station?.name ?? forecast.sources.current_station?.id ?? "" })}</text>`;
  }
  const readout = (hour: Hour): TemplateResult =>
    html`<b>${fmt.clock(hour.time)}</b> ${
        hour.tide_height !== null
          ? html`<div>
              ${t(hour.tide_rising ? "day.tide_rising" : "day.tide_falling", {
                height: heightText(fmt, t, hour.tide_height),
              })}
            </div>`
          : nothing
      }
      ${
        hour.current !== null
          ? html`<div>
              ${t(
                Math.abs(hour.current) < 0.2
                  ? "day.current_slack"
                  : hour.current > 0
                    ? "day.current_flood"
                    : "day.current_ebb",
                { speed: fmt.number(Math.abs(hour.current), 1) },
              )}
            </div>`
          : nothing
      }`;
  return html`<section class="card">
    <div class="card-head">
      <h2>${t(currents.length ? "day.tide_and_current" : "day.tide")}</h2>
      <div class="key">
        <span
          >${t(fmt.feet ? "day.tide_datum_feet" : "day.tide_datum_meters", {
            datum: datumText(t, forecast.tide?.datum),
          })}</span
        >
        ${
          currents.length
            ? html`<span><i style="background:var(--sc-flood)"></i>${t("day.key_flood")}</span>
                <span><i style="background:var(--sc-ebb)"></i>${t("day.key_ebb")}</span>`
            : nothing
        }
      </div>
    </div>
    <div class="chart">
      <svg
        viewBox="0 0 ${frame.width} ${frame.height}"
        width=${frame.width}
        height=${frame.height}
        role="img"
        aria-label=${t(currents.length ? "day.tide_current_label" : "day.tide_label")}
        @pointermove=${crosshair(ctx, frame, hours, readout)}
        @pointerleave=${hideCrosshair(ctx)}
      >
        ${background(ctx, day, { ...frame, bottom: 26, height: frame.height - currentHeight }, "t")}
        ${grid} ${curve} ${markers} ${current}
        ${svg`<line class="xh" y1=${frame.top} y2=${frame.height - 26} opacity="0"></line>`}
      </svg>
    </div>
  </section>`;
}

function hourTable(ctx: Ctx, hours: Hour[]): TemplateResult {
  const { t, fmt } = ctx;
  const cell = (hour: Hour, content: unknown, style = ""): TemplateResult =>
    html`<td class=${isPast(ctx, hour) ? "is-past" : ""} style=${style}>${content}</td>`;
  const row = (label: string, render: (hour: Hour) => TemplateResult): TemplateResult =>
    html`<tr>
      <th scope="row">${label}</th>
      ${hours.map(render)}
    </tr>`;
  const waves = hours.some((hour) => hour.wave_height !== null);
  const periods = hours.some((hour) => hour.wave_period !== null);
  const tides = hours.some((hour) => hour.tide_height !== null);
  const currents = hours.some((hour) => hour.current !== null);
  const height = fmt.feet ? t("unit.feet_short") : t("unit.meters_short");
  const degrees = fmt.fahrenheit ? "°F" : "°C";
  return html`<table class="hours">
    <thead>
      <tr>
        <th></th>
        ${hours.map((hour) => html`<th scope="col">${fmt.clock(hour.time)}</th>`)}
      </tr>
    </thead>
    <tbody>
      ${row(t("table.direction"), (hour) =>
        cell(hour, html`${arrow(hour.direction)} ${compass(t, hour.direction)}`),
      )}
      ${row(t("table.wind"), (hour) => cell(hour, fmt.number(hour.wind), windCell(hour.wind)))}
      ${row(t("table.gusts"), (hour) => cell(hour, fmt.number(hour.gust), windCell(hour.gust)))}
      ${
        waves
          ? row(t("table.waves", { unit: height }), (hour) =>
              cell(
                hour,
                hour.wave_height === null ? "—" : fmt.number(fmt.height(hour.wave_height), 1),
              ),
            )
          : nothing
      }
      ${
        periods
          ? row(t("table.period"), (hour) =>
              cell(
                hour,
                hour.wave_period === null
                  ? "—"
                  : // Short chop on sheltered water needs a decimal.
                    fmt.number(hour.wave_period, hour.wave_period < 5 ? 1 : 0),
              ),
            )
          : nothing
      }
      ${
        tides
          ? row(t("table.tide", { unit: height }), (hour) =>
              cell(
                hour,
                hour.tide_height === null
                  ? "—"
                  : `${fmt.number(fmt.height(hour.tide_height), 1)} ${hour.tide_rising ? "↑" : "↓"}`,
              ),
            )
          : nothing
      }
      ${
        currents
          ? row(t("table.current"), (hour) =>
              cell(
                hour,
                hour.current === null
                  ? "—"
                  : `${fmt.number(Math.abs(hour.current), 1)} ${t(
                      Math.abs(hour.current) < 0.2
                        ? "table.slack"
                        : hour.current > 0
                          ? "table.flood"
                          : "table.ebb",
                    )}`,
              ),
            )
          : nothing
      }
      ${row(t("table.air", { unit: degrees }), (hour) =>
        cell(hour, hour.temperature === null ? "—" : fmt.number(fmt.temperature(hour.temperature))),
      )}
      ${row(t("table.rain"), (hour) =>
        cell(hour, hour.rain_chance === null ? "—" : fmt.number(hour.rain_chance)),
      )}
      ${row(t("table.rating"), (hour) =>
        cell(
          hour,
          html`<span
            class="rate lvl-${hour.rating}"
            title=${`${t(`level.${hour.rating}`)}: ${reasonsText(fmt, t, hour.reasons) || t("table.within")}`}
            >${t(`level_short.${hour.rating}`)}</span
          >`,
        ),
      )}
      ${row(t("table.score"), (hour) =>
        cell(
          hour,
          hour.score === null
            ? "–"
            : html`<span class="score-pill s-${band(hour.score)}">${hour.score}</span>`,
        ),
      )}
    </tbody>
  </table>`;
}

/** Where the tides come from, what they're measured from, and the provider's notice. */
function tideSource(ctx: Ctx): TemplateResult | string {
  const { t } = ctx;
  const forecast = ctx.forecast!;
  const saved = forecast.sources.tide_station;
  const tide = forecast.tide;
  if (!saved || !tide) return t("sources.none");
  return html`${t(`sources.tide_by.${tide.provider}`, {
    station: savedSourceText(saved.id, saved.name),
    gauge: tide.station ?? "",
    datum: datumText(t, tide.datum),
  })}
  ${tide.provider === "worldtides" && tide.station ? t("sources.tide_gauge", { gauge: tide.station }) : nothing}
  ${tide.notice ? html`<small class="notice">${tide.notice}</small>` : nothing}
  ${
    tide.provider === "worldtides"
      ? html`<a href="https://www.worldtides.info/copyright" target="_blank" rel="noreferrer"
          >${t("sources.worldtides_credit")}</a
        >`
      : nothing
  }`;
}

function sourcesCard(ctx: Ctx): TemplateResult {
  const { t, fmt } = ctx;
  const forecast = ctx.forecast!;
  const sources = forecast.sources;
  const spot = ctx.spot;
  const name = (source: { id: string; name: string | null } | null): string =>
    source ? (source.name ? `${source.id} · ${source.name}` : source.id) : "";
  const nudge = forecast.adjustments.find((item) => item.field === "wind");
  const waveNudge = forecast.adjustments.find((item) => item.field === "wave_height");
  const waveSources = new Set(forecast.hours.map((hour) => hour.wave_source));
  const shoreline = forecast.shoreline;
  const readings: TemplateResult[] = [];
  for (const source of forecast.readings.sources) {
    const label =
      source.kind === "sensors"
        ? t("reading_source.sensors")
        : t(`sources.${source.kind}_text`, { station: name(sources[source.kind]) });
    readings.push(
      html`<div>
        ${label}${source.newest ? html` · ${t("sources.newest", { age: ageText(t, forecast.now, source.newest) })}` : nothing}
      </div>`,
    );
  }
  return html`<section class="card sources">
    <div class="card-head"><h2>${t("sources.title")}</h2></div>
    <dl>
      <dt>${t("sources.wind")}</dt>
      <dd>
        ${t("sources.wind_text")}
        ${
          nudge
            ? t("sources.nudged", {
                difference: t("unit.knots", { value: fmt.number(Math.abs(nudge.difference), 1) }),
                direction: t(nudge.difference > 0 ? "sources.up" : "sources.down"),
                source: sourceText(t, nudge.kind, nudge.station),
                time: fmt.clock(nudge.time),
              })
            : nothing
        }
      </dd>
      <dt>${t("sources.waves")}</dt>
      <dd>
        ${
          shoreline && !shoreline.on_water
            ? t("sources.on_land")
            : waveSources.has("estimate")
              ? t(spot?.fetch ? "sources.waves_estimate_set" : "sources.waves_estimate", {
                  distance: spot?.fetch
                    ? t(fmt.miles ? "unit.miles" : "unit.km", {
                        value: fmt.number(fmt.distance(spot.fetch), 1),
                      })
                    : "",
                })
              : waveSources.has("model") || waveSources.has("sheltered")
                ? t("sources.waves_open")
                : t("sources.waves_none")
        }
        ${waveSources.has("sheltered") ? t("sources.waves_sheltered") : nothing}
        ${
          waveNudge
            ? t("sources.waves_nudged", {
                difference: heightText(fmt, t, Math.abs(waveNudge.difference)),
                direction: t(waveNudge.difference > 0 ? "sources.up" : "sources.down"),
                source: sourceText(t, waveNudge.kind, waveNudge.station),
                time: fmt.clock(waveNudge.time),
              })
            : nothing
        }
      </dd>
      <dt>${t("sources.readings")}</dt>
      <dd>${readings.length ? readings : t("sources.no_readings")}</dd>
      <dt>${t("sources.tide")}</dt>
      <dd>${tideSource(ctx)}</dd>
      ${
        sources.current_station
          ? html`<dt>${t("sources.current")}</dt>
              <dd>${t("sources.current_text", { station: name(sources.current_station) })}</dd>`
          : nothing
      }
      <dt>${t("sources.warnings")}</dt>
      <dd>${warningSource(ctx) ?? t("sources.none")}</dd>
      ${
        ctx.forecast!.fetched
          ? html`<dt>${t("sources.updated")}</dt>
              <dd>
                ${`${ctx.fmt.weekday(localTime(ctx.forecast!.fetched, ctx.fmt.zone).date, "long")} ${ctx.fmt.clock(ctx.forecast!.fetched)}`}
              </dd>`
          : nothing
      }
    </dl>
  </section>`;
}
