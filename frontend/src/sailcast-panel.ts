import {
  LitElement,
  css,
  html,
  nothing,
  unsafeCSS,
  type PropertyValues,
  type TemplateResult,
} from "lit";

import { bannerWaves, brandIcon } from "./brand";
import { localize } from "./localize";
import { paletteCss } from "./theme";
import type { Boat, HomeAssistant, SailCastConfig } from "./types";

const FEET_PER_METER = 3.28084;
const SETTINGS_PATH = "/config/integrations/integration/sailcast";

/**
 * The SailCast sidebar panel. Home Assistant creates it and sets `hass`,
 * `narrow` and `panel`.
 */
export class SailCastPanel extends LitElement {
  static override properties = {
    hass: { attribute: false },
    narrow: { type: Boolean, reflect: true },
    panel: { attribute: false },
    config: { state: true },
    error: { state: true },
  };

  declare hass?: HomeAssistant;
  declare narrow: boolean;
  declare panel?: unknown;
  declare config?: SailCastConfig;
  declare error?: string;
  private loading = false;

  constructor() {
    super();
    this.narrow = false;
  }

  override connectedCallback(): void {
    super.connectedCallback();
    // Profiles can change while the panel is closed, so read them again.
    this.config = undefined;
    this.error = undefined;
  }

  protected override willUpdate(changed: PropertyValues<this>): void {
    if (changed.has("hass")) {
      this.toggleAttribute("night", Boolean(this.hass?.themes?.darkMode));
    }
  }

  protected override updated(): void {
    if (this.hass && !this.config && !this.error && !this.loading) {
      void this.load(this.hass);
    }
  }

  private async load(hass: HomeAssistant): Promise<void> {
    this.loading = true;
    try {
      this.config = await hass.connection.sendMessagePromise<SailCastConfig>({
        type: "sailcast/config",
      });
    } catch (err) {
      this.error =
        typeof err === "object" && err && "message" in err ? String(err.message) : String(err);
    } finally {
      this.loading = false;
    }
  }

  private t(key: string, values?: Record<string, string | number>): string {
    return localize(this.hass?.language, key, values);
  }

  protected override render(): TemplateResult {
    return html`
      <div class="page">
        <header class="toolbar">
          <ha-menu-button .hass=${this.hass} .narrow=${this.narrow}></ha-menu-button>
          <span class="logo">${brandIcon}</span>
          <h1>SailCast</h1>
        </header>
        <main>
          <section class="banner">
            <h2>${this.t("hero.title")}</h2>
            <p>${this.t("hero.body")}</p>
            <svg class="waves" viewBox="0 0 1200 120" preserveAspectRatio="none" aria-hidden="true">
              ${bannerWaves}
            </svg>
          </section>
          ${this.renderProfiles()}
          <p class="advisory">${this.t("advisory")}</p>
        </main>
      </div>
    `;
  }

  private renderProfiles(): TemplateResult {
    if (this.error) {
      return html`<p class="card error" role="alert">
        ${this.t("error", { message: this.error })}
      </p>`;
    }
    const config = this.config;
    if (!config) {
      return html`<p class="loading">${this.t("loading")}</p>`;
    }
    const boats = new Map(config.boats.map((boat) => [boat.id, boat]));
    const empty = !config.spots.length && !config.boats.length && !config.sailors.length;
    return html`
      <section class="profiles">
        ${this.renderCard(
          "spots",
          config.spots.map((spot) => [spot.name, this.t(`water_type.${spot.water_type}`)]),
        )}
        ${this.renderCard(
          "boats",
          config.boats.map((boat) => [
            boat.name,
            `${this.t(`size_class.${boat.size_class}`)} · ${this.formatLength(boat)}`,
          ]),
        )}
        ${this.renderCard(
          "sailors",
          config.sailors.map((sailor) => [
            sailor.name,
            [this.t(`skill.${sailor.skill}`), boats.get(sailor.boats[0])?.name]
              .filter(Boolean)
              .join(" · "),
          ]),
        )}
      </section>
      <div class="actions">
        ${empty ? html`<p>${this.t("start")}</p>` : nothing}
        ${
          this.hass?.user?.is_admin
            ? html`<a class="button" href=${SETTINGS_PATH} @click=${this.openSettings}>
                ${this.t("manage")}
              </a>`
            : html`<p>${this.t("manage_admin_only")}</p>`
        }
      </div>
    `;
  }

  private renderCard(kind: string, items: [string, string][]): TemplateResult {
    return html`
      <article class="card">
        <header>
          <h3>${this.t(`profiles.${kind}`)}</h3>
          <span class="count">${items.length}</span>
        </header>
        ${
          items.length
            ? html`<ul>
                ${items.map(
                  ([name, detail]) =>
                    html`<li>
                      <span class="name">${name}</span>
                      <span class="detail">${detail}</span>
                    </li>`,
                )}
              </ul>`
            : html`<p class="none">${this.t("profiles.none")}</p>`
        }
      </article>
    `;
  }

  private formatLength(boat: Boat): string {
    const feet = this.hass?.config.unit_system.length === "mi";
    const value = new Intl.NumberFormat(this.hass?.language, {
      maximumFractionDigits: 1,
    }).format(feet ? boat.length * FEET_PER_METER : boat.length);
    return this.t(feet ? "length.feet" : "length.meters", { value });
  }

  /** Open the integration's page inside Home Assistant, without a reload. */
  private openSettings(event: MouseEvent): void {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) {
      return;
    }
    event.preventDefault();
    history.pushState(null, "", SETTINGS_PATH);
    window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
  }

  static override styles = css`
    :host {
      ${unsafeCSS(paletteCss("day"))}
      --sc-radius: 14px;
      /* The panel registers with handle_safe_area, so it keeps clear of
         notches itself. Home Assistant sets these variables; the sidebar
         already covers the left inset when it's shown. */
      --sc-inset-top: var(--safe-area-inset-top, env(safe-area-inset-top, 0px));
      --sc-inset-bottom: var(--safe-area-inset-bottom, env(safe-area-inset-bottom, 0px));
      --sc-inset-left: var(
        --safe-area-content-inset-left,
        var(--safe-area-inset-left, env(safe-area-inset-left, 0px))
      );
      --sc-inset-right: var(
        --safe-area-content-inset-right,
        var(--safe-area-inset-right, env(safe-area-inset-right, 0px))
      );
      display: block;
      font-family: var(--ha-font-family-body, Roboto, system-ui, sans-serif);
      -webkit-font-smoothing: antialiased;
    }
    :host([night]) {
      ${unsafeCSS(paletteCss("night"))}
    }
    .page {
      min-height: 100vh;
      min-height: 100dvh;
      background: var(--sc-page);
      color: var(--sc-fg);
    }
    .toolbar {
      position: sticky;
      top: 0;
      z-index: 1;
      display: flex;
      align-items: center;
      gap: 12px;
      height: 56px;
      padding: var(--sc-inset-top) max(16px, var(--sc-inset-right)) 0
        max(12px, var(--sc-inset-left));
      background: var(--sc-toolbar);
      border-bottom: 1px solid var(--sc-line);
      color: var(--sc-toolbar-ink);
    }
    ha-menu-button {
      color: var(--sc-toolbar-ink);
    }
    .logo svg {
      display: block;
      width: 32px;
      height: 32px;
    }
    h1 {
      margin: 0;
      font-size: 20px;
      font-weight: 500;
    }
    main {
      display: grid;
      gap: 20px;
      max-width: 1040px;
      margin: 0 auto;
      padding: 24px max(16px, var(--sc-inset-right)) calc(32px + var(--sc-inset-bottom))
        max(16px, var(--sc-inset-left));
    }
    .banner {
      position: relative;
      overflow: hidden;
      padding: 28px 28px 76px;
      border-radius: var(--sc-radius);
      background: var(--sc-sea);
      color: var(--sc-sea-ink);
    }
    .banner h2 {
      margin: 0 0 8px;
      font-size: 26px;
      font-weight: 500;
      text-wrap: balance;
    }
    .banner p {
      position: relative;
      max-width: 60ch;
      margin: 0;
      color: var(--sc-sea-ink2);
      font-size: 15px;
      line-height: 1.5;
    }
    .waves {
      position: absolute;
      inset: auto 0 0;
      width: 100%;
      height: 64px;
    }
    .waves .back {
      fill: var(--sc-sea-wave3);
    }
    .waves .front {
      fill: var(--sc-sea-wave);
    }
    .waves .crest {
      fill: none;
      stroke: var(--sc-sea-wave2);
      stroke-width: 2;
      vector-effect: non-scaling-stroke;
    }
    .profiles {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 16px;
    }
    .card {
      margin: 0;
      padding: 16px 18px;
      border: 1px solid var(--sc-line);
      border-radius: var(--sc-radius);
      background: var(--sc-card);
    }
    .card header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 6px;
    }
    h3 {
      margin: 0;
      color: var(--sc-fg2);
      font-size: 13px;
      font-weight: 500;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }
    .count {
      min-width: 12px;
      padding: 2px 8px;
      border-radius: 999px;
      background: var(--sc-primary-tint);
      color: var(--sc-primary-ink);
      font-size: 13px;
      font-weight: 500;
      text-align: center;
    }
    ul {
      margin: 0;
      padding: 0;
      list-style: none;
    }
    li {
      display: grid;
      gap: 2px;
      padding: 10px 0;
      border-top: 1px solid var(--sc-line2);
    }
    li:first-child {
      border-top: none;
    }
    .name {
      font-size: 15px;
    }
    .detail,
    .none,
    .loading,
    .advisory,
    .actions p {
      color: var(--sc-fg2);
      font-size: 14px;
    }
    .none {
      margin: 8px 0 4px;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 12px 20px;
    }
    .actions p {
      margin: 0;
    }
    .button {
      display: inline-flex;
      align-items: center;
      min-height: 40px;
      padding: 0 20px;
      border-radius: 999px;
      background: var(--sc-btn);
      color: var(--sc-btn-ink);
      font-size: 14px;
      font-weight: 500;
      text-decoration: none;
    }
    .button:focus-visible {
      outline: 2px solid var(--sc-focus);
      outline-offset: 2px;
    }
    .error {
      border-color: transparent;
      background: var(--sc-danger-bg);
      color: var(--sc-danger);
    }
    .advisory {
      margin: 4px 0 0;
      font-size: 13px;
    }
  `;
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
