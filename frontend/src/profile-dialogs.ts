/**
 * Adding and editing sailors, boats and spots. Changes go through the same
 * checks as Home Assistant's setup dialogs and land in the same place, so
 * Settings → Devices & services always shows the same thing.
 */
import { html, nothing, type TemplateResult } from "lit";

import { checked, define, hourSelect, hourTime, numberOrNull, ScDialog, value } from "./dialog";
import { compassKey, FEET_PER_METER, KM_PER_MILE, WEEKDAYS } from "./format";
import { limitBars, skillBars } from "./settings";
import "./spot-map";
import type { StationMark } from "./spot-map";
import { positionText, savedSourceText } from "./text";
import type {
  Comfort,
  DayHours,
  SensorKey,
  Shoreline,
  SizeClass,
  Skill,
  SourceKey,
  SourceSuggestions,
  Spot,
  WaterType,
} from "./types";
import { SIZES } from "./week";

const SKILLS: Skill[] = ["beginner", "intermediate", "advanced"];
const WATER = ["open_coast", "bay", "river", "lake"];
const DIRECTIONS = ["n", "ne", "e", "se", "s", "sw", "w", "nw"];
const SOURCES: SourceKey[] = ["tide_station", "current_station", "marine_zone", "buoy", "airport"];
// Sources whose position is kept, for the forecast where they are.
const PLACED = ["buoy", "airport"] as const;
// Your own sensors, by the device class each reading needs.
const SENSORS: [SensorKey, string][] = [
  ["wind", "wind_speed"],
  ["gust", "wind_speed"],
  ["wind_direction", "wind_direction"],
  ["temperature", "temperature"],
  ["water_temperature", "temperature"],
];

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
  static override properties = {
    ...ProfileDialog.properties,
    boats: { state: true },
    days: { state: true },
  };
  /** The boats ticked so far, for the usual-boat choice. */
  declare boats?: string[];
  /** The days ticked so far, whose hours can be chosen. */
  declare days?: string[];

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
    // A new sailor sails every day, sunrise to sunset.
    const week: Partial<Record<string, DayHours>> =
      sailor?.week ?? Object.fromEntries(WEEKDAYS.map((day) => [day, { start: null, end: null }]));
    const days = this.days ?? WEEKDAYS.filter((day) => week[day]);
    const comfort: Comfort = sailor?.comfort ?? {
      ideal_low: null,
      ideal_high: null,
      coldest: null,
      rain: "some",
    };
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
        <div class="dayhours">
          <span></span>
          <span class="lbl">${t("sailor.from")}</span>
          <span class="lbl">${t("sailor.until")}</span>
          ${WEEKDAYS.map((day, index) => {
            const sails = days.includes(day);
            const name = fmt.weekday(`2026-11-0${2 + index}`, "long");
            return html`<label class="dayt"
                ><input
                  type="checkbox"
                  name="days"
                  value=${day}
                  ?checked=${sails}
                  @change=${(event: Event) => {
                    const on = (event.target as HTMLInputElement).checked;
                    this.days = WEEKDAYS.filter((item) =>
                      item === day ? on : days.includes(item),
                    );
                  }}
                /><span>${t(`weekday.${day}`)}</span></label
              >
              ${hourSelect(ctx, `start_${day}`, false, week[day]?.start, {
                label: t("sailor.from_day", { day: name }),
                disabled: !sails,
              })}
              ${hourSelect(ctx, `end_${day}`, true, week[day]?.end, {
                label: t("sailor.until_day", { day: name }),
                disabled: !sails,
              })}
              ${this.err(`${day}_end`)}`;
          })}
        </div>
        ${this.err("days")}
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
    const coldest = numberOrNull(form, "coldest");
    // The days ticked, each with its own hours.
    const hours = Object.fromEntries(
      checked(form, "days").map((day) => [
        day,
        {
          start: hourTime(value(form, `start_${day}`)),
          end: hourTime(value(form, `end_${day}`)),
        },
      ]),
    );
    return this.save("sailor", name, {
      skill: value(form, "skill"),
      boats: boats.includes(first) ? [first, ...boats.filter((boat) => boat !== first)] : boats,
      hours,
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
        <label class="check">
          <input type="checkbox" name="lights" ?checked=${boat?.lights ?? false} />
          <span>${t("boat.lights")}</span>
        </label>
        <p class="hint">${t("boat.lights_hint")}</p>
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
      lights: checked(form, "lights").length > 0,
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
    water: { state: true },
    exposed: { state: true },
    shore: { state: true },
  };
  declare latitude: number;
  declare longitude: number;
  /** Meters. */
  declare radius: number;
  declare found?: SourceSuggestions;
  /** Sources picked so far: an ID, or "" for none. */
  declare chosen: Partial<Record<SourceKey, string>>;
  declare water: WaterType;
  declare exposed: string[];
  /** The pin's shoreline: measured, being measured (null), or not to be had. */
  declare shore?: Shoreline | null | "failed";
  private lookup?: number;
  /** Whether someone picked the exposure by hand, which a moved pin leaves alone. */
  private exposedTouched = false;

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
    this.water = spot?.water_type ?? "bay";
    this.exposed = [...(spot?.exposed ?? [])];
    this.exposedTouched = Boolean(spot?.exposed.length);
    void this.suggest();
    void this.measure();
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
        buoy: [],
        airport: [],
        suggested: {
          tide_station: null,
          current_station: null,
          marine_zone: null,
          buoy: null,
          airport: null,
        },
        failed: true,
      };
    }
  }

  /**
   * Measure how far the water reaches from the pin. For a new spot, or one
   * without exposure set, the directions open to the sea are checked.
   */
  private async measure(): Promise<void> {
    const at = [this.latitude, this.longitude];
    this.shore = null;
    let shore: Shoreline | "failed";
    try {
      shore = await this.ctx.api.shoreline(this.latitude, this.longitude);
    } catch {
      shore = "failed";
    }
    if (at[0] !== this.latitude || at[1] !== this.longitude) return;
    this.shore = shore;
    if (shore !== "failed" && shore.on_water && !this.exposedTouched) {
      this.exposed = [...shore.exposed];
    }
  }

  /** The sources someone picked by hand, which a moved pin leaves alone. */
  private touched: Partial<Record<SourceKey, true>> = {};

  private pinMoved(event: CustomEvent<{ latitude: number; longitude: number }>): void {
    this.latitude = Math.round(event.detail.latitude * 100_000) / 100_000;
    this.longitude = Math.round(event.detail.longitude * 100_000) / 100_000;
    window.clearTimeout(this.lookup);
    this.lookup = window.setTimeout(() => {
      void this.suggest();
      void this.measure();
    }, 700);
  }

  protected heading(): string {
    const spot = this.spot;
    return spot ? this.t("spot.edit", { name: spot.name }) : this.t("spot.add");
  }

  /** The suggested stations, buoys and airports, to show on the map. */
  private stations(): StationMark[] {
    const found = this.found;
    if (!found) return [];
    const marks: StationMark[] = [];
    for (const [key, kind] of [
      ["tide_station", "tide"],
      ["current_station", "current"],
      ["buoy", "buoy"],
      ["airport", "airport"],
    ] as const) {
      for (const choice of found[key]) {
        if (choice.latitude === null || choice.longitude === null) continue;
        marks.push({
          kind,
          id: choice.id,
          label: this.t(`spot.${kind}_mark`, {
            name: choice.name,
            id: (choice.code ?? choice.id).split("_")[0],
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
                ${savedSourceText(chosen, spot?.source_names[key])}
              </option>`
            : nothing
        }
        ${options.map(
          (option, index) =>
            html`<option value=${option.id} ?selected=${option.id === chosen}>
              ${option.name}${option.code ? ` (${option.code.split("_")[0]})` : ""}${
                option.distance !== null
                  ? ` · ${this.distance(option.distance)}${index === 0 ? `, ${t("spot.nearest")}` : ""}`
                  : ""
              }
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
            position: positionText(fmt, t, this.latitude, this.longitude, 4),
          })}</span
        >
        ${this.shoreText()}
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
        <select
          name="water_type"
          @change=${(event: Event) => {
            this.water = (event.target as HTMLSelectElement).value as WaterType;
          }}
        >
          ${WATER.map(
            (water) =>
              html`<option value=${water} ?selected=${this.water === water}>
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
                      .checked=${
                        key === "exposed"
                          ? this.exposed.includes(direction)
                          : (spot?.offshore.includes(direction) ?? false)
                      }
                      @change=${key === "exposed" ? this.exposedChanged : nothing}
                    /><span>${t(`compass.${direction}`)}</span></label
                  >`,
              )}
            </div>
            <span class="hint">${t(`spot.${key}_hint`)}</span>
          </fieldset>`,
      )}
      ${this.water === "river" || this.water === "lake" ? this.fetchField() : nothing}
      ${SOURCES.map((key) => this.sourceSelect(key))}
      <p class="hint">${this.found?.failed ? t("spot.sources_failed") : t("spot.sources_hint")}</p>
      ${this.sensorFields()}
    `;
  }

  private exposedChanged(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.exposedTouched = true;
    this.exposed = input.checked
      ? DIRECTIONS.filter((item) => item === input.value || this.exposed.includes(item))
      : this.exposed.filter((item) => item !== input.value);
  }

  /** Whether the pin is on water, and how far the water reaches. */
  private shoreText(): TemplateResult | typeof nothing {
    const { t } = this.ctx;
    const shore = this.shore;
    if (shore === undefined || shore === "failed") return nothing;
    if (shore === null) return html`<span class="hint">${t("spot.shore_measuring")}</span>`;
    if (!shore.on_water) return html`<p class="form-err" role="alert">${t("spot.on_land")}</p>`;
    const longest = Math.max(...shore.rays);
    const toward = shore.rays.indexOf(longest) * 3;
    const open = shore.exposed
      .map((point) => t(`compass.${point}`))
      .join(t("advice.list_separator"));
    return html`<span class="hint"
      >${t(open ? "spot.shore_open" : "spot.shore_closed", {
        distance: this.distance(longest),
        direction: t(`compass.${compassKey(toward)}`),
        open,
      })}</span
    >`;
  }

  /** The open water upwind, set by hand, for a river or lake. */
  private fetchField(): TemplateResult {
    const { t, fmt } = this.ctx;
    const fetch = this.spot?.fetch;
    return html`<label class="fld">
      <span class="lbl">${t(fmt.miles ? "spot.fetch_miles" : "spot.fetch_km")}</span>
      <input
        type="number"
        name="fetch"
        min="0"
        step="0.1"
        inputmode="decimal"
        .value=${fetch ? String(Math.round(fmt.distance(fetch) * 10) / 10) : ""}
      />
      <span class="hint">${t("spot.fetch_hint")}</span>
      ${this.err("fetch")}
    </label>`;
  }

  /** Your own sensors: any sensor with the right kind of reading. */
  private sensorFields(): TemplateResult {
    const { t, hass } = this.ctx;
    const saved = this.spot?.sensors ?? {};
    const states = Object.values(hass.states ?? {});
    return html`<fieldset class="fld">
      <legend class="lbl">${t("spot.sensors")}</legend>
      ${SENSORS.map(([key, deviceClass]) => {
        const chosen = saved[key] ?? "";
        const options = states
          .filter(
            (state) =>
              state.entity_id.startsWith("sensor.") &&
              state.attributes.device_class === deviceClass,
          )
          .sort((a, b) => a.entity_id.localeCompare(b.entity_id));
        return html`<label class="fld">
          <span class="lbl">${t(`spot.sensor.${key}`)}</span>
          <select name=${`sensor_${key}`}>
            <option value="" ?selected=${!chosen}>${t("spot.none")}</option>
            ${
              chosen && !options.some((state) => state.entity_id === chosen)
                ? html`<option value=${chosen} selected>${chosen}</option>`
                : nothing
            }
            ${options.map(
              (state) =>
                html`<option value=${state.entity_id} ?selected=${state.entity_id === chosen}>
                  ${state.attributes.friendly_name ?? state.entity_id}
                </option>`,
            )}
          </select>
        </label>`;
      })}
      <span class="hint">${t("spot.sensors_hint")}</span>
      ${this.err("sensors")}
    </fieldset>`;
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
    const points: Partial<Record<(typeof PLACED)[number], [number, number]>> = {};
    for (const key of SOURCES) {
      const id = value(form, key) || null;
      sources[key] = id;
      const found = this.found?.[key].find((option) => option.id === id);
      const name = found?.name ?? (id && id === spot?.[key] ? spot?.source_names[key] : undefined);
      if (id && name) names[key] = name;
    }
    for (const key of PLACED) {
      const id = sources[key];
      const found = this.found?.[key].find((option) => option.id === id);
      const point =
        found?.latitude != null && found.longitude != null
          ? ([found.latitude, found.longitude] as [number, number])
          : id && id === spot?.[key]
            ? spot.source_points[key]
            : undefined;
      if (id && point) points[key] = point;
    }
    const sensors = Object.fromEntries(
      SENSORS.map(([key]) => [key, value(form, `sensor_${key}`)]).filter(([, id]) => id),
    );
    const fetch = numberOrNull(form, "fetch");
    return this.save("spot", name, {
      latitude: this.latitude,
      longitude: this.longitude,
      radius: this.radius,
      water_type: value(form, "water_type"),
      offshore: checked(form, "offshore"),
      exposed: this.exposed,
      ...sources,
      sensors,
      fetch:
        fetch && (this.water === "river" || this.water === "lake")
          ? Math.round((this.ctx.fmt.miles ? fetch * KM_PER_MILE : fetch) * 1000) / 1000
          : null,
      source_names: names,
      source_points: points,
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
