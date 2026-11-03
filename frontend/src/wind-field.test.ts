import { describe, expect, it } from "vitest";

import type { WindGrid } from "./types";
import { components, fromDirection, legendGradient, windColor, WindField } from "./wind-field";

/** A 3 x 3 grid over two hours: a westerly building to the north. */
function grid(): WindGrid {
  return {
    fetched: "2026-11-02T22:05:00+00:00",
    stale: false,
    south: 32.6,
    west: -117.4,
    north: 32.8,
    east: -117.0,
    rows: 3,
    cols: 3,
    spots: ["harbor"],
    times: ["2026-11-02T22:00:00+00:00", "2026-11-02T23:00:00+00:00"],
    speed: [
      [10, 10, 10, 14, 14, 14, 18, 18, 18],
      [12, 12, 12, 16, 16, 16, null, 20, 20],
    ],
    gust: [
      [15, 15, 15, 19, 19, 19, 23, 23, 23],
      [17, 17, 17, 21, 21, 21, 25, 25, 25],
    ],
    direction: [
      [270, 270, 270, 270, 270, 270, 270, 270, 270],
      [0, 0, 0, 90, 90, 90, 180, 180, 180],
    ],
  };
}

describe("components", () => {
  it("splits wind into east and north parts, and back", () => {
    const [east, north] = components(10, 270);
    // A westerly blows toward the east.
    expect(east).toBeCloseTo(10);
    expect(north).toBeCloseTo(0);
    expect(fromDirection(east, north)).toBeCloseTo(270);
    const [e2, n2] = components(10, 0);
    expect(n2).toBeCloseTo(-10);
    expect(fromDirection(e2, n2)).toBeCloseTo(0);
  });
});

describe("WindField", () => {
  const field = new WindField(grid());

  it("reads values between points", () => {
    // Halfway between the south and middle rows: 12 kt.
    expect(field.speed(0, "wind", 32.65, -117.2)).toBeCloseTo(12);
    expect(field.speed(0, "gust", 32.8, -117.0)).toBeCloseTo(23);
    expect(field.direction(0, 32.7, -117.2)).toBeCloseTo(270);
  });

  it("holds the edge's value outside the grid", () => {
    expect(field.speed(0, "wind", 33.5, -117.2)).toBeCloseTo(18);
    expect(field.inside(33.5, -117.2)).toBe(false);
    expect(field.inside(32.7, -117.2)).toBe(true);
  });

  it("treats a missing value as calm", () => {
    expect(field.speed(1, "wind", 32.8, -117.4)).toBe(0);
  });

  it("paints the colors with north at the top", () => {
    const pixels = field.paint(0, "wind", 2, 2);
    expect(pixels).toHaveLength(16);
    const top = Array.from(pixels.slice(0, 3));
    const bottom = Array.from(pixels.slice(8, 11));
    expect(top).toEqual(windColor(field.speed(0, "wind", 32.75, -117.3)));
    expect(bottom).toEqual(windColor(field.speed(0, "wind", 32.65, -117.3)));
    expect(pixels[3]).toBe(255);
  });
});

describe("windColor", () => {
  it("blends between the stops and holds past the ends", () => {
    expect(windColor(0)).toEqual([91, 107, 184]);
    expect(windColor(2)).toEqual([76, 125, 190]);
    expect(windColor(50)).toEqual([123, 63, 160]);
    expect(windColor(Number.NaN)).toEqual([91, 107, 184]);
  });

  it("gives the legend a gradient across the scale", () => {
    expect(legendGradient()).toMatch(/^linear-gradient\(to right, rgb\(91, 107, 184\) 0\.0%/);
    expect(legendGradient()).toMatch(/rgb\(123, 63, 160\) 100\.0%\)$/);
  });
});
