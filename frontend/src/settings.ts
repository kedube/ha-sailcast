/**
 * The Settings tab: sailors, boats and spots, and everything in your
 * calendars. Only administrators can change them; everyone else sees them
 * read-only, as in Home Assistant's own settings pages.
 */
import { html, nothing, type TemplateResult } from "lit";

import type { Ctx } from "./context";
import { localTime } from "./format";
import { icon } from "./glyphs";
import type { Sailor, SizeClass, Skill } from "./types";
import { addIcon, autoSummary, daysText, plannedStatus } from "./week";

const SKILL_LEVELS: Record<Skill, number> = { beginner: 1, intermediate: 2, advanced: 3 };

/** Bars that fill with skill, for each level. */
export function skillBars(skill: Skill): TemplateResult {
  const level = SKILL_LEVELS[skill];
  return html`<span class="bars" aria-hidden="true"
    >${[1, 2, 3].map((bar) => html`<i class=${bar <= level ? "on" : ""}></i>`)}</span
  >`;
}

/**
 * A boat size's limits as scales: where caution, not recommended and
 * dangerous start for wind, gusts and waves.
 */
export function limitBars(ctx: Ctx, size: SizeClass): TemplateResult {
  const { t, fmt } = ctx;
  const limits = ctx.config.limits[size];
  const bar = (label: string, starts: number[], top: number, unit: string): TemplateResult => {
    const edges = [0, ...starts, top];
    const levels =
      starts.length === 2
        ? ["good", "caution", "dangerous"]
        : ["good", "caution", "not_recommended", "dangerous"];
    return html`<div class="lim">
      <span>${label}</span>
      <div class="lim-track">
        <div class="lim-bar">
          ${levels.map(
            (level, index) =>
              html`<i class="lb-${level}" style="--w:${edges[index + 1] - edges[index]}"></i>`,
          )}
        </div>
        ${starts.map(
          (start) =>
            html`<span class="lim-t" style="--a:${start / top}"
              >${fmt.number(start, Number.isInteger(start) ? 0 : 1)}</span
            >`,
        )}
      </div>
      <span>${unit}</span>
    </div>`;
  };
  const waves = limits.wave.map((height) => Math.round(fmt.height(height) * 10) / 10);
  return html`<div class="lims">
    ${bar(t("limits.wind"), limits.wind, 40, t("unit.knots_short"))}
    ${bar(t("limits.gusts"), limits.gust, 48, t("unit.knots_short"))}
    ${bar(
      t("limits.waves"),
      waves,
      fmt.feet ? 15 : 4.5,
      fmt.feet ? t("unit.feet_short") : t("unit.meters_short"),
    )}
  </div>`;
}

function sailingTimes(ctx: Ctx, sailor: Sailor): string {
  const { t, fmt } = ctx;
  const time = (value: string | null, fallback: string): string =>
    value ? fmt.hourOf("2026-11-02", Number(value.slice(0, 2))) : t(fallback);
  return t("settings.times", {
    days: daysText(ctx, sailor.days),
    start: time(sailor.start, "settings.sunrise"),
    end: time(sailor.end, "settings.sunset"),
  });
}

function avatar(name: string, index: number, small = false): TemplateResult {
  return html`<span
    class="avatar ${small ? "sm" : ""}"
    style="--av:var(--sc-av${(index % 4) + 1})"
    aria-hidden="true"
    >${name.charAt(0).toUpperCase()}</span
  >`;
}

export function settingsView(ctx: Ctx): TemplateResult {
  const { t, fmt } = ctx;
  const config = ctx.config;
  const admin = ctx.admin;
  const users = new Map(config.users.map((user) => [user.id, user.name]));
  const boats = new Map(config.boats.map((boat) => [boat.id, boat]));
  const people = config.sailors.map(
    (sailor, index) =>
      html`<article class="person">
        <div class="person-top">
          ${avatar(sailor.name, index)}
          <div>
            <h3>${sailor.name}</h3>
            <span class="small"
              >${
                sailor.user
                  ? t("settings.linked", { user: users.get(sailor.user) ?? t("settings.someone") })
                  : t("settings.not_linked")
              }</span
            >
          </div>
          ${
            admin
              ? html`<button
                  type="button"
                  class="icon-btn"
                  aria-label=${t("settings.edit_name", { name: sailor.name })}
                  @click=${() => ctx.act.editSailor(sailor.id)}
                >
                  ${icon("pencil")}
                </button>`
              : nothing
          }
        </div>
        <div class="skill-line">
          ${skillBars(sailor.skill)}
          <div>
            <b>${t(`skill.${sailor.skill}`)}</b
            ><span class="small">${t(`skill_text.${sailor.skill}`)}</span>
          </div>
        </div>
        <div class="ci">
          ${icon("sail")}<span
            >${sailor.boats.map(
              (id, number) =>
                html`${number ? ", " : ""}${boats.get(id)?.name ?? id}${
                  number === 0 && sailor.boats.length > 1
                    ? html`<span class="tag">${t("settings.default")}</span>`
                    : nothing
                }`,
            )}</span
          >
        </div>
        <div class="ci">${icon("clock")}<span>${sailingTimes(ctx, sailor)}</span></div>
      </article>`,
  );
  const boatRows = config.boats.map((boat) => {
    const sailors = config.sailors.filter((sailor) => sailor.boats.includes(boat.id));
    const length = fmt.feet ? boat.length * 3.28084 : boat.length;
    return html`<article class="row">
      <div>
        <h3>${boat.name}</h3>
        <span class="small"
          >${t(`size_class.${boat.size_class}`)} ·
          ${t(fmt.feet ? "unit.feet" : "unit.meters", { value: fmt.number(length, fmt.feet ? 0 : 1) })}</span
        >
        <span class="small"
          >${
            sailors.length
              ? t("settings.sailed_by", {
                  sailors: sailors.map((sailor) => sailor.name).join(", "),
                })
              : t("settings.no_sailors")
          }</span
        >
      </div>
      ${limitBars(ctx, boat.size_class)}
      ${
        admin
          ? html`<button
              type="button"
              class="icon-btn"
              aria-label=${t("settings.edit_name", { name: boat.name })}
              @click=${() => ctx.act.editBoat(boat.id)}
            >
              ${icon("pencil")}
            </button>`
          : html`<span></span>`
      }
    </article>`;
  });
  const spotRows = config.spots.map((spot) => {
    const radius = fmt.miles ? spot.radius / 1609.344 : spot.radius / 1000;
    const source = (key: "tide_station" | "current_station" | "marine_zone") => {
      const id = spot[key];
      if (!id) return nothing;
      const name = spot.source_names[key];
      return html`<dt>${t(`spot.${key}_short`)}</dt>
        <dd>${name ? `${name} (${id.split("_")[0]})` : id.split("_")[0]}</dd>`;
    };
    return html`<article class="row">
      <div>
        <h3>${spot.name}</h3>
        <span class="small"
          >${t(`water_type.${spot.water_type}`)} · ${fmt.number(Math.abs(spot.latitude), 3)}°
          ${spot.latitude >= 0 ? "N" : "S"}, ${fmt.number(Math.abs(spot.longitude), 3)}°
          ${spot.longitude >= 0 ? "E" : "W"} ·
          ${t(fmt.miles ? "settings.map_miles" : "settings.map_km", { value: fmt.number(radius) })}</span
        >
      </div>
      <dl class="srcs">
        ${source("tide_station")} ${source("current_station")} ${source("marine_zone")}
        ${
          !spot.tide_station && !spot.current_station && !spot.marine_zone
            ? html`<dt>${t("settings.sources")}</dt>
                <dd>${t("spot.none")}</dd>`
            : nothing
        }
      </dl>
      ${
        admin
          ? html`<button
              type="button"
              class="icon-btn"
              aria-label=${t("settings.edit_name", { name: spot.name })}
              @click=${() => ctx.act.editSpot(spot.id)}
            >
              ${icon("pencil")}
            </button>`
          : html`<span></span>`
      }
    </article>`;
  });
  const autos = config.sailors.map((sailor, index) => {
    const auto = sailor.auto_calendar;
    return html`<div class="auto-row">
      ${avatar(sailor.name, index, true)}
      <div>
        <b>${sailor.name}</b>
        <span class="small"
          >${
            auto
              ? t("auto.on_summary", { summary: autoSummary(ctx, auto) })
              : t("auto.off_row", { sailor: sailor.name })
          }</span
        >
      </div>
      ${
        admin
          ? html`<button
              type="button"
              class="btn btn-text"
              @click=${() => ctx.act.openAuto(sailor.id)}
            >
              ${t(auto ? "auto.change" : "auto.set_up")}
            </button>`
          : html`<span></span>`
      }
    </div>`;
  });
  const planned = (ctx.planned?.planned ?? []).map((sail) => {
    const sailor = config.sailors.find((item) => item.id === sail.sailor);
    const boat = boats.get(sail.boat);
    const calendar = config.calendars.find((item) => item.entity_id === sail.calendar);
    return html`<li class="prow ${sail.status.worse ? "worse" : ""}">
      ${icon(sail.status.worse ? "calAlert" : addIcon(sail))}
      <div>
        <b
          >${fmt.longDate(localTime(sail.start, fmt.zone).date)} ·
          ${fmt.span(sail.start, sail.end)}</b
        >${sail.auto ? html`<span class="tag">${t("settings.automatic")}</span>` : nothing}
        <span class="small"
          >${sail.title} · ${calendar ? `${calendar.name} (${calendar.via})` : sail.calendar} ·
          ${sailor?.name ?? ""}, ${boat?.name ?? ""}</span
        >
        <span class="pstat"
          >${plannedStatus(ctx, sail)}${sail.watch ? "" : ` · ${t("settings.warnings_off")}`}</span
        >
      </div>
      <button type="button" class="btn btn-text" @click=${() => ctx.act.removePlanned(sail)}>
        ${t(sail.can_delete ? "settings.take_out" : "planned.stop_tracking")}
      </button>
    </li>`;
  });
  return html`
    <div class="notice">
      ${icon("shield")}
      <p>${t(admin ? "settings.admin_note" : "settings.read_only_note")}</p>
    </div>
    <section class="card sec">
      <div class="sec-head">
        <div>
          <h2>${t("settings.sailors")}</h2>
          <p class="small">${t("settings.sailors_sub")}</p>
        </div>
        ${
          admin
            ? html`<button
                type="button"
                class="btn btn-tonal"
                ?disabled=${!config.boats.length}
                title=${config.boats.length ? "" : t("settings.boat_first")}
                @click=${() => ctx.act.editSailor()}
              >
                ${icon("plus")}${t("settings.add_sailor")}
              </button>`
            : nothing
        }
      </div>
      ${
        people.length
          ? html`<div class="people">${people}</div>`
          : html`<p class="empty">
              ${t(config.boats.length ? "settings.no_sailors_yet" : "settings.boat_first")}
            </p>`
      }
    </section>
    <section class="card sec">
      <div class="sec-head">
        <div>
          <h2>${t("settings.boats")}</h2>
          <p class="small">${t("settings.boats_sub")}</p>
        </div>
        ${
          admin
            ? html`<button type="button" class="btn btn-tonal" @click=${() => ctx.act.editBoat()}>
                ${icon("plus")}${t("settings.add_boat")}
              </button>`
            : nothing
        }
      </div>
      ${
        boatRows.length
          ? html`<div class="rows">${boatRows}</div>`
          : html`<p class="empty">${t("settings.no_boats_yet")}</p>`
      }
    </section>
    <section class="card sec">
      <div class="sec-head">
        <div>
          <h2>${t("settings.spots")}</h2>
          <p class="small">${t("settings.spots_sub")}</p>
        </div>
        ${
          admin
            ? html`<button type="button" class="btn btn-tonal" @click=${() => ctx.act.editSpot()}>
                ${icon("plus")}${t("settings.add_spot")}
              </button>`
            : nothing
        }
      </div>
      ${
        spotRows.length
          ? html`<div class="rows">${spotRows}</div>`
          : html`<p class="empty">${t("settings.no_spots_yet")}</p>`
      }
    </section>
    <section class="card sec">
      <div class="sec-head">
        <div>
          <h2>${t("settings.calendar")}</h2>
          <p class="small">${t("settings.calendar_sub")}</p>
        </div>
      </div>
      ${
        config.calendars.length
          ? html`<label class="fld">
              <span class="lbl">${t("settings.default_calendar")}</span>
              <select
                @change=${(event: Event) => ctx.act.setCalendar((event.target as HTMLSelectElement).value)}
              >
                ${config.calendars.map(
                  (calendar) =>
                    html`<option
                      value=${calendar.entity_id}
                      ?selected=${calendar.entity_id === ctx.calendar}
                    >
                      ${calendar.name} (${calendar.via})
                    </option>`,
                )}
              </select>
              <span class="hint">${t("settings.default_calendar_hint")}</span>
            </label>`
          : html`<p class="empty">${t("add.no_calendars")}</p>`
      }
      <div class="cal-info">
        ${icon("calSync")}
        <p>
          ${t("settings.read_only_calendars", {
            calendars: config.sailors
              .map((sailor) => t("settings.sailor_calendar", { name: sailor.name }))
              .join(", "),
          })}
        </p>
      </div>
      ${
        config.sailors.length
          ? html`<h3 class="sub">${t("settings.automatic_title")}</h3>
              <div class="auto-rows">${autos}</div>`
          : nothing
      }
      <h3 class="sub">${t("settings.in_calendars")}</h3>
      ${
        planned.length
          ? html`<ul class="plist">
              ${planned}
            </ul>`
          : html`<p class="empty">${t("settings.nothing_planned")}</p>`
      }
    </section>
  `;
}
