/**
 * The wind map: the wind or gust speed as colors over the base map, moving
 * particles that follow the wind, a time slider with play and pause, buttons
 * that jump to a day, and a readout of the wind under the pointer.
 *
 * The colors are a canvas pinned to the grid's corners, so MapLibre moves
 * them with the map. The particles move on a canvas over the map, in screen
 * pixels, so they keep their pace at any zoom. When the device asks for
 * reduced motion, arrows replace them. Nothing animates while the map is out
 * of sight.
 */
import { css, html, LitElement, nothing, type PropertyValues, type TemplateResult } from "lit";

import { define } from "./dialog";
import { localTime, type Formatter } from "./format";
import { icon } from "./glyphs";
import { addSeamarks, createMap, loadMapLibre, MAP_CREDITS, type MapInstance } from "./map";
import { styles } from "./styles";
import { compass, type Translate } from "./text";
import type { Spot, WindGrid } from "./types";
import { LEGEND_TICKS, legendGradient, WindField, type Layer } from "./wind-field";

type MarkerInstance = InstanceType<typeof import("maplibre-gl").Marker>;
interface CanvasSource {
  play(): void;
  pause(): void;
}

/** The color field's size in pixels; MapLibre smooths it as it stretches it. */
const FIELD_SIZE = 128;
const PLAY_STEP = 700;
// Particles, as in the mockup: how long one lives, in frames, and how far it
// moves in a frame for each knot, in pixels.
const MAX_AGE = 90;
const PACE = 0.075;
const ARROW_GAP = 44;
const CREDITS = `${MAP_CREDITS} · Wind © <a href="https://open-meteo.com" target="_blank" rel="noopener">Open-Meteo</a> (CC BY 4.0)`;

interface Dot {
  x: number;
  y: number;
  age: number;
}

export class ScWindMap extends LitElement {
  static override properties = {
    hass: { attribute: false },
    grid: { attribute: false },
    spots: { attribute: false },
    spotId: { type: String },
    t: { attribute: false },
    fmt: { attribute: false },
    hour: { state: true },
    layer: { state: true },
    playing: { state: true },
    readout: { state: true },
    failed: { state: true },
  };

  declare hass: import("./types").HomeAssistant;
  declare grid: WindGrid;
  declare spots: Spot[];
  declare spotId: string;
  declare t: Translate;
  declare fmt: Formatter;
  declare hour: number;
  declare layer: Layer;
  declare playing: boolean;
  declare readout?: string;
  declare failed: boolean;

  private field?: WindField;
  private map?: MapInstance;
  private stop?: () => void;
  private maplibre?: typeof import("maplibre-gl");
  private readonly fieldCanvas = document.createElement("canvas");
  private markers = new Map<string, MarkerInstance>();
  private dots: Dot[] = [];
  /** The map's screen position of the grid's corners, for turning pixels into places. */
  private corners = { left: 0, top: 0, right: 1, bottom: 1 };
  private size = { width: 1, height: 1, ratio: 1 };
  private frame = 0;
  private timer = 0;
  private onScreen = true;
  private observer?: IntersectionObserver;
  private readonly reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  /** Whether the screen is touched rather than pointed at. */
  private readonly touch = window.matchMedia?.("(hover: none)").matches;

  constructor() {
    super();
    this.hour = 0;
    this.layer = "wind";
    this.playing = false;
    this.failed = false;
    this.spots = [];
  }

  override connectedCallback(): void {
    super.connectedCallback();
    document.addEventListener("visibilitychange", this.visibilityChanged);
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    document.removeEventListener("visibilitychange", this.visibilityChanged);
    this.observer?.disconnect();
    this.setPlaying(false);
    this.halt();
    this.stop?.();
    this.map = undefined;
    this.markers.clear();
  }

  protected override willUpdate(changed: PropertyValues<this>): void {
    if (changed.has("grid") && this.grid) {
      this.field = new WindField(this.grid);
      this.hour = Math.min(this.hour, Math.max(0, this.field.hours - 1));
    }
  }

  protected override firstUpdated(): void {
    this.observer = new IntersectionObserver(([entry]) => {
      this.onScreen = entry.isIntersecting;
      this.resume();
    });
    this.observer.observe(this);
    void this.load();
  }

  protected override updated(changed: PropertyValues<this>): void {
    if (!this.map?.loaded()) return;
    if (changed.has("grid")) this.placeGrid();
    if (changed.has("grid") || changed.has("hour") || changed.has("layer")) {
      this.paintField();
      this.labelSpots();
      if (this.reduced) this.drawArrows();
    }
  }

  private visibilityChanged = (): void => this.resume();

  private async load(): Promise<void> {
    const root = this.renderRoot as ShadowRoot;
    const maplibre = await loadMapLibre(root);
    const container = root.querySelector<HTMLElement>(".map");
    if (!maplibre) {
      this.failed = true;
      return;
    }
    if (!container || !this.isConnected) return;
    this.maplibre = maplibre;
    const grid = this.grid;
    const { map, stop } = await createMap(maplibre, container, this.hass, {
      center: [(grid.west + grid.east) / 2, (grid.south + grid.north) / 2],
      zoom: 10,
      credits: CREDITS,
    });
    this.map = map;
    this.stop = stop;
    map.on("load", () => {
      map.resize();
      this.fieldCanvas.width = FIELD_SIZE;
      this.fieldCanvas.height = FIELD_SIZE;
      map.addSource("wind", {
        type: "canvas",
        canvas: this.fieldCanvas,
        coordinates: this.cornerCoordinates(),
        animate: false,
      });
      map.addLayer({
        id: "wind",
        type: "raster",
        source: "wind",
        paint: { "raster-opacity": 0.6, "raster-resampling": "linear", "raster-fade-duration": 0 },
      });
      addSeamarks(map);
      map.fitBounds(
        [
          [grid.west, grid.south],
          [grid.east, grid.north],
        ],
        { padding: 8, animate: false },
      );
      this.paintField();
      this.labelSpots();
      this.measure();
      this.resume();
    });
    map.on("move", () => {
      this.measure();
      if (this.reduced) this.drawArrows();
    });
    map.on("resize", () => this.measure());
    map.on("mousemove", (event) => this.read(event.lngLat.lat, event.lngLat.lng));
    map.on("click", (event) => this.read(event.lngLat.lat, event.lngLat.lng));
    map.getCanvasContainer().addEventListener("mouseleave", () => (this.readout = undefined));
  }

  private cornerCoordinates(): [
    [number, number],
    [number, number],
    [number, number],
    [number, number],
  ] {
    const { west, east, north, south } = this.grid;
    return [
      [west, north],
      [east, north],
      [east, south],
      [west, south],
    ];
  }

  /** Move the color field to a new grid's corners. */
  private placeGrid(): void {
    const source = this.map?.getSource("wind") as
      { setCoordinates?: (corners: [number, number][]) => void } | undefined;
    source?.setCoordinates?.(this.cornerCoordinates());
    for (const marker of this.markers.values()) marker.remove();
    this.markers.clear();
    this.labelSpots();
  }

  /** Paint the hour's colors and have MapLibre show them. */
  private paintField(): void {
    const field = this.field;
    const map = this.map;
    if (!field || !map || !field.hours) return;
    const context = this.fieldCanvas.getContext("2d");
    if (!context) return;
    const pixels = field.paint(this.hour, this.layer, FIELD_SIZE, FIELD_SIZE);
    context.putImageData(new ImageData(pixels, FIELD_SIZE, FIELD_SIZE), 0, 0);
    // A paused canvas source only takes a new picture while it plays.
    const source = map.getSource("wind") as CanvasSource | undefined;
    if (source) {
      source.play();
      map.once("render", () => source.pause());
      map.triggerRepaint();
    }
  }

  /** Put each spot the grid covers on the map, with its wind now. */
  private labelSpots(): void {
    const { map, maplibre, field } = this;
    if (!map || !maplibre || !field) return;
    for (const spot of this.spots.filter((item) => this.grid.spots.includes(item.id))) {
      let marker = this.markers.get(spot.id);
      if (!marker) {
        const element = document.createElement("div");
        element.className = "spot";
        element.innerHTML = "<i></i><span></span>";
        marker = new maplibre.Marker({ element, anchor: "left", offset: [-6, 0] })
          .setLngLat([spot.longitude, spot.latitude])
          .addTo(map);
        this.markers.set(spot.id, marker);
      }
      const element = marker.getElement();
      element.classList.toggle("chosen", spot.id === this.spotId);
      const speed = field.speed(this.hour, this.layer, spot.latitude, spot.longitude);
      element.querySelector("span")!.textContent = this.t("map.spot", {
        spot: spot.name,
        speed: this.fmt.number(speed),
      });
    }
  }

  /** Note where the grid is on screen, and size the particle canvas to the map. */
  private measure(): void {
    const map = this.map;
    const canvas = this.renderRoot.querySelector<HTMLCanvasElement>(".particles");
    if (!map || !canvas) return;
    const box = map.getContainer().getBoundingClientRect();
    const ratio = Math.min(2, window.devicePixelRatio || 1);
    const width = Math.max(1, Math.round(box.width));
    const height = Math.max(1, Math.round(box.height));
    if (width !== this.size.width || height !== this.size.height || ratio !== this.size.ratio) {
      this.size = { width, height, ratio };
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      canvas.getContext("2d")?.setTransform(ratio, 0, 0, ratio, 0, 0);
    }
    const { west, north, east, south } = this.grid;
    const topLeft = map.project([west, north]);
    const bottomRight = map.project([east, south]);
    this.corners = {
      left: topLeft.x,
      top: topLeft.y,
      right: bottomRight.x,
      bottom: bottomRight.y,
    };
    // Start the trails again, with as many particles as the grid's area on
    // screen calls for: fewer on small screens.
    const shown = this.shownArea();
    const count = Math.round(
      Math.min(
        1600,
        Math.max(150, ((shown.right - shown.left) * (shown.bottom - shown.top)) / 900),
      ),
    );
    this.dots = Array.from({ length: count }, () =>
      this.spawn(Math.floor(Math.random() * MAX_AGE)),
    );
    canvas.getContext("2d")?.clearRect(0, 0, width, height);
  }

  /** The part of the screen the grid covers. */
  private shownArea(): { left: number; top: number; right: number; bottom: number } {
    const { left, top, right, bottom } = this.corners;
    return {
      left: Math.max(0, left),
      top: Math.max(0, top),
      right: Math.min(this.size.width, right),
      bottom: Math.min(this.size.height, bottom),
    };
  }

  private spawn(age = 0): Dot {
    const area = this.shownArea();
    return {
      x: area.left + Math.random() * Math.max(1, area.right - area.left),
      y: area.top + Math.random() * Math.max(1, area.bottom - area.top),
      age,
    };
  }

  /** The place under a point on screen. */
  private placeAt(x: number, y: number): [number, number] {
    const { left, top, right, bottom } = this.corners;
    const { west, east, north, south } = this.grid;
    return [
      north - ((y - top) / (bottom - top)) * (north - south),
      west + ((x - left) / (right - left)) * (east - west),
    ];
  }

  private resume(): void {
    const running = this.onScreen && document.visibilityState !== "hidden" && Boolean(this.map);
    if (!running) {
      this.halt();
      if (this.playing) this.setPlaying(false);
      return;
    }
    if (this.reduced) {
      this.drawArrows();
    } else if (!this.frame) {
      this.frame = requestAnimationFrame(this.tick);
    }
  }

  private halt(): void {
    if (this.frame) cancelAnimationFrame(this.frame);
    this.frame = 0;
  }

  /** Move every particle one frame along the wind, leaving a fading trail. */
  private tick = (): void => {
    this.frame = 0;
    const canvas = this.renderRoot.querySelector<HTMLCanvasElement>(".particles");
    const context = canvas?.getContext("2d");
    const field = this.field;
    if (!context || !field || !field.hours) return;
    const { width, height } = this.size;
    const pace = PACE * Math.max(0.6, width / 640);
    context.globalCompositeOperation = "destination-in";
    context.fillStyle = "rgba(0, 0, 0, 0.92)";
    context.fillRect(0, 0, width, height);
    context.globalCompositeOperation = "source-over";
    context.strokeStyle = "rgba(255, 255, 255, 0.85)";
    context.lineWidth = 1.15;
    context.beginPath();
    const area = this.shownArea();
    for (const dot of this.dots) {
      if (++dot.age > MAX_AGE) {
        Object.assign(dot, this.spawn());
        continue;
      }
      const [latitude, longitude] = this.placeAt(dot.x, dot.y);
      const [east, north] = field.components(this.hour, latitude, longitude);
      const x = dot.x + east * pace;
      const y = dot.y - north * pace;
      context.moveTo(dot.x, dot.y);
      context.lineTo(x, y);
      dot.x = x;
      dot.y = y;
      if (x < area.left || x > area.right || y < area.top || y > area.bottom) {
        Object.assign(dot, this.spawn());
      }
    }
    context.stroke();
    this.frame = requestAnimationFrame(this.tick);
  };

  /** Draw still arrows across the grid, for reduced motion. */
  private drawArrows(): void {
    const canvas = this.renderRoot.querySelector<HTMLCanvasElement>(".particles");
    const context = canvas?.getContext("2d");
    const field = this.field;
    if (!context || !field || !field.hours) return;
    const { width, height } = this.size;
    context.clearRect(0, 0, width, height);
    const area = this.shownArea();
    context.fillStyle = "rgba(255, 255, 255, 0.9)";
    context.strokeStyle = "rgba(6, 16, 24, 0.6)";
    context.lineWidth = 1;
    for (let y = area.top + ARROW_GAP / 2; y < area.bottom; y += ARROW_GAP) {
      for (let x = area.left + ARROW_GAP / 2; x < area.right; x += ARROW_GAP) {
        const [latitude, longitude] = this.placeAt(x, y);
        const [east, north] = field.components(this.hour, latitude, longitude);
        context.save();
        context.translate(x, y);
        context.rotate(Math.atan2(east, north));
        context.beginPath();
        context.moveTo(0, -9);
        context.lineTo(-4, 1);
        context.lineTo(-1.2, 1);
        context.lineTo(-1.2, 8);
        context.lineTo(1.2, 8);
        context.lineTo(1.2, 1);
        context.lineTo(4, 1);
        context.closePath();
        context.fill();
        context.stroke();
        context.restore();
      }
    }
  }

  private read(latitude: number, longitude: number): void {
    const field = this.field;
    if (!field?.inside(latitude, longitude) || !field.hours) {
      this.readout = undefined;
      return;
    }
    this.readout = this.t("map.readout", {
      direction: compass(this.t, field.direction(this.hour, latitude, longitude)),
      speed: this.fmt.number(field.speed(this.hour, "wind", latitude, longitude)),
      gust: this.fmt.number(field.speed(this.hour, "gust", latitude, longitude)),
    });
  }

  private setPlaying(on: boolean): void {
    window.clearInterval(this.timer);
    this.timer = 0;
    this.playing = on;
    if (on) {
      this.timer = window.setInterval(() => {
        const hours = this.field?.hours ?? 1;
        this.hour = (this.hour + 1) % hours;
      }, PLAY_STEP);
    }
  }

  /** The hour's label, such as "Sat 2 PM", in the spot's time zone. */
  private timeLabel(hour: number): string {
    const time = this.grid.times[hour];
    if (!time) return "";
    const date = localTime(time, this.fmt.zone).date;
    const today = localTime(this.grid.times[0], this.fmt.zone).date;
    const day = date === today ? this.t("week.today") : this.fmt.weekday(date);
    return `${day} ${this.fmt.clock(time)}`;
  }

  /** Each day in the grid, and the hour to jump to: noon, or now if that's later. */
  private days(): { date: string; label: string; hour: number }[] {
    const zone = this.fmt.zone;
    const days: { date: string; label: string; hour: number }[] = [];
    this.grid.times.forEach((time, index) => {
      const local = localTime(time, zone);
      let day = days.find((item) => item.date === local.date);
      if (!day) {
        day = {
          date: local.date,
          label: days.length ? this.fmt.weekday(local.date) : this.t("week.today_short"),
          hour: index,
        };
        days.push(day);
      }
      if (local.hour <= 12) day.hour = index;
    });
    return days;
  }

  protected override render(): TemplateResult {
    const t = this.t;
    const hours = this.grid?.times.length ?? 0;
    const days = hours ? this.days() : [];
    const current = this.grid?.times[this.hour];
    const currentDate = current ? localTime(current, this.fmt.zone).date : "";
    return html`<section class="card map-card">
      <div class="map-head">
        <div class="seg-btns" role="group" aria-label=${t("map.layer_label")}>
          ${(["wind", "gust"] as const).map(
            (layer) =>
              html`<button
                type="button"
                aria-pressed=${this.layer === layer ? "true" : "false"}
                @click=${() => (this.layer = layer)}
              >
                ${t(`map.${layer}`)}
              </button>`,
          )}
        </div>
        <div class="mlegend" role="img" aria-label=${t("map.legend")}>
          <div class="bar" style="background:${legendGradient()}"></div>
          <div class="ticks">
            ${LEGEND_TICKS.map(
              (knots, index) =>
                html`<span
                  >${knots}${
                    index === LEGEND_TICKS.length - 1 ? ` ${t("unit.knots_short")}` : ""
                  }</span
                >`,
            )}
          </div>
        </div>
      </div>
      <div class="stage">
        <div
          class="map"
          role="application"
          aria-label=${t("map.label", { spot: this.spots.find((spot) => spot.id === this.spotId)?.name ?? "" })}
        ></div>
        <canvas class="particles" aria-hidden="true"></canvas>
        <div class="overlay read">${this.readout ?? t(this.touch ? "map.tap" : "map.point")}</div>
        <div class="overlay time">${this.timeLabel(this.hour)}</div>
        ${this.failed ? html`<p class="overlay failed">${t("map.failed")}</p>` : nothing}
      </div>
      <div class="timebar">
        <button type="button" class="play" @click=${() => this.setPlaying(!this.playing)}>
          ${
            this.playing
              ? html`<svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M6 4h4v16H6zm8 0h4v16h-4z"></path>
                </svg>`
              : html`<svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M7 4v16l13-8z"></path>
                </svg>`
          }
          <span>${t(this.playing ? "map.pause" : "map.play")}</span>
        </button>
        <input
          type="range"
          min="0"
          max=${Math.max(0, hours - 1)}
          step="1"
          .value=${String(this.hour)}
          aria-label=${t("map.time")}
          aria-valuetext=${this.timeLabel(this.hour)}
          @input=${(event: Event) => {
            this.setPlaying(false);
            this.hour = Number((event.target as HTMLInputElement).value);
          }}
        />
      </div>
      <div class="jump" role="group" aria-label=${t("map.jump")}>
        ${days.map(
          (day) =>
            html`<button
              type="button"
              aria-pressed=${day.date === currentDate ? "true" : "false"}
              @click=${() => {
                this.setPlaying(false);
                this.hour = day.hour;
              }}
            >
              ${day.label}
            </button>`,
        )}
      </div>
      <p class="attrib">
        ${
          this.grid?.stale
            ? html`${icon("info")}
              ${t("map.stale", { time: `${this.fmt.weekday(localTime(this.grid.fetched, this.fmt.zone).date)} ${this.fmt.clock(this.grid.fetched)}` })} `
            : nothing
        }
        ${t("map.credits")}
      </p>
    </section>`;
  }

  static override styles = [
    styles,
    css`
      .map-card {
        padding: 0;
        overflow: hidden;
      }
      .map-head {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: space-between;
        gap: 10px 16px;
        padding: 12px 14px;
      }
      .seg-btns {
        display: inline-flex;
        overflow: hidden;
        border: 1px solid var(--sc-line);
        border-radius: 999px;
      }
      .seg-btns button {
        padding: 6px 16px;
        border: 0;
        background: transparent;
        color: var(--sc-fg2);
        font-weight: 500;
        cursor: pointer;
      }
      .seg-btns button[aria-pressed="true"] {
        background: var(--sc-primary-tint);
        color: var(--sc-primary-ink);
      }
      .mlegend {
        display: grid;
        gap: 2px;
        width: min(240px, 60vw);
        color: var(--sc-fg2);
        font-size: 11px;
      }
      .mlegend .bar {
        height: 9px;
        border-radius: 5px;
      }
      .ticks {
        display: flex;
        justify-content: space-between;
        font-variant-numeric: tabular-nums;
      }
      .stage {
        position: relative;
        height: min(68vh, 640px);
        min-height: 320px;
        background: #d4e6f3;
        touch-action: pan-y;
      }
      /* More specific than MapLibre's own .maplibregl-map. */
      .stage > .map {
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
      }
      .particles {
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        pointer-events: none;
      }
      .overlay {
        position: absolute;
        margin: 0;
        padding: 5px 9px;
        border-radius: 8px;
        background: var(--sc-map-chip);
        color: var(--sc-map-ink);
        font-size: 12.5px;
        font-variant-numeric: tabular-nums;
        pointer-events: none;
      }
      .read {
        left: 10px;
        top: 10px;
      }
      /* Beside the zoom buttons. */
      .time {
        right: 50px;
        top: 10px;
        font-size: 13px;
        font-weight: 500;
      }
      .failed {
        right: 10px;
        top: 50px;
      }
      .spot {
        display: flex;
        align-items: center;
        gap: 6px;
        pointer-events: none;
      }
      .spot i {
        width: 9px;
        height: 9px;
        border: 2px solid rgba(6, 16, 24, 0.8);
        border-radius: 50%;
        background: #ffffff;
      }
      .spot.chosen i {
        width: 12px;
        height: 12px;
      }
      .spot span {
        color: #ffffff;
        font: 500 12px var(--sc-font);
        text-shadow:
          0 0 3px rgba(6, 16, 24, 0.9),
          0 0 1px rgba(6, 16, 24, 0.9);
        white-space: nowrap;
      }
      .timebar {
        display: grid;
        grid-template-columns: auto minmax(0, 1fr);
        align-items: center;
        gap: 12px;
        padding: 12px 14px 6px;
      }
      .play {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 14px;
        border: 1px solid var(--sc-line);
        border-radius: 999px;
        background: var(--sc-card);
        color: var(--sc-fg);
        font-weight: 500;
        cursor: pointer;
      }
      .play svg {
        width: 14px;
        height: 14px;
        fill: currentColor;
      }
      .jump {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        padding: 0 14px 12px;
      }
      .jump button {
        padding: 3px 10px;
        border: 1px solid var(--sc-line);
        border-radius: 999px;
        background: transparent;
        color: var(--sc-fg2);
        font-size: 12px;
        cursor: pointer;
      }
      .jump button[aria-pressed="true"] {
        border-color: var(--sc-primary);
        background: var(--sc-primary-tint);
        color: var(--sc-primary-ink);
      }
      .attrib {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 6px;
        margin: 0;
        padding: 10px 14px 14px;
        border-top: 1px solid var(--sc-line);
        color: var(--sc-fg2);
        font-size: 12px;
      }
      .attrib .i {
        width: 16px;
        height: 16px;
        fill: var(--sc-fg3);
      }
      @media (max-width: 600px) {
        .stage {
          height: min(62vh, 520px);
        }
      }
    `,
  ];
}

define("sc-wind-map", ScWindMap);

declare global {
  interface HTMLElementTagNameMap {
    "sc-wind-map": ScWindMap;
  }
}
