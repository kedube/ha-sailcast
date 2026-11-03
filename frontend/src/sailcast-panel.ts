import { html, LitElement, nothing, render, type PropertyValues, type TemplateResult } from "lit";

import { Api } from "./api";
import { brandIcon } from "./brand";
import "./calendar-dialogs";
import type { Actions, Ctx } from "./context";
import { dayView } from "./day";
import { errorText } from "./dialog";
import { Formatter, ms } from "./format";
import { icon } from "./glyphs";
import { localize } from "./localize";
import "./profile-dialogs";
import { settingsView } from "./settings";
import { styles } from "./styles";
import { PALETTES, THEME_VARIABLES, type Mode } from "./theme";
import type {
  Forecast,
  HomeAssistant,
  PlannedList,
  PlannedSail,
  Preferences,
  SailCastConfig,
  Theme,
  View,
  WindGrid,
} from "./types";
import { weekView } from "./week";
import "./wind-map";

const VIEWS: View[] = ["week", "day", "map", "settings"];
const TAB_ICONS = { week: "calMonth", day: "clock", map: "windy", settings: "cog" } as const;
const THEMES: Theme[] = ["auto", "day", "night"];
// Updates can come in bursts, such as a reload after a settings change.
const REFRESH_DELAY = 400;
const TOAST_TIME = 3200;

interface Route {
  prefix: string;
  path: string;
}

/**
 * The SailCast sidebar panel. Home Assistant creates it and sets `hass`,
 * `narrow`, `route` and `panel`.
 */
export class SailCastPanel extends LitElement {
  static override styles = styles;
  static override properties = {
    hass: { attribute: false },
    narrow: { type: Boolean, reflect: true },
    route: { attribute: false },
    panel: { attribute: false },
    config: { state: true },
    forecast: { state: true },
    planned: { state: true },
    preferences: { state: true },
    spotId: { state: true },
    sailorId: { state: true },
    boatId: { state: true },
    view: { state: true },
    day: { state: true },
    theme: { state: true },
    error: { state: true },
    forecastError: { state: true },
    dialog: { state: true },
    width: { state: true },
    grid: { state: true },
    gridError: { state: true },
  };

  declare hass?: HomeAssistant;
  declare narrow: boolean;
  declare route?: Route;
  declare panel?: unknown;
  declare config?: SailCastConfig;
  declare forecast?: Forecast;
  declare planned?: PlannedList;
  declare preferences?: Preferences;
  declare spotId?: string;
  declare sailorId?: string;
  declare boatId?: string;
  /** The view when Home Assistant doesn't pass a route, as in the demo. */
  declare view: View;
  declare day?: number;
  declare theme: Theme;
  declare error?: string;
  declare forecastError?: string;
  declare dialog?: TemplateResult;
  declare width: number;
  /** The wind map's grid, and the spot it was asked for. */
  declare grid?: WindGrid;
  declare gridError?: string;
  private gridSpot?: string;

  private api?: Api;
  private unsubscribe?: Promise<() => Promise<void>>;
  private refreshTimer?: number;
  private toastTimer?: number;
  private resizer?: ResizeObserver;
  private started = false;
  private applied = "";
  /** The request whose forecast is wanted, so a late reply for another is ignored. */
  private wanted = "";

  constructor() {
    super();
    this.narrow = false;
    this.view = "week";
    this.theme = "auto";
    this.width = 0;
  }

  override connectedCallback(): void {
    super.connectedCallback();
    if (this.hass && !this.started) void this.start();
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    this.started = false;
    void this.unsubscribe?.then((unsubscribe) => unsubscribe()).catch(() => undefined);
    this.unsubscribe = undefined;
    window.clearTimeout(this.refreshTimer);
    this.resizer?.disconnect();
    this.resizer = undefined;
  }

  protected override willUpdate(changed: PropertyValues<this>): void {
    if (changed.has("hass") && this.hass && !this.started && this.isConnected) {
      void this.start();
    }
    this.applyPalette();
  }

  protected override updated(): void {
    if (this.currentView() === "map" && this.spotId && this.gridSpot !== this.spotId) {
      void this.loadGrid(this.spotId);
    }
    const content = this.renderRoot.querySelector(".content");
    if (content && !this.resizer) {
      this.resizer = new ResizeObserver(([entry]) => {
        const width = Math.round(entry.contentRect.width);
        if (Math.abs(width - this.width) > 4) this.width = width;
      });
      this.resizer.observe(content);
    }
  }

  /** Load everything and follow changes. */
  private async start(): Promise<void> {
    const hass = this.hass!;
    this.started = true;
    this.api = new Api(hass.connection);
    this.unsubscribe = this.api.subscribe(() => this.scheduleRefresh());
    try {
      const [config, preferences] = await Promise.all([this.api.config(), this.api.preferences()]);
      this.preferences = preferences;
      if (THEMES.includes(preferences.theme as Theme)) this.theme = preferences.theme as Theme;
      if (!this.route && VIEWS.includes(preferences.view as View)) {
        this.view = preferences.view as View;
      }
      this.applyConfig(config);
      this.error = undefined;
    } catch (err) {
      this.error = errorText(err);
      return;
    }
    await Promise.all([this.loadForecast(), this.loadPlanned()]);
  }

  private scheduleRefresh(): void {
    window.clearTimeout(this.refreshTimer);
    this.refreshTimer = window.setTimeout(() => void this.refresh(), REFRESH_DELAY);
  }

  /** Read everything again after SailCast tells the panel something changed. */
  private async refresh(): Promise<void> {
    if (!this.api) return;
    try {
      this.applyConfig(await this.api.config());
      this.error = undefined;
    } catch (err) {
      this.error = errorText(err);
      return;
    }
    await Promise.all([this.loadForecast(), this.loadPlanned()]);
  }

  /** Use new settings, keeping the selection where it still exists. */
  private applyConfig(config: SailCastConfig): void {
    this.config = config;
    const preferences = this.preferences ?? {};
    const pick = <T extends { id: string }>(items: T[], ...ids: (string | undefined)[]) =>
      ids.map((id) => items.find((item) => item.id === id)).find(Boolean) ?? items[0];
    const spot = pick(config.spots, this.spotId, preferences.spot);
    const sailor = pick(config.sailors, this.sailorId, preferences.sailor);
    this.spotId = spot?.id;
    this.sailorId = sailor?.id;
    const boats = sailor?.boats ?? [];
    this.boatId =
      [this.boatId, preferences.boat].find((id) => id && boats.includes(id)) ?? boats[0];
  }

  private async loadForecast(): Promise<void> {
    const { api, spotId, sailorId, boatId } = this;
    if (!api || !spotId || !sailorId) {
      this.forecast = undefined;
      return;
    }
    const wanted = `${spotId}|${sailorId}|${boatId}`;
    this.wanted = wanted;
    try {
      const forecast = await api.forecast(spotId, sailorId, boatId);
      if (this.wanted !== wanted) return;
      const first = this.forecast === undefined || this.forecast.spot !== forecast.spot;
      this.forecast = forecast;
      this.forecastError = undefined;
      if (first && this.day === undefined) this.day = this.firstDay(forecast);
    } catch (err) {
      if (this.wanted !== wanted) return;
      this.forecast = undefined;
      this.forecastError = errorText(err);
    }
  }

  /**
   * The day the day view opens on: the first with a window still to come,
   * or else the first that isn't over.
   */
  private firstDay(forecast: Forecast): number {
    const withWindow = forecast.days.findIndex((day) => day.windows.length);
    if (withWindow >= 0) return withWindow;
    return Math.max(
      0,
      forecast.days.findIndex((day) => !day.over),
    );
  }

  /** Ask for the wind map's grid; SailCast keeps it three hours. */
  private async loadGrid(spot: string): Promise<void> {
    if (!this.api) return;
    this.gridSpot = spot;
    this.gridError = undefined;
    if (this.grid && !this.grid.spots.includes(spot)) this.grid = undefined;
    try {
      const grid = await this.api.windGrid(spot);
      if (this.gridSpot === spot) this.grid = grid;
    } catch (err) {
      if (this.gridSpot !== spot) return;
      const code = typeof err === "object" && err && "code" in err ? String(err.code) : "";
      this.grid = undefined;
      this.gridError =
        code === "budget"
          ? this.t("map.budget")
          : this.t("map.unavailable", { message: errorText(err) });
    }
  }

  private async loadPlanned(): Promise<void> {
    try {
      this.planned = await this.api?.planned();
    } catch {
      this.planned = undefined;
    }
  }

  private savePreferences(changes: Partial<Record<keyof Preferences, string | null>>): void {
    this.preferences = { ...this.preferences, ...changes } as Preferences;
    void this.api?.setPreferences(changes).catch(() => undefined);
  }

  /** The panel's palette: Home Assistant's mode in Auto, or the chosen one. */
  private mode(): Mode {
    if (this.theme === "auto") return this.hass?.themes?.darkMode ? "night" : "day";
    return this.theme;
  }

  private applyPalette(): void {
    const mode = this.mode();
    const follow = this.theme === "auto";
    const key = `${mode}:${follow}`;
    if (key === this.applied) return;
    this.applied = key;
    for (const [name, value] of Object.entries(PALETTES[mode])) {
      const variable = follow ? THEME_VARIABLES[name] : undefined;
      this.style.setProperty(`--sc-${name}`, variable ? `var(--${variable}, ${value})` : value);
    }
    this.style.colorScheme = mode === "night" ? "dark" : "light";
  }

  private currentView(): View {
    const path = this.route?.path.split("/")[1];
    if (this.route) return VIEWS.includes(path as View) ? (path as View) : this.view;
    return this.view;
  }

  private go(view: View, event?: MouseEvent): void {
    if (event && (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey)) return;
    event?.preventDefault();
    this.view = view;
    this.savePreferences({ view });
    if (this.route) {
      history.pushState(null, "", `${this.route.prefix}/${view}`);
      window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
    }
    window.scrollTo?.({ top: 0 });
  }

  private t = (key: string, values?: Record<string, string | number>): string =>
    localize(this.hass?.locale?.language ?? this.hass?.language, key, values);

  private get tip(): HTMLElement | null {
    return this.renderRoot.querySelector(".tip");
  }

  private placeTip(x: number, top: number, bottom: number): void {
    const tip = this.tip;
    if (!tip) return;
    const box = tip.getBoundingClientRect();
    let y = top - box.height - 8;
    if (y < 8) y = bottom + 8;
    tip.style.left = `${Math.min(Math.max(x - box.width / 2, 8), window.innerWidth - box.width - 8)}px`;
    tip.style.top = `${y}px`;
  }

  private showTipContent(content: TemplateResult | string): HTMLElement | null {
    const tip = this.tip;
    if (!tip) return null;
    render(content, tip);
    if (typeof tip.showPopover === "function") {
      if (!tip.matches(":popover-open")) tip.showPopover();
    } else {
      tip.hidden = false;
    }
    return tip;
  }

  private hideTip(): void {
    const tip = this.tip;
    if (!tip) return;
    if (typeof tip.hidePopover === "function") {
      if (tip.matches(":popover-open")) tip.hidePopover();
    } else {
      tip.hidden = true;
    }
  }

  private toast(message: string): void {
    const toast = this.renderRoot.querySelector<HTMLElement>(".toast");
    if (!toast) return;
    render(html`${icon("check")}<span>${message}</span>`, toast);
    if (typeof toast.showPopover === "function") {
      if (!toast.matches(":popover-open")) toast.showPopover();
    } else {
      toast.hidden = false;
    }
    window.clearTimeout(this.toastTimer);
    this.toastTimer = window.setTimeout(() => {
      if (typeof toast.hidePopover === "function") {
        if (toast.matches(":popover-open")) toast.hidePopover();
      } else {
        toast.hidden = true;
      }
    }, TOAST_TIME);
  }

  private openDialog(dialog: TemplateResult): void {
    this.hideTip();
    this.dialog = dialog;
  }

  private closeDialog = (): void => {
    this.dialog = undefined;
  };

  private actions: Actions = {
    openDay: (index) => {
      this.day = index;
      if (this.currentView() !== "day") this.go("day");
    },
    openWindow: (day, number) => {
      const window = this.forecast?.days[day]?.windows[number];
      if (!window) return;
      const ctx = this.ctx()!;
      const sail = this.forecast?.planned.find(
        (item) =>
          item.boat === this.boatId &&
          item.spot === this.spotId &&
          ms(item.start) < ms(window.end) &&
          ms(item.end) > ms(window.start),
      );
      if (sail) {
        this.actions.openPlanned(sail);
        return;
      }
      this.openDialog(
        html`<sc-window-dialog
          .ctx=${ctx}
          .dayIndex=${day}
          .windowIndex=${number}
          @closed=${this.closeDialog}
        ></sc-window-dialog>`,
      );
    },
    openPlanned: (sail: PlannedSail) =>
      this.openDialog(
        html`<sc-planned-dialog
          .ctx=${this.ctx()}
          .sail=${sail}
          @closed=${this.closeDialog}
        ></sc-planned-dialog>`,
      ),
    removePlanned: async (sail: PlannedSail) => {
      try {
        const result = await this.api!.removeFromCalendar(sail.id);
        const calendar = this.config?.calendars.find((item) => item.entity_id === sail.calendar);
        this.toast(
          result.deleted
            ? this.t("planned.removed", {
                calendar: calendar ? `${calendar.name} (${calendar.via})` : sail.calendar,
              })
            : this.t("planned.stopped"),
        );
      } catch (err) {
        this.toast(errorText(err));
      }
    },
    openAuto: (sailor) => {
      if (!this.hass?.user?.is_admin) return;
      this.openDialog(
        html`<sc-auto-dialog
          .ctx=${this.ctx()}
          .sailorId=${sailor}
          @closed=${this.closeDialog}
        ></sc-auto-dialog>`,
      );
    },
    editSpot: (id) =>
      this.openDialog(
        html`<sc-spot-dialog
          .ctx=${this.ctx()}
          .profileId=${id}
          @closed=${this.closeDialog}
        ></sc-spot-dialog>`,
      ),
    editSailor: (id) =>
      this.openDialog(
        html`<sc-sailor-dialog
          .ctx=${this.ctx()}
          .profileId=${id}
          @closed=${this.closeDialog}
        ></sc-sailor-dialog>`,
      ),
    editBoat: (id) =>
      this.openDialog(
        html`<sc-boat-dialog
          .ctx=${this.ctx()}
          .profileId=${id}
          @closed=${this.closeDialog}
        ></sc-boat-dialog>`,
      ),
    setCalendar: (entityId) => {
      if (entityId === this.preferences?.calendar) return;
      this.savePreferences({ calendar: entityId });
      const calendar = this.config?.calendars.find((item) => item.entity_id === entityId);
      if (calendar)
        this.toast(
          this.t("settings.calendar_set", { calendar: `${calendar.name} (${calendar.via})` }),
        );
    },
    showTip: (target, content) => {
      const tip = this.showTipContent(content);
      if (!tip) return;
      const box = target.getBoundingClientRect();
      this.placeTip(box.left + box.width / 2, box.top, box.bottom);
    },
    showTipAt: (x, y, content) => {
      if (this.showTipContent(content)) this.placeTip(x, y, y + 24);
    },
    hideTip: () => this.hideTip(),
    toast: (message) => this.toast(message),
  };

  private ctx(): Ctx | undefined {
    const hass = this.hass;
    const config = this.config;
    if (!hass || !config || !this.api) return undefined;
    return {
      hass,
      api: this.api,
      fmt: new Formatter(hass),
      t: this.t,
      config,
      forecast: this.forecast,
      planned: this.planned,
      spot: config.spots.find((spot) => spot.id === this.spotId),
      sailor: config.sailors.find((sailor) => sailor.id === this.sailorId),
      boat: config.boats.find((boat) => boat.id === this.boatId),
      day: this.day ?? 0,
      admin: Boolean(hass.user?.is_admin),
      calendar: this.preferences?.calendar,
      act: this.actions,
    };
  }

  protected override render(): TemplateResult {
    const ctx = this.ctx();
    const view = this.currentView();
    return html`
      <div class="page">
        <header class="toolbar">
          <div class="title">
            <ha-menu-button .hass=${this.hass} .narrow=${this.narrow}></ha-menu-button>
            <span class="logo">${brandIcon}</span>
            <h1>SailCast</h1>
          </div>
          ${ctx ? this.pickers(ctx) : nothing} ${this.modeSwitch()}
        </header>
        <nav class="tabs" role="tablist" aria-label=${this.t("tabs.label")}>
          ${VIEWS.map(
            (item) =>
              html`<a
                href=${this.route ? `${this.route.prefix}/${item}` : `#${item}`}
                role="tab"
                aria-selected=${item === view ? "true" : "false"}
                @click=${(event: MouseEvent) => this.go(item, event)}
                >${icon(TAB_ICONS[item])}${this.t(`tabs.${item}`)}</a
              >`,
          )}
        </nav>
        <main class="content">
          <section class="view" role="tabpanel">${this.content(ctx, view)}</section>
          <p class="advisory">${this.t("advisory")}</p>
        </main>
      </div>
      ${this.dialog ?? nothing}
      <div class="tip" popover="manual" role="tooltip"></div>
      <div class="toast" popover="manual" role="status" aria-live="polite"></div>
    `;
  }

  private pickers(ctx: Ctx): TemplateResult {
    const config = ctx.config;
    const sailor = ctx.sailor;
    const admin = ctx.admin;
    const pencil = (label: string, edit: () => void) =>
      admin
        ? html`<button type="button" class="icon-btn" aria-label=${label} @click=${edit}>
            ${icon("pencil")}
          </button>`
        : nothing;
    if (!config.spots.length || !config.sailors.length) return html``;
    return html`<div class="pickers">
      <div class="pick">
        <label class="field"
          >${this.t("pickers.spot")}
          <select
            @change=${(event: Event) => {
              this.spotId = (event.target as HTMLSelectElement).value;
              this.savePreferences({ spot: this.spotId });
              void this.loadForecast();
            }}
          >
            ${config.spots.map(
              (spot) =>
                html`<option value=${spot.id} ?selected=${spot.id === this.spotId}>
                  ${spot.name}
                </option>`,
            )}
          </select></label
        >
        ${pencil(this.t("pickers.edit_spot"), () => this.actions.editSpot(this.spotId))}
      </div>
      <div class="pick">
        <label class="field"
          >${this.t("pickers.sailor")}
          <select
            @change=${(event: Event) => {
              this.sailorId = (event.target as HTMLSelectElement).value;
              this.boatId = config.sailors.find((item) => item.id === this.sailorId)?.boats[0];
              this.savePreferences({ sailor: this.sailorId, boat: this.boatId ?? null });
              void this.loadForecast();
            }}
          >
            ${config.sailors.map(
              (item) =>
                html`<option value=${item.id} ?selected=${item.id === this.sailorId}>
                  ${item.name} · ${this.t(`skill.${item.skill}`)}
                </option>`,
            )}
          </select></label
        >
        ${pencil(this.t("pickers.edit_sailor"), () => this.actions.editSailor(this.sailorId))}
      </div>
      ${
        sailor
          ? html`<div class="pick">
              <label class="field"
                >${this.t("pickers.boat")}
                <select
                  @change=${(event: Event) => {
                    this.boatId = (event.target as HTMLSelectElement).value;
                    this.savePreferences({ boat: this.boatId });
                    void this.loadForecast();
                  }}
                >
                  ${sailor.boats.map((id) => {
                    const boat = config.boats.find((item) => item.id === id);
                    return html`<option value=${id} ?selected=${id === this.boatId}>
                      ${boat?.name ?? id}
                    </option>`;
                  })}
                </select></label
              >
              ${pencil(this.t("pickers.edit_boat"), () => this.actions.editBoat(this.boatId))}
            </div>`
          : nothing
      }
    </div>`;
  }

  private modeSwitch(): TemplateResult {
    const names = { auto: "themeAuto", day: "sun", night: "night" } as const;
    return html`<div class="mode" role="group" aria-label=${this.t("theme.label")}>
      ${THEMES.map(
        (theme) =>
          html`<button
            type="button"
            aria-pressed=${this.theme === theme ? "true" : "false"}
            aria-label=${this.t(`theme.${theme}_label`)}
            title=${this.t(`theme.${theme}_label`)}
            @click=${() => {
              this.theme = theme;
              this.savePreferences({ theme });
            }}
          >
            ${icon(names[theme])}<b>${this.t(`theme.${theme}`)}</b>
          </button>`,
      )}
    </div>`;
  }

  private content(ctx: Ctx | undefined, view: View): TemplateResult {
    if (this.error) {
      return html`<div class="notice error" role="alert">
        ${icon("alert")}
        <p>${this.t("error.load", { message: this.error })}</p>
      </div>`;
    }
    if (!ctx) return html`<p class="muted">${this.t("loading")}</p>`;
    const config = ctx.config;
    if (view === "settings") return settingsView(ctx);
    if (!config.spots.length || !config.boats.length || !config.sailors.length) {
      return html`<section class="card empty-state">
        <h2>${this.t("start.title")}</h2>
        <p>${this.t(ctx.admin ? "start.admin" : "start.other")}</p>
        ${
          ctx.admin
            ? html`<button
                type="button"
                class="btn btn-primary"
                @click=${() => this.go("settings")}
              >
                ${icon("cog")}${this.t("start.open_settings")}
              </button>`
            : nothing
        }
      </section>`;
    }
    if (!ctx.forecast) {
      return this.forecastError
        ? html`<section class="card empty-state">
            <h2>${this.t("forecast.none_title", { spot: ctx.spot?.name ?? "" })}</h2>
            <p>${this.t("forecast.none")}</p>
          </section>`
        : html`<p class="muted">${this.t("loading")}</p>`;
    }
    if (view === "map") return this.mapView(ctx);
    return view === "day" ? dayView(ctx, Math.max(0, this.width - 34)) : weekView(ctx);
  }

  private mapView(ctx: Ctx): TemplateResult {
    if (this.gridError) {
      return html`<div class="notice" role="status">
        ${icon("info")}
        <p>${this.gridError}</p>
      </div>`;
    }
    if (!this.grid || !this.spotId || !this.grid.spots.includes(this.spotId)) {
      return html`<p class="muted">${this.t("map.loading")}</p>`;
    }
    return html`<sc-wind-map
      .hass=${ctx.hass}
      .grid=${this.grid}
      .spots=${ctx.config.spots}
      .spotId=${this.spotId}
      .t=${this.t}
      .fmt=${ctx.fmt}
    ></sc-wind-map>`;
  }
}

// A new build can load while the old one is still defined.
if (!customElements.get("sailcast-panel")) {
  customElements.define("sailcast-panel", SailCastPanel);
}

declare global {
  interface HTMLElementTagNameMap {
    "sailcast-panel": SailCastPanel;
  }
}
