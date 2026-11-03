/**
 * Dialogs for sailing windows in your own calendars: adding one, looking at
 * one that's in a calendar already, and automatic adding.
 */
import { html, nothing, type TemplateResult } from "lit";

import { checked, define, ScDialog, value } from "./dialog";
import { band, localTime, ms, WEEKDAYS } from "./format";
import { icon, ring } from "./glyphs";
import { compass, heightRange } from "./text";
import type { AutoCalendar, CalendarInfo, PlannedSail } from "./types";
import { addIcon, addText, plannedStatus } from "./week";

const AHEAD = [1, 2, 4, 6];
const HALF_HOUR = 1_800_000;
const HOUR = 3_600_000;

function calendarLabel(calendar: CalendarInfo | undefined, fallback: string): string {
  return calendar ? `${calendar.name} (${calendar.via})` : fallback;
}

/** Add a sailing window to one of your calendars. */
export class ScWindowDialog extends ScDialog {
  static override properties = {
    ...ScDialog.properties,
    dayIndex: { type: Number },
    windowIndex: { type: Number },
    start: { state: true },
    end: { state: true },
  };

  declare dayIndex: number;
  declare windowIndex: number;
  declare start?: string;
  declare end?: string;

  private get window() {
    return this.ctx.forecast?.days[this.dayIndex]?.windows[this.windowIndex];
  }

  /** The times a sail can start: the window's start, then each half hour. */
  private starts(): string[] {
    const window = this.window!;
    const first = Date.parse(window.start);
    const last = Date.parse(window.end) - HOUR;
    const times = [window.start];
    for (
      let time = Math.ceil((first + 1) / HALF_HOUR) * HALF_HOUR;
      time <= last;
      time += HALF_HOUR
    ) {
      times.push(new Date(time).toISOString());
    }
    return times;
  }

  /** The times a sail can end, at least an hour after it starts. */
  private ends(start: string): string[] {
    const window = this.window!;
    const end = Date.parse(window.end);
    const times = [];
    for (
      let time = Math.ceil((Date.parse(start) + HOUR) / HALF_HOUR) * HALF_HOUR;
      time < end;
      time += HALF_HOUR
    ) {
      times.push(new Date(time).toISOString());
    }
    times.push(window.end);
    return times;
  }

  protected heading(): string {
    return this.t("add.title");
  }

  protected body(): TemplateResult {
    const { ctx } = this;
    const { fmt, t } = ctx;
    const day = ctx.forecast!.days[this.dayIndex];
    const window = this.window!;
    const start = this.start ?? window.start;
    const ends = this.ends(start);
    const end = this.end && ends.includes(this.end) ? this.end : ends[ends.length - 1];
    const calendars = ctx.config.calendars;
    const chosen = calendars.find((item) => item.entity_id === ctx.calendar) ?? calendars[0];
    const hours = ctx.forecast!.hours.filter(
      (hour) => ms(hour.time) < ms(end) && ms(hour.time) + HOUR > ms(start) && hour.score !== null,
    );
    const score = hours.length
      ? Math.round(hours.reduce((sum, hour) => sum + (hour.score ?? 0), 0) / hours.length)
      : window.score;
    const winds = hours.map((hour) => hour.wind);
    const waves = hours
      .map((hour) => hour.wave_height)
      .filter((height): height is number => height !== null);
    const tides = day.tides.filter(
      (turn) => ms(turn.time) >= ms(start) && ms(turn.time) <= ms(end),
    );
    const direction = hours.length ? hours[Math.floor(hours.length / 2)].direction : 0;
    return html`
      <div class="evt">
        ${ring(score)}
        <b>${fmt.longDate(day.date)} · ${fmt.span(start, end)}</b>
        <span>${ctx.spot?.name} · ${ctx.sailor?.name} · ${ctx.boat?.name}</span>
      </div>
      ${
        calendars.length
          ? html`<label class="fld">
              <span class="lbl">${t("add.calendar")}</span>
              <select name="calendar">
                ${calendars.map(
                  (item) =>
                    html`<option value=${item.entity_id} ?selected=${item === chosen}>
                      ${calendarLabel(item, item.entity_id)}
                    </option>`,
                )}
              </select>
            </label>`
          : html`<p class="form-err">${t("add.no_calendars")}</p>`
      }
      <label class="fld">
        <span class="lbl">${t("add.event_title")}</span>
        <input
          type="text"
          name="title"
          maxlength="80"
          .value=${t("add.default_title", { spot: ctx.spot?.name ?? "" })}
        />
      </label>
      <div class="two">
        <label class="fld">
          <span class="lbl">${t("add.start")}</span>
          <select
            name="start"
            @change=${(event: Event) => (this.start = (event.target as HTMLSelectElement).value)}
          >
            ${this.starts().map(
              (time) =>
                html`<option value=${time} ?selected=${time === start}>${fmt.clock(time)}</option>`,
            )}
          </select>
        </label>
        <label class="fld">
          <span class="lbl">${t("add.end")}</span>
          <select
            name="end"
            @change=${(event: Event) => (this.end = (event.target as HTMLSelectElement).value)}
          >
            ${ends.map(
              (time) =>
                html`<option value=${time} ?selected=${time === end}>
                  ${fmt.clock(time)}${ms(time) === ms(day.sunset) ? ` (${t("add.sunset")})` : ""}
                </option>`,
            )}
          </select>
        </label>
      </div>
      <div class="fld">
        <span class="lbl">${t("add.description")}</span>
        <div class="desc">
          ${t("add.preview", {
            sailor: ctx.sailor?.name ?? "",
            boat: ctx.boat?.name ?? "",
            score,
            band: t(`band.${band(score)}`).toLowerCase(),
          })}
          ${
            winds.length
              ? t("add.preview_wind", {
                  direction: compass(t, direction),
                  range: fmt.range(Math.min(...winds), Math.max(...winds)),
                  gust: fmt.number(Math.max(...hours.map((hour) => hour.gust))),
                })
              : ""
          }
          ${
            waves.length
              ? t("add.preview_waves", {
                  range: heightRange(fmt, t, Math.min(...waves), Math.max(...waves)),
                })
              : ""
          }
          ${tides
            .map((turn) =>
              t(turn.high ? "add.preview_high" : "add.preview_low", { time: fmt.clock(turn.time) }),
            )
            .join(" ")}
          ${t("add.preview_sunset", { time: fmt.clock(day.sunset) })} ${t("add.preview_check")}
        </div>
      </div>
      <label class="check">
        <input type="checkbox" name="watch" checked />
        <span>${t("add.watch")}</span>
      </label>
      <p class="hint">${t("add.hint")}</p>
    `;
  }

  protected footer(): TemplateResult {
    return this.actions(this.t("add.submit"), !this.ctx.config.calendars.length);
  }

  protected async submit(form: HTMLFormElement): Promise<string | void> {
    const { ctx } = this;
    const title = value(form, "title").trim();
    if (!title) return this.t("add.need_title");
    const calendar = value(form, "calendar");
    await ctx.api.addToCalendar({
      spot: ctx.spot!.id,
      sailor: ctx.sailor!.id,
      boat: ctx.boat!.id,
      calendar,
      start: value(form, "start"),
      end: value(form, "end"),
      title,
      watch: (form.elements.namedItem("watch") as HTMLInputElement).checked,
    });
    ctx.act.setCalendar(calendar);
    const chosen = ctx.config.calendars.find((item) => item.entity_id === calendar);
    ctx.act.toast(this.t("add.added", { calendar: calendarLabel(chosen, calendar) }));
  }
}

/** A sailing window that's in a calendar: how its forecast looks, and taking it out. */
export class ScPlannedDialog extends ScDialog {
  static override properties = { ...ScDialog.properties, sail: { attribute: false } };
  declare sail: PlannedSail;

  protected heading(): string {
    return addText(this.ctx, this.sail);
  }

  protected body(): TemplateResult {
    const { ctx, sail } = this;
    const { t, fmt } = ctx;
    const calendar = ctx.config.calendars.find((item) => item.entity_id === sail.calendar);
    const sailor = ctx.config.sailors.find((item) => item.id === sail.sailor);
    const explanation = sail.auto
      ? t("planned.auto_explain", { sailor: sailor?.name ?? "" })
      : sail.watch
        ? t("planned.watching")
        : t("planned.not_watching");
    return html`
      <div class="evt">
        ${icon(addIcon(sail))}
        <b
          >${fmt.longDate(localTime(sail.start, fmt.zone).date)} ·
          ${fmt.span(sail.start, sail.end)}</b
        >
        <span>${sail.title} · ${calendarLabel(calendar, sail.calendar)}</span>
      </div>
      <p class="hint">${plannedStatus(ctx, sail)}. ${explanation}</p>
      ${
        sail.can_delete
          ? nothing
          : html`<p class="hint">
              ${t("planned.cannot_delete", { calendar: calendar?.via ?? sail.calendar })}
            </p>`
      }
    `;
  }

  protected footer(): TemplateResult {
    const { sail } = this;
    return html`<button
        type="button"
        class="btn btn-danger"
        ?disabled=${this.busy}
        @click=${() => this.remove_()}
      >
        ${icon("calRemove")}<span
          >${this.t(sail.can_delete ? "planned.take_out" : "planned.stop_tracking")}</span
        >
      </button>
      <span class="grow"></span>
      <button type="submit" class="btn btn-primary">${this.t("dialog.done")}</button>`;
  }

  private async remove_(): Promise<void> {
    const { ctx, sail } = this;
    this.busy = true;
    try {
      const result = await ctx.api.removeFromCalendar(sail.id);
      const calendar = ctx.config.calendars.find((item) => item.entity_id === sail.calendar);
      ctx.act.toast(
        result.deleted
          ? this.t("planned.removed", { calendar: calendarLabel(calendar, sail.calendar) })
          : this.t("planned.stopped"),
      );
      this.close();
    } catch (err) {
      this.error = String((err as { message?: string }).message ?? err);
    } finally {
      this.busy = false;
    }
  }

  protected async submit(): Promise<string | void> {
    return undefined;
  }
}

/** Turn a sailor's automatic adding on or off, and set it up. */
export class ScAutoDialog extends ScDialog {
  static override properties = {
    ...ScDialog.properties,
    sailorId: { type: String },
    on: { state: true },
  };
  declare sailorId: string;
  declare on?: boolean;

  private get sailor() {
    return this.ctx.config.sailors.find((item) => item.id === this.sailorId)!;
  }

  protected heading(): string {
    return this.t("auto.title", { sailor: this.sailor.name });
  }

  protected body(): TemplateResult {
    const { ctx } = this;
    const { t, fmt } = ctx;
    const sailor = this.sailor;
    const auto: AutoCalendar = sailor.auto_calendar ?? {
      calendar: ctx.calendar ?? ctx.config.calendars[0]?.entity_id ?? "",
      days: ["sat", "sun"],
      min_score: 60,
      ahead: 2,
      spots: ctx.config.spots.map((spot) => spot.id),
    };
    const on = this.on ?? Boolean(sailor.auto_calendar);
    const boat = ctx.config.boats.find((item) => item.id === sailor.boats[0]);
    const skipped = ctx.planned?.skipped[sailor.id] ?? [];
    const calendars = ctx.config.calendars;
    return html`
      <label class="switch big">
        <input
          type="checkbox"
          name="on"
          .checked=${on}
          @change=${(event: Event) => (this.on = (event.target as HTMLInputElement).checked)}
        />
        <span>${t("auto.switch", { sailor: sailor.name })}</span>
      </label>
      <div class="fld" ?hidden=${!on} style="gap:16px">
        ${
          calendars.length
            ? html`<label class="fld">
                <span class="lbl">${t("add.calendar")}</span>
                <select name="calendar">
                  ${calendars.map(
                    (item) =>
                      html`<option
                        value=${item.entity_id}
                        ?selected=${item.entity_id === auto.calendar}
                      >
                        ${calendarLabel(item, item.entity_id)}
                      </option>`,
                  )}
                </select>
              </label>`
            : html`<p class="form-err">${t("add.no_calendars")}</p>`
        }
        <fieldset class="fld">
          <legend class="lbl">${t("auto.days")}</legend>
          <div class="daypick">
            ${WEEKDAYS.map(
              (day) =>
                html`<label class="dayt"
                  ><input
                    type="checkbox"
                    name="days"
                    value=${day}
                    ?checked=${auto.days.includes(day)}
                  /><span>${t(`weekday.${day}`)}</span></label
                >`,
            )}
          </div>
        </fieldset>
        <fieldset class="fld">
          <legend class="lbl">${t("auto.min_score")}</legend>
          <div class="opts two">
            ${[60, 80].map(
              (score) =>
                html`<label class="opt"
                  ><input
                    type="radio"
                    name="min_score"
                    value=${score}
                    ?checked=${auto.min_score === score}
                  /><span class="opt-t"
                    ><b>${t(`auto.score_${score}`)}</b
                    ><span>${t(`auto.score_${score}_hint`)}</span></span
                  ></label
                >`,
            )}
          </div>
        </fieldset>
        <label class="fld">
          <span class="lbl">${t("auto.ahead")}</span>
          <select name="ahead">
            ${AHEAD.map(
              (days) =>
                html`<option value=${days} ?selected=${auto.ahead === days}>
                  ${t(`ahead.${days}`)}
                </option>`,
            )}
          </select>
          <span class="hint">${t("auto.ahead_hint")}</span>
        </label>
        <fieldset class="fld">
          <legend class="lbl">${t("auto.spots")}</legend>
          <div class="checks">
            ${ctx.config.spots.map(
              (spot) =>
                html`<label class="check"
                  ><input
                    type="checkbox"
                    name="spots"
                    value=${spot.id}
                    ?checked=${auto.spots.includes(spot.id)}
                  /><span>${spot.name}</span></label
                >`,
            )}
          </div>
          <span class="hint">${t("auto.spots_hint")}</span>
        </fieldset>
        <div class="desc">
          ${t("auto.explain", { boat: boat?.name ?? "", sailor: sailor.name })}
        </div>
        ${
          skipped.length
            ? html`<fieldset class="fld">
                <legend class="lbl">${t("auto.skipped")}</legend>
                <div class="checks">
                  ${skipped.map(
                    (day) =>
                      html`<label class="check"
                        ><input type="checkbox" name="skipped" value=${day} checked /><span
                          >${t("auto.skipped_day", { day: fmt.longDate(day) })}</span
                        ></label
                      >`,
                  )}
                </div>
              </fieldset>`
            : nothing
        }
      </div>
    `;
  }

  protected footer(): TemplateResult {
    return this.actions(this.t("dialog.save"));
  }

  protected async submit(form: HTMLFormElement): Promise<string | void> {
    const { ctx } = this;
    const sailor = this.sailor;
    const on = (form.elements.namedItem("on") as HTMLInputElement).checked;
    let auto: AutoCalendar | null = null;
    if (on) {
      const days = checked(form, "days");
      const spots = checked(form, "spots");
      if (!days.length) return this.t("auto.need_day");
      if (!spots.length) return this.t("auto.need_spot");
      if (!value(form, "calendar")) return this.t("add.no_calendars");
      auto = {
        calendar: value(form, "calendar"),
        days,
        min_score: Number(value(form, "min_score")),
        ahead: Number(value(form, "ahead")),
        spots,
      };
    }
    const { id, name, ...data } = sailor;
    const result = await ctx.api.save("sailor", name, { ...data, auto_calendar: auto }, id);
    if (result.errors) {
      return Object.values(result.errors)
        .map((key) => this.t(`error.${key}`))
        .join(" ");
    }
    const skipped = ctx.planned?.skipped[sailor.id] ?? [];
    const kept = checked(form, "skipped");
    if (kept.length !== skipped.length) await ctx.api.setSkipped(sailor.id, kept);
    ctx.act.toast(this.t(on ? "auto.saved_on" : "auto.saved_off", { sailor: name }));
  }
}

define("sc-window-dialog", ScWindowDialog);
define("sc-planned-dialog", ScPlannedDialog);
define("sc-auto-dialog", ScAutoDialog);

declare global {
  interface HTMLElementTagNameMap {
    "sc-window-dialog": ScWindowDialog;
    "sc-planned-dialog": ScPlannedDialog;
    "sc-auto-dialog": ScAutoDialog;
  }
}
