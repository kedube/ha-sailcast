/**
 * The wind map's numbers: the grid's wind as east and north components, read
 * anywhere between its points, and the colors of wind speeds.
 */
import type { WindGrid } from "./types";

export type Layer = "wind" | "gust";
type Rgb = [number, number, number];

/** Wind colors, as in the mockup: blue in light air to purple in a gale. */
export const WIND_STOPS: [number, Rgb][] = [
  [0, [91, 107, 184]],
  [4, [61, 143, 196]],
  [8, [43, 179, 164]],
  [12, [87, 194, 79]],
  [16, [227, 196, 58]],
  [20, [240, 138, 44]],
  [25, [224, 69, 58]],
  [30, [184, 50, 122]],
  [35, [123, 63, 160]],
];

/** The legend's marks, in knots. */
export const LEGEND_TICKS = [0, 5, 10, 15, 20, 25, 30, 35];

/** The color of a wind speed, blended between the stops. */
export function windColor(knots: number): Rgb {
  if (!(knots > 0)) return WIND_STOPS[0][1];
  for (let i = 1; i < WIND_STOPS.length; i++) {
    const [k1, c1] = WIND_STOPS[i];
    if (knots <= k1) {
      const [k0, c0] = WIND_STOPS[i - 1];
      const f = (knots - k0) / (k1 - k0);
      return [0, 1, 2].map((j) => Math.round(c0[j] + (c1[j] - c0[j]) * f)) as Rgb;
    }
  }
  return WIND_STOPS[WIND_STOPS.length - 1][1];
}

/** The legend's colors as a CSS gradient, left to right. */
export function legendGradient(): string {
  const top = WIND_STOPS[WIND_STOPS.length - 1][0];
  return `linear-gradient(to right, ${WIND_STOPS.map(
    ([knots, rgb]) => `rgb(${rgb.join(", ")}) ${((knots / top) * 100).toFixed(1)}%`,
  ).join(", ")})`;
}

/** The east and north parts of a wind (kt) from the direction it blows from. */
export function components(speed: number, from: number): [number, number] {
  const angle = (from * Math.PI) / 180;
  return [-speed * Math.sin(angle), -speed * Math.cos(angle)];
}

/** The direction (degrees) a wind blows from, given its east and north parts. */
export function fromDirection(east: number, north: number): number {
  return ((Math.atan2(-east, -north) * 180) / Math.PI + 360) % 360;
}

/** A grid's wind, ready to read at any point between its points. */
export class WindField {
  readonly grid: WindGrid;
  private readonly east: Float32Array[] = [];
  private readonly north: Float32Array[] = [];
  private readonly values: Record<Layer, Float32Array[]> = { wind: [], gust: [] };

  constructor(grid: WindGrid) {
    this.grid = grid;
  }

  get hours(): number {
    return this.grid.times.length;
  }

  /** Whether a point is inside the grid. */
  inside(latitude: number, longitude: number): boolean {
    const { south, north, west, east } = this.grid;
    return latitude >= south && latitude <= north && longitude >= west && longitude <= east;
  }

  private layer(layer: Layer, hour: number): Float32Array {
    let values = this.values[layer][hour];
    if (!values) {
      const source = (layer === "wind" ? this.grid.speed : this.grid.gust)[hour] ?? [];
      values = Float32Array.from(source, (value) => value ?? 0);
      this.values[layer][hour] = values;
    }
    return values;
  }

  private parts(hour: number): [Float32Array, Float32Array] {
    if (!this.east[hour]) {
      const speed = this.grid.speed[hour] ?? [];
      const direction = this.grid.direction[hour] ?? [];
      const east = new Float32Array(speed.length);
      const north = new Float32Array(speed.length);
      for (let point = 0; point < speed.length; point++) {
        [east[point], north[point]] = components(speed[point] ?? 0, direction[point] ?? 0);
      }
      this.east[hour] = east;
      this.north[hour] = north;
    }
    return [this.east[hour], this.north[hour]];
  }

  /** Read values between the four points around a place, clamped to the grid. */
  private sample(values: Float32Array, latitude: number, longitude: number): number {
    const { south, north, west, east, rows, cols } = this.grid;
    const row = Math.min(
      rows - 1,
      Math.max(0, ((latitude - south) / (north - south)) * (rows - 1)),
    );
    const col = Math.min(cols - 1, Math.max(0, ((longitude - west) / (east - west)) * (cols - 1)));
    const r0 = Math.min(rows - 2, Math.floor(row));
    const c0 = Math.min(cols - 2, Math.floor(col));
    const fr = row - r0;
    const fc = col - c0;
    const at = (r: number, c: number) => values[r * cols + c];
    return (
      (at(r0, c0) * (1 - fc) + at(r0, c0 + 1) * fc) * (1 - fr) +
      (at(r0 + 1, c0) * (1 - fc) + at(r0 + 1, c0 + 1) * fc) * fr
    );
  }

  /** The wind's east and north parts (kt) at a place and hour. */
  components(hour: number, latitude: number, longitude: number): [number, number] {
    const [east, north] = this.parts(hour);
    return [this.sample(east, latitude, longitude), this.sample(north, latitude, longitude)];
  }

  /** The wind or gust speed (kt) at a place and hour. */
  speed(hour: number, layer: Layer, latitude: number, longitude: number): number {
    return this.sample(this.layer(layer, hour), latitude, longitude);
  }

  /** The direction the wind blows from at a place and hour. */
  direction(hour: number, latitude: number, longitude: number): number {
    return fromDirection(...this.components(hour, latitude, longitude));
  }

  /**
   * Paint the wind or gust speed's colors over the grid, north at the top,
   * into an RGBA buffer of the given size.
   */
  paint(hour: number, layer: Layer, width: number, height: number): Uint8ClampedArray<ArrayBuffer> {
    const { south, north, west, east } = this.grid;
    const values = this.layer(layer, hour);
    const pixels = new Uint8ClampedArray(width * height * 4);
    for (let y = 0; y < height; y++) {
      const latitude = north - ((y + 0.5) / height) * (north - south);
      for (let x = 0; x < width; x++) {
        const longitude = west + ((x + 0.5) / width) * (east - west);
        const [r, g, b] = windColor(this.sample(values, latitude, longitude));
        const index = (y * width + x) * 4;
        pixels[index] = r;
        pixels[index + 1] = g;
        pixels[index + 2] = b;
        pixels[index + 3] = 255;
      }
    }
    return pixels;
  }
}
