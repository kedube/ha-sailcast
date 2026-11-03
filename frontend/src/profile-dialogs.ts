/**
 * Adding and editing sailors, boats and spots. Changes go through the same
 * checks as Home Assistant's setup dialogs and land in the same place, so
 * Settings → Devices & services always shows the same thing.
 */
import { html, nothing, type TemplateResult } from "lit";

import { checked, define, numberOrNull, ScDialog, value } from "./dialog";
import { FEET_PER_METER, KM_PER_MILE, WEEKDAYS } from "./format";
import { limitBars, skillBars } from "./settings";
import "./spot-map";
import type { StationMark } from "./spot-map";
import type { Comfort, SizeClass, Skill, SourceKey, SourceSuggestions, Spot } from "./types";
import { SIZES } from "./week";

const SKILLS: Skill[] = ["beginner", "intermediate", "advanced"];
const WATER = ["open_coast", "bay", "river", "lake"];
const DIRECTIONS = ["n", "ne", "e", "se", "s", "sw", "w", "nw"];
const SOURCES: SourceKey[] = ["tide_station", "current_station", "marine_zone"];
const HOURS = Array.from({ length: 17 }, (_, index) => index + 5);

/** A field's error from the server, under the field. */
function fieldError(errors: Record<string, string>, key: string, t: (key: string) => string) {
  return errors[key] ? html`<p class="fld-err">${t(`error.${errors[key]}`)}</p>` : nothing;
}

abstract class ProfileDialog extends ScDialog {
  static override properties = {
    ...ScDialog.properties,
    profileId: { type: String },
    errors: { state: true },
  };
  declare profileId?: string;
  declare errors: Record<string, string>;

  constructor() {
    super();
    this.errors = {};
  }

  protected err(key: string) {
    return fieldError(this.errors, key, (name) => this.t(name));
  }

  /** Save, keeping field errors by field and the rest above the form. */
  protected async save(
    kind: "spot" | "boat" | "sailor",
    name: string,
    data: Record<string, unknown>,
  ): Promise<string | void> {
    const result = await this.ctx.api.save(kind, name, data, this.profileId);
    if (result.errors) {
      this.errors = result.errors;
      return this.t("error.check_fields");
    }
    this.ctx.act.toast(
      this.t(this.profileId ? "settings.saved" : "settings.added", { name: name.trim() }),
    );
  }

  protected async delete_(kind: "spot" | "boat" | "sailor", name: string): Promise<string | void> {
    const result = await this.ctx.api.remove(kind, this.profileId!);
    if (result.errors) {
      return this.t(`error.${result.errors.base}`, { sailor: result.sailor ?? "" });
    }
    this.ctx.act.toast(this.t("settings.deleted", { name }));
  }
}

export class ScSailorDialog extends ProfileDialog {
  static override properties = { ...ProfileDialog.properties, boats: { state: true } };
  /** The boats ticked so far, for the usual-boat choice. */
  declare boats?: string[];

  private get sailor() {
    return this.ctx.config.sailors.find((item) => item.id === this.profileId);
  }

  protected heading(): string {
    const sailor = this.sailor;
    return sailor ? this.t("sailor.edit", { name: sailor.name }) : this.t("sailor.add");
  }

  protected body(): TemplateResult {
    const { ctx } = this;
    const { t, fmt } = ctx;
    const sailor = this.sailor;
    const boats =
      this.boats ?? sailor?.boats ?? ctx.config.boats.slice(0, 1).map((boat) => boat.id);
    const skill = sailor?.skill ?? "beginner";
    const days = sailor?.days ?? [...WEEKDAYS];
    const comfort: Comfort = sailor?.comfort ?? {
      ideal_low: null,
      ideal_high: null,
      coldest: null,
      rain: "some",
    };
    const hour = (time: string | null | undefined): number | null =>
      time ? Number(time.slice(0, 2)) : null;
    const coldest = comfort.coldest === null ? "" : fmt.number(fmt.temperature(comfort.coldest));
    return html`
      <label class="fld">
        <span class="lbl">${t("profile.name")}</span>
        <input
          type="text"
          name="name"
          maxlength="40"
          autocomplete="off"
          .value=${sailor?.name ?? ""}
        />
        ${this.err("name")}
      </label>
      <fieldset class="fld">
        <legend class="lbl">${t("sailor.skill")}</legend>
        <div class="opts">
          ${SKILLS.map(
            (level) =>
              html`<label class="opt">
                <input type="radio" name="skill" value=${level} ?checked=${skill === level} />
                <span class="opt-t"
                  ><b>${t(`skill.${level}`)}</b><span>${t(`skill_text.${level}`)}</span></span
                >
                ${skillBars(level)}
              </label>`,
          )}
        </div>
        <p class="hint">${t("sailor.skill_hint")}</p>
      </fieldset>
      <fieldset class="fld">
        <legend class="lbl">${t("sailor.boats")}</legend>
        <div class="checks">
          ${ctx.config.boats.map(
            (boat) =>
              html`<label class="check">
                <input
                  type="checkbox"
                  name="boats"
                  value=${boat.id}
                  ?checked=${boats.includes(boat.id)}
                  @change=${(event: Event) => {
                    const form = (event.target as HTMLInputElement).form!;
                    this.boats = checked(form, "boats");
                  }}
                />
                <span
                  >${boat.name}
                  <span class="muted">· ${t(`size_class.${boat.size_class}`)}</span></span
                >
              </label>`,
          )}
        </div>
        ${this.err("boats")}
      </fieldset>
      <label class="fld">
        <span class="lbl">${t("sailor.default_boat")}</span>
        <select name="default">
          ${boats.map(
            (id) =>
              html`<option value=${id} ?selected=${id === boats[0]}>
                ${ctx.config.boats.find((boat) => boat.id === id)?.name ?? id}
              </option>`,
          )}
        </select>
      </label>
      <fieldset class="fld">
        <legend class="lbl">${t("sailor.when")}</legend>
        <div class="daypick">
          ${WEEKDAYS.map(
            (day) =>
              html`<label class="dayt"
                ><input
                  type="checkbox"
                  name="days"
                  value=${day}
                  ?checked=${days.includes(day)}
                /><span>${t(`weekday.${day}`)}</span></label
              >`,
          )}
        </div>
        ${this.err("days")}
        <div class="two" style="margin-top:6px">
          <label class="fld">
            <span class="lbl">${t("sailor.from")}</span>
            <select name="start">
              <option value="">${t("sailor.sunrise")}</option>
              ${HOURS.map(
                (value) =>
                  html`<option value=${value} ?selected=${hour(sailor?.start) === value}>
                    ${fmt.hourOf("2026-11-02", value)}
                  </option>`,
              )}
            </select>
          </label>
          <label class="fld">
            <span class="lbl">${t("sailor.until")}</span>
            <select name="end">
              <option value="">${t("sailor.sunset")}</option>
              ${HOURS.map(
                (value) =>
                  html`<option value=${value} ?selected=${hour(sailor?.end) === value}>
                    ${fmt.hourOf("2026-11-02", value)}
                  </option>`,
              )}
            </select>
          </label>
        </div>
        ${this.err("end")}
        <p class="hint">${t("sailor.when_hint")}</p>
      </fieldset>
      <fieldset class="fld">
        <legend class="lbl">${t("sailor.comfort")}</legend>
        <div class="two">
          <label class="fld">
            <span class="lbl">${t("sailor.ideal_low")}</span>
            <input
              type="number"
              name="ideal_low"
              min="0"
              max="40"
              step="1"
              inputmode="numeric"
              .value=${comfort.ideal_low === null ? "" : String(comfort.ideal_low)}
            />
            ${this.err("ideal_low")}
          </label>
          <label class="fld">
            <span class="lbl">${t("sailor.ideal_high")}</span>
            <input
              type="number"
              name="ideal_high"
              min="0"
              max="40"
              step="1"
              inputmode="numeric"
              .value=${comfort.ideal_high === null ? "" : String(comfort.ideal_high)}
            />
            ${this.err("ideal_high")}
          </label>
        </div>
        <p class="hint">${t("sailor.ideal_hint")}</p>
        <label class="fld">
          <span class="lbl">${t("sailor.coldest", { unit: fmt.fahrenheit ? "°F" : "°C" })}</span>
          <input type="number" name="coldest" step="1" inputmode="numeric" .value=${coldest} />
          ${this.err("coldest")}
          <span class="hint"
            >${t("sailor.coldest_hint", { default: fmt.fahrenheit ? "50 °F" : "10 °C" })}</span
          >
        </label>
        <div class="opts">
          ${(["avoid", "some", "any"] as const).map(
            (rain) =>
              html`<label class="opt">
                <input type="radio" name="rain" value=${rain} ?checked=${comfort.rain === rain} />
                <span class="opt-t"><b>${t(`rain.${rain}`)}</b></span>
              </label>`,
          )}
        </div>
        <p class="hint">${t("sailor.comfort_hint")}</p>
      </fieldset>
      ${
        ctx.config.users.length
          ? html`<label class="fld">
              <span class="lbl">${t("sailor.user")}</span>
              <select name="user">
                <option value="">${t("sailor.no_user")}</option>
                ${ctx.config.users.map(
                  (user) =>
                    html`<option value=${user.id} ?selected=${sailor?.user === user.id}>
                      ${user.name}
                    </option>`,
                )}
              </select>
              <span class="hint">${t("sailor.user_hint")}</span>
              ${this.err("user")}
            </label>`
          : nothing
      }
    `;
  }

  protected footer(): TemplateResult {
    const sailor = this.sailor;
    return html`${
      sailor ? this.deleteButton(sailor.name, () => this.delete_("sailor", sailor.name)) : nothing
    }${this.actions(this.t("dialog.save"))}`;
  }

  protected async submit(form: HTMLFormElement): Promise<string | void> {
    const { fmt } = this.ctx;
    const name = value(form, "name");
    if (!name.trim()) return this.t("error.name_required");
    const boats = checked(form, "boats");
    const first = value(form, "default");
    const start = value(form, "start");
    const end = value(form, "end");
    const coldest = numberOrNull(form, "coldest");
    const time = (hour: string): string | null => (hour ? `${hour.padStart(2, "0")}:00:00` : null);
    return this.save("sailor", name, {
      skill: value(form, "skill"),
      boats: boats.includes(first) ? [first, ...boats.filter((boat) => boat !== first)] : boats,
      days: checked(form, "days"),
      start: time(start),
      end: time(end),
      user: value(form, "user") || null,
      comfort: {
        ideal_low: numberOrNull(form, "ideal_low"),
        ideal_high: numberOrNull(form, "ideal_high"),
        coldest: coldest === null ? null : Math.round(fmt.celsius(coldest) * 10) / 10,
        rain: value(form, "rain") || "some",
      },
      auto_calendar: this.sailor?.auto_calendar ?? null,
    });
  }
}

export class ScBoatDialog extends ProfileDialog {
  static override properties = { ...ProfileDialog.properties, size: { state: true } };
  declare size?: SizeClass;

  private get boat() {
    return this.ctx.config.boats.find((item) => item.id === this.profileId);
  }

  protected heading(): string {
    const boat = this.boat;
    return boat ? this.t("boat.edit", { name: boat.name }) : this.t("boat.add");
  }

  protected body(): TemplateResult {
    const { ctx } = this;
    const { t, fmt } = ctx;
    const boat = this.boat;
    const size = this.size ?? boat?.size_class ?? "small_keelboat";
    const length = boat ? fmt.number(fmt.feet ? boat.length * FEET_PER_METER : boat.length, 1) : "";
    return html`
      <label class="fld">
        <span class="lbl">${t("profile.name")}</span>
        <input
          type="text"
          name="name"
          maxlength="40"
          autocomplete="off"
          .value=${boat?.name ?? ""}
        />
        ${this.err("name")}
      </label>
      <fieldset class="fld">
        <legend class="lbl">${t("boat.size")}</legend>
        <div class="opts">
          ${SIZES.map((item) => {
            const limits = ctx.config.limits[item];
            return html`<label class="opt">
              <input
                type="radio"
                name="size_class"
                value=${item}
                ?checked=${size === item}
                @change=${() => (this.size = item)}
              />
              <span class="opt-t"
                ><b>${t(`size_class.${item}`)}</b
                ><span
                  >${t("boat.size_hint", {
                    lengths: t(`size_lengths.${item}`),
                    caution: limits.wind[0],
                    dangerous: limits.wind[1],
                  })}</span
                ></span
              >
            </label>`;
          })}
        </div>
      </fieldset>
      <div class="two">
        <label class="fld">
          <span class="lbl">${t(fmt.feet ? "boat.length_feet" : "boat.length_meters")}</span>
          <input
            type="number"
            name="length"
            min="1"
            step="0.1"
            inputmode="decimal"
            .value=${length}
          />
          ${this.err("length")}
        </label>
      </div>
      <div class="fld">
        <span class="lbl">${t("boat.limits")}</span>
        <div class="lims-preview">${limitBars(ctx, size)}</div>
      </div>
    `;
  }

  protected footer(): TemplateResult {
    const boat = this.boat;
    return html`${
      boat ? this.deleteButton(boat.name, () => this.delete_("boat", boat.name)) : nothing
    }${this.actions(this.t("dialog.save"))}`;
  }

  protected async submit(form: HTMLFormElement): Promise<string | void> {
    const name = value(form, "name");
    if (!name.trim()) return this.t("error.name_required");
    const length = numberOrNull(form, "length");
    if (length === null || length <= 0) {
      this.errors = { length: "length_out_of_range" };
      return this.t("error.check_fields");
    }
    const meters = this.ctx.fmt.feet ? length / FEET_PER_METER : length;
    return this.save("boat", name, {
      size_class: value(form, "size_class"),
      length: Math.round(meters * 1000) / 1000,
    });
  }
}

export class ScSpotDialog extends ProfileDialog {
  static override properties = {
    ...ProfileDialog.properties,
    latitude: { state: true },
    longitude: { state: true },
    radius: { state: true },
    found: { state: true },
    chosen: { state: true },
  };
  declare latitude: number;
  declare longitude: number;
  /** Meters. */
  declare radius: number;
  declare found?: SourceSuggestions;
  /** Sources picked so far: an ID, or "" for none. */
  declare chosen: Partial<Record<SourceKey, string>>;
  private lookup?: number;

  private get spot(): Spot | undefined {
    return this.ctx.config.spots.find((item) => item.id === this.profileId);
  }

  override connectedCallback(): void {
    super.connectedCallback();
    if (this.latitude !== undefined) return;
    const spot = this.spot;
    this.latitude = spot?.latitude ?? this.ctx.hass.config.latitude;
    this.longitude = spot?.longitude ?? this.ctx.hass.config.longitude;
    this.radius = spot?.radius ?? 15_000;
    this.chosen = spot ? Object.fromEntries(SOURCES.map((key) => [key, spot[key] ?? ""])) : {};
    void this.suggest();
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    window.clearTimeout(this.lookup);
  }

  /** Look up the sources near the pin, and pick the nearest for a new spot. */
  private async suggest(): Promise<void> {
    try {
      const found = await this.ctx.api.sources(this.latitude, this.longitude);
      this.found = found;
      if (!this.spot) {
        const chosen = { ...this.chosen };
        for (const key of SOURCES) {
          if (!(key in this.touched)) chosen[key] = found.suggested[key] ?? "";
        }
        this.chosen = chosen;
      }
    } catch {
      this.found = {
        tide_station: [],
        current_station: [],
        marine_zone: [],
        suggested: { tide_station: null, current_station: null, marine_zone: null },
        failed: true,
      };
    }
  }

  /** The sources someone picked by hand, which a moved pin leaves alone. */
  private touched: Partial<Record<SourceKey, true>> = {};

  private pinMoved(event: CustomEvent<{ latitude: number; longitude: number }>): void {
    this.latitude = Math.round(event.detail.latitude * 100_000) / 100_000;
    this.longitude = Math.round(event.detail.longitude * 100_000) / 100_000;
    window.clearTimeout(this.lookup);
    this.lookup = window.setTimeout(() => void this.suggest(), 700);
  }

  protected heading(): string {
    const spot = this.spot;
    return spot ? this.t("spot.edit", { name: spot.name }) : this.t("spot.add");
  }

  /** The suggested tide and current stations, to show on the map. */
  private stations(): StationMark[] {
    const found = this.found;
    if (!found) return [];
    const marks: StationMark[] = [];
    for (const [key, kind] of [
      ["tide_station", "tide"],
      ["current_station", "current"],
    ] as const) {
      for (const choice of found[key]) {
        if (choice.latitude === null || choice.longitude === null) continue;
        marks.push({
          kind,
          id: choice.id,
          label: this.t(`spot.${kind}_mark`, {
            name: choice.name,
            id: choice.id.split("_")[0],
          }),
          latitude: choice.latitude,
          longitude: choice.longitude,
        });
      }
    }
    return marks;
  }

  private distance(km: number): string {
    const { t, fmt } = this.ctx;
    return t(fmt.miles ? "unit.miles" : "unit.km", { value: fmt.number(fmt.distance(km), 1) });
  }

  private sourceSelect(key: SourceKey): TemplateResult {
    const { t } = this.ctx;
    const spot = this.spot;
    const options = this.found?.[key] ?? [];
    const chosen = this.chosen[key] ?? "";
    const known = new Set(options.map((option) => option.id));
    return html`<label class="fld">
      <span class="lbl">${t(`spot.${key}`)}</span>
      <select
        name=${key}
        @change=${(event: Event) => {
          this.touched = { ...this.touched, [key]: true };
          this.chosen = { ...this.chosen, [key]: (event.target as HTMLSelectElement).value };
        }}
      >
        <option value="" ?selected=${!chosen}>${t("spot.none")}</option>
        ${
          chosen && !known.has(chosen)
            ? html`<option value=${chosen} selected>
                ${spot?.source_names[key] ? `${spot.source_names[key]} (${chosen})` : chosen}
              </option>`
            : nothing
        }
        ${options.map(
          (option, index) =>
            html`<option value=${option.id} ?selected=${option.id === chosen}>
              ${option.name} (${option.id.split("_")[0]}) ·
              ${this.distance(option.distance)}${index === 0 ? `, ${t("spot.nearest")}` : ""}
            </option>`,
        )}
      </select>
    </label>`;
  }

  protected body(): TemplateResult {
    const { ctx } = this;
    const { t, fmt } = ctx;
    const spot = this.spot;
    const radius = fmt.miles ? this.radius / 1000 / KM_PER_MILE : this.radius / 1000;
    const [low, high] = fmt.miles ? [1, 31] : [2, 50];
    return html`
      <div class="fld">
        <span class="lbl" id="pin-label">${t("spot.pin")}</span>
        <sc-spot-map
          .hass=${ctx.hass}
          .latitude=${this.latitude}
          .longitude=${this.longitude}
          .radius=${this.radius}
          .stations=${this.stations()}
          label=${t("spot.map_label")}
          @pin=${this.pinMoved}
        ></sc-spot-map>
        <span class="hint"
          >${t("spot.pin_hint", {
            position: `${fmt.number(Math.abs(this.latitude), 4)}° ${this.latitude >= 0 ? "N" : "S"}, ${fmt.number(Math.abs(this.longitude), 4)}° ${this.longitude >= 0 ? "E" : "W"}`,
          })}</span
        >
      </div>
      <label class="fld">
        <span class="lbl"
          >${t(fmt.miles ? "spot.radius_miles" : "spot.radius_km", {
            value: fmt.number(radius),
          })}</span
        >
        <input
          type="range"
          min=${low}
          max=${high}
          step="1"
          .value=${String(Math.round(radius))}
          @input=${(event: Event) => {
            const value = Number((event.target as HTMLInputElement).value);
            this.radius = Math.round((fmt.miles ? value * KM_PER_MILE : value) * 1000);
          }}
        />
        ${this.err("radius")}
      </label>
      <label class="fld">
        <span class="lbl">${t("profile.name")}</span>
        <input
          type="text"
          name="name"
          maxlength="40"
          autocomplete="off"
          .value=${spot?.name ?? ""}
        />
        ${this.err("name")}
      </label>
      <label class="fld">
        <span class="lbl">${t("spot.water")}</span>
        <select name="water_type">
          ${WATER.map(
            (water) =>
              html`<option value=${water} ?selected=${(spot?.water_type ?? "bay") === water}>
                ${t(`water_type.${water}`)}
              </option>`,
          )}
        </select>
      </label>
      ${(["offshore", "exposed"] as const).map(
        (key) =>
          html`<fieldset class="fld">
            <legend class="lbl">${t(`spot.${key}`)}</legend>
            <div class="daypick">
              ${DIRECTIONS.map(
                (direction) =>
                  html`<label class="dayt"
                    ><input
                      type="checkbox"
                      name=${key}
                      value=${direction}
                      ?checked=${spot?.[key].includes(direction) ?? false}
                    /><span>${t(`compass.${direction}`)}</span></label
                  >`,
              )}
            </div>
            <span class="hint">${t(`spot.${key}_hint`)}</span>
          </fieldset>`,
      )}
      ${SOURCES.map((key) => this.sourceSelect(key))}
      <p class="hint">${this.found?.failed ? t("spot.sources_failed") : t("spot.sources_hint")}</p>
    `;
  }

  protected footer(): TemplateResult {
    const spot = this.spot;
    return html`${
      spot ? this.deleteButton(spot.name, () => this.delete_("spot", spot.name)) : nothing
    }${this.actions(this.t(spot ? "dialog.save" : "spot.add_submit"))}`;
  }

  protected async submit(form: HTMLFormElement): Promise<string | void> {
    const name = value(form, "name");
    if (!name.trim()) return this.t("error.name_required");
    const spot = this.spot;
    const names: Partial<Record<SourceKey, string>> = {};
    const sources: Partial<Record<SourceKey, string | null>> = {};
    for (const key of SOURCES) {
      const id = value(form, key) || null;
      sources[key] = id;
      const found = this.found?.[key].find((option) => option.id === id);
      const name = found?.name ?? (id && id === spot?.[key] ? spot?.source_names[key] : undefined);
      if (id && name) names[key] = name;
    }
    return this.save("spot", name, {
      latitude: this.latitude,
      longitude: this.longitude,
      radius: this.radius,
      water_type: value(form, "water_type"),
      offshore: checked(form, "offshore"),
      exposed: checked(form, "exposed"),
      ...sources,
      source_names: names,
    });
  }
}

define("sc-sailor-dialog", ScSailorDialog);
define("sc-boat-dialog", ScBoatDialog);
define("sc-spot-dialog", ScSpotDialog);

declare global {
  interface HTMLElementTagNameMap {
    "sc-sailor-dialog": ScSailorDialog;
    "sc-boat-dialog": ScBoatDialog;
    "sc-spot-dialog": ScSpotDialog;
  }
}
