/**
 * What the spot editor's map and the wind map share: MapLibre, loaded only
 * when a map is shown, and the base map.
 *
 * The base map is OpenStreetMap through Home Assistant's own tile proxy,
 * which takes a short-lived token. If that internal interface isn't there,
 * the map falls back to OpenFreeMap. OpenSeaMap's seamarks go on top.
 */
import type { HomeAssistant } from "./types";

export type MapLibre = typeof import("maplibre-gl");
export type MapInstance = InstanceType<MapLibre["Map"]>;

const SEAMARKS = "https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png";
const FALLBACK_STYLE = "https://tiles.openfreemap.org/styles/liberty";
// Tokens change every 30 minutes and two are accepted at a time.
const TOKEN_REFRESH = 20 * 60 * 1000;

export const MAP_CREDITS =
  '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors · ' +
  'Seamarks © <a href="https://www.openseamap.org" target="_blank" rel="noopener">OpenSeaMap</a>';

/** Load MapLibre and add its styles to a shadow root; undefined if it can't load. */
export async function loadMapLibre(root: ShadowRoot): Promise<MapLibre | undefined> {
  let maplibre: MapLibre;
  let styles: string;
  try {
    [maplibre, styles] = await Promise.all([
      import("maplibre-gl"),
      import("maplibre-gl/dist/maplibre-gl.css?inline").then((module) => module.default),
    ]);
  } catch {
    return undefined;
  }
  if (import.meta.env.DEV) {
    // The dev server bundles MapLibre elsewhere, so point it at its worker.
    maplibre.setWorkerUrl(
      `${location.origin}/node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs`,
    );
  }
  const sheet = new CSSStyleSheet();
  sheet.replaceSync(styles);
  root.adoptedStyleSheets = [...root.adoptedStyleSheets, sheet];
  return maplibre;
}

async function token(hass: HomeAssistant): Promise<string | undefined> {
  try {
    const result = await hass.connection.sendMessagePromise<{ token: string }>({
      type: "map_tiles/access_token",
    });
    return result.token;
  } catch {
    return undefined;
  }
}

function tiles(key: string): string {
  return `${location.origin}/api/map_tiles/raster/{z}/{x}/{y}.png?token=${key}`;
}

/**
 * Create a map in a container with the base map, the zoom buttons and the
 * credits, and keep its tile token fresh. `stop` removes it again.
 */
export async function createMap(
  maplibre: MapLibre,
  container: HTMLElement,
  hass: HomeAssistant,
  options: { center: [number, number]; zoom: number; credits: string },
): Promise<{ map: MapInstance; stop: () => void }> {
  const key = await token(hass);
  const map = new maplibre.Map({
    container,
    style: key
      ? {
          version: 8,
          sources: { osm: { type: "raster", tiles: [tiles(key)], tileSize: 256, maxzoom: 19 } },
          layers: [{ id: "osm", type: "raster", source: "osm" }],
        }
      : FALLBACK_STYLE,
    center: options.center,
    zoom: options.zoom,
    attributionControl: false,
    dragRotate: false,
    pitchWithRotate: false,
  });
  map.addControl(
    new maplibre.AttributionControl({ compact: true, customAttribution: options.credits }),
    "bottom-right",
  );
  map.addControl(new maplibre.NavigationControl({ showCompass: false }), "top-right");
  map.touchZoomRotate.disableRotation();
  const refresher = key
    ? window.setInterval(async () => {
        const fresh = await token(hass);
        const source = map.getSource("osm") as { setTiles?: (urls: string[]) => void } | undefined;
        if (fresh) source?.setTiles?.([tiles(fresh)]);
      }, TOKEN_REFRESH)
    : undefined;
  return {
    map,
    stop: () => {
      window.clearInterval(refresher);
      map.remove();
    },
  };
}

/** Add OpenSeaMap's seamarks, from zoom 9, under a layer if given. */
export function addSeamarks(map: MapInstance, before?: string): void {
  map.addSource("seamarks", { type: "raster", tiles: [SEAMARKS], tileSize: 256, maxzoom: 18 });
  map.addLayer({ id: "seamarks", type: "raster", source: "seamarks", minzoom: 9 }, before);
}
