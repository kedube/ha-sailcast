/**
 * The spot editor's map: a pin on the water, the wind map's circle around it,
 * and the tide and current stations nearby. Select the map or drag the pin to
 * move it; arrow keys move it too.
 */
import type { Feature } from "geojson";
import { css, html, LitElement, type PropertyValues, type TemplateResult } from "lit";

import { define } from "./dialog";
import { circle } from "./geo";
import { addSeamarks, createMap, loadMapLibre, MAP_CREDITS, type MapInstance } from "./map";
import type { HomeAssistant } from "./types";

type MarkerInstance = InstanceType<typeof import("maplibre-gl").Marker>;

/** A station to show on the map. */
export interface StationMark {
  kind: "tide" | "current";
  id: string;
  /** What a pointer over it reads, such as "Tide station: San Diego". */
  label: string;
  latitude: number;
  longitude: number;
}

export class ScSpotMap extends LitElement {
  static override properties = {
    hass: { attribute: false },
    latitude: { type: Number },
    longitude: { type: Number },
    radius: { type: Number },
    stations: { attribute: false },
    label: { type: String },
    failed: { state: true },
  };

  declare hass: HomeAssistant;
  declare latitude: number;
  declare longitude: number;
  /** Meters. */
  declare radius: number;
  declare stations: StationMark[];
  declare label: string;
  declare failed: boolean;

  private map?: MapInstance;
  private stop?: () => void;
  private pin?: MarkerInstance;
  private markers: MarkerInstance[] = [];
  private maplibre?: typeof import("maplibre-gl");

  constructor() {
    super();
    this.failed = false;
    this.label = "";
    this.stations = [];
  }

  protected override firstUpdated(): void {
    void this.load();
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    this.stop?.();
    this.map = undefined;
  }

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
    const { map, stop } = await createMap(maplibre, container, this.hass, {
      center: [this.longitude, this.latitude],
      zoom: 10,
      credits: MAP_CREDITS,
    });
    this.map = map;
    this.stop = stop;
    const color = getComputedStyle(this).getPropertyValue("--sc-btn").trim() || "#0a6a9c";
    this.pin = new maplibre.Marker({ draggable: true, color })
      .setLngLat([this.longitude, this.latitude])
      .addTo(map);
    this.pin.on("dragend", () => {
      const where = this.pin!.getLngLat();
      this.move(where.lat, where.lng);
    });
    map.on("click", (event) => this.move(event.lngLat.lat, event.lngLat.lng));
    map.on("load", () => {
      map.resize();
      addSeamarks(map);
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
      this.showStations();
    });
  }

  /** Put a marker on each station: a triangle for tides, a diamond for currents. */
  private showStations(): void {
    const { map, maplibre } = this;
    if (!map || !maplibre) return;
    for (const marker of this.markers) marker.remove();
    this.markers = this.stations.map((station) => {
      // MapLibre positions the marker with its own transform, so the shape
      // goes on an element inside it.
      const element = document.createElement("div");
      element.className = "station";
      element.title = station.label;
      element.setAttribute("role", "img");
      element.setAttribute("aria-label", station.label);
      const shape = document.createElement("span");
      shape.className = station.kind;
      element.append(shape);
      return new maplibre.Marker({ element })
        .setLngLat([station.longitude, station.latitude])
        .addTo(map);
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
      this.pin?.setLngLat([this.longitude, this.latitude]);
      const source = map.getSource("area") as { setData?: (data: Feature) => void } | undefined;
      source?.setData?.(circle(this.latitude, this.longitude, this.radius));
      if (changed.has("radius")) this.fit();
    }
    if (changed.has("stations") && map.loaded()) this.showStations();
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
      background: #d4e6f3;
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
    .station {
      display: grid;
      place-items: center;
      width: 16px;
      height: 16px;
      filter: drop-shadow(0 0 1px #ffffff) drop-shadow(0 1px 1px rgba(0, 0, 0, 0.45));
      cursor: default;
    }
    .station span {
      display: block;
      background: #2f4250;
    }
    .station .tide {
      width: 13px;
      height: 12px;
      clip-path: polygon(50% 0, 100% 100%, 0 100%);
    }
    .station .current {
      width: 9px;
      height: 9px;
      transform: rotate(45deg);
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
