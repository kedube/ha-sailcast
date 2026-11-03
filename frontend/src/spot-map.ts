/**
 * The spot editor's map: a pin on the water and the wind map's circle around
 * it. Select the map or drag the pin to move it; arrow keys move it too.
 *
 * The base map is OpenStreetMap through Home Assistant's own tile proxy,
 * which takes a short-lived token. If that internal interface isn't there,
 * the map falls back to OpenFreeMap. OpenSeaMap's seamarks go on top.
 * MapLibre is only loaded when the map is shown.
 */
import type { Feature } from "geojson";
import { css, html, LitElement, unsafeCSS, type PropertyValues, type TemplateResult } from "lit";

import { define } from "./dialog";
import { circle } from "./geo";
import type { HomeAssistant } from "./types";

type MapLibre = typeof import("maplibre-gl");
type MapInstance = InstanceType<MapLibre["Map"]>;
type MarkerInstance = InstanceType<MapLibre["Marker"]>;

const SEAMARKS = "https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png";
const FALLBACK_STYLE = "https://tiles.openfreemap.org/styles/liberty";
// Tokens change every 30 minutes and two are accepted at a time.
const TOKEN_REFRESH = 20 * 60 * 1000;
const ATTRIBUTION =
  '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors · ' +
  'Seamarks © <a href="https://www.openseamap.org" target="_blank" rel="noopener">OpenSeaMap</a>';

export class ScSpotMap extends LitElement {
  static override properties = {
    hass: { attribute: false },
    latitude: { type: Number },
    longitude: { type: Number },
    radius: { type: Number },
    label: { type: String },
    failed: { state: true },
  };

  declare hass: HomeAssistant;
  declare latitude: number;
  declare longitude: number;
  /** Meters. */
  declare radius: number;
  declare label: string;
  declare failed: boolean;

  private map?: MapInstance;
  private marker?: MarkerInstance;
  private refresher?: number;

  constructor() {
    super();
    this.failed = false;
    this.label = "";
  }

  protected override firstUpdated(): void {
    void this.load();
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    window.clearInterval(this.refresher);
    this.map?.remove();
    this.map = undefined;
  }

  private async token(): Promise<string | undefined> {
    try {
      const result = await this.hass.connection.sendMessagePromise<{ token: string }>({
        type: "map_tiles/access_token",
      });
      return result.token;
    } catch {
      return undefined;
    }
  }

  private async load(): Promise<void> {
    let maplibre: MapLibre;
    let styleSheet: string;
    try {
      [maplibre, styleSheet] = await Promise.all([
        import("maplibre-gl"),
        import("maplibre-gl/dist/maplibre-gl.css?inline").then((module) => module.default),
      ]);
    } catch {
      this.failed = true;
      return;
    }
    if (import.meta.env.DEV) {
      // The dev server bundles MapLibre elsewhere, so point it at its worker.
      maplibre.setWorkerUrl(
        `${location.origin}/node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs`,
      );
    }
    const sheet = new CSSStyleSheet();
    sheet.replaceSync(styleSheet);
    const root = this.renderRoot as ShadowRoot;
    root.adoptedStyleSheets = [...root.adoptedStyleSheets, sheet];

    const token = await this.token();
    const container = root.querySelector<HTMLElement>(".map");
    if (!container || !this.isConnected) return;
    const tiles = (key: string): string =>
      `${location.origin}/api/map_tiles/raster/{z}/{x}/{y}.png?token=${key}`;
    const map = new maplibre.Map({
      container,
      style: token
        ? {
            version: 8,
            sources: {
              osm: { type: "raster", tiles: [tiles(token)], tileSize: 256, maxzoom: 19 },
            },
            layers: [{ id: "osm", type: "raster", source: "osm" }],
          }
        : FALLBACK_STYLE,
      center: [this.longitude, this.latitude],
      zoom: 10,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
    });
    this.map = map;
    map.addControl(
      new maplibre.AttributionControl({ compact: true, customAttribution: ATTRIBUTION }),
      "bottom-right",
    );
    map.addControl(new maplibre.NavigationControl({ showCompass: false }), "top-right");
    map.touchZoomRotate.disableRotation();
    if (token) {
      this.refresher = window.setInterval(async () => {
        const fresh = await this.token();
        const source = map.getSource("osm") as { setTiles?: (tiles: string[]) => void } | undefined;
        if (fresh) source?.setTiles?.([tiles(fresh)]);
      }, TOKEN_REFRESH);
    }
    const color = getComputedStyle(this).getPropertyValue("--sc-btn").trim() || "#0a6a9c";
    this.marker = new maplibre.Marker({ draggable: true, color })
      .setLngLat([this.longitude, this.latitude])
      .addTo(map);
    this.marker.on("dragend", () => {
      const where = this.marker!.getLngLat();
      this.move(where.lat, where.lng);
    });
    map.on("click", (event) => this.move(event.lngLat.lat, event.lngLat.lng));
    map.on("load", () => {
      map.resize();
      map.addSource("seamarks", { type: "raster", tiles: [SEAMARKS], tileSize: 256, maxzoom: 18 });
      map.addLayer({ id: "seamarks", type: "raster", source: "seamarks", minzoom: 9 });
      map.addSource("area", {
        type: "geojson",
        data: circle(this.latitude, this.longitude, this.radius),
      });
      const tint = getComputedStyle(this).getPropertyValue("--sc-primary").trim() || "#03a9f4";
      map.addLayer({
        id: "area-fill",
        type: "fill",
        source: "area",
        paint: { "fill-color": tint, "fill-opacity": 0.1 },
      });
      map.addLayer({
        id: "area-line",
        type: "line",
        source: "area",
        paint: { "line-color": tint, "line-width": 1.5, "line-dasharray": [3, 2] },
      });
      this.fit(false);
    });
  }

  private move(latitude: number, longitude: number): void {
    this.dispatchEvent(
      new CustomEvent("pin", { detail: { latitude, longitude }, bubbles: true, composed: true }),
    );
  }

  /** Show the whole circle. */
  private fit(animate = true): void {
    const map = this.map;
    if (!map) return;
    const ring = circle(this.latitude, this.longitude, this.radius).geometry.coordinates[0];
    const lons = ring.map((point: number[]) => point[0]);
    const lats = ring.map((point: number[]) => point[1]);
    map.fitBounds(
      [
        [Math.min(...lons), Math.min(...lats)],
        [Math.max(...lons), Math.max(...lats)],
      ],
      { padding: 24, animate },
    );
  }

  protected override updated(changed: PropertyValues<this>): void {
    const map = this.map;
    if (!map) return;
    if (changed.has("latitude") || changed.has("longitude") || changed.has("radius")) {
      this.marker?.setLngLat([this.longitude, this.latitude]);
      const source = map.getSource("area") as { setData?: (data: Feature) => void } | undefined;
      source?.setData?.(circle(this.latitude, this.longitude, this.radius));
      if (changed.has("radius")) this.fit();
    }
  }

  private onKey(event: KeyboardEvent): void {
    const steps: Record<string, [number, number]> = {
      ArrowUp: [0.002, 0],
      ArrowDown: [-0.002, 0],
      ArrowLeft: [0, -0.003],
      ArrowRight: [0, 0.003],
    };
    const step = steps[event.key];
    if (!step) return;
    event.preventDefault();
    this.move(this.latitude + step[0], this.longitude + step[1]);
  }

  protected override render(): TemplateResult {
    return html`<div
        class="map"
        tabindex="0"
        role="application"
        aria-label=${this.label}
        @keydown=${this.onKey}
      ></div>
      ${this.failed ? html`<p class="failed">${this.label}</p>` : ""}`;
  }

  static override styles = css`
    :host {
      display: block;
      position: relative;
      width: 100%;
      aspect-ratio: 1.25;
      max-width: 100%;
      overflow: hidden;
      border: 1px solid var(--sc-line);
      border-radius: 12px;
      background: ${unsafeCSS("#d4e6f3")};
    }
    /* More specific than MapLibre's own .maplibregl-map, which would make
       the container relative and, with no height of its own, empty. */
    :host > .map {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
    }
    .map:focus-visible {
      outline: 2px solid var(--sc-focus);
      outline-offset: -2px;
    }
    .failed {
      position: absolute;
      inset: auto 8px 8px;
      margin: 0;
      color: #15222c;
      font-size: 12px;
    }
  `;
}

define("sc-spot-map", ScSpotMap);

declare global {
  interface HTMLElementTagNameMap {
    "sc-spot-map": ScSpotMap;
  }
}
