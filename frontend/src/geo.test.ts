import { describe, expect, it } from "vitest";

import { circle } from "./geo";

describe("circle", () => {
  it("draws a closed ring the given distance from its center", () => {
    const ring = circle(32.7, -117.2, 10_000).geometry.coordinates[0];
    expect(ring).toHaveLength(65);
    expect(ring[0]).toEqual(ring[64]);
    // The first point is due north: 10 km is about 0.09° of latitude.
    expect(ring[0][1] - 32.7).toBeCloseTo(0.0899, 3);
    expect(ring[0][0]).toBeCloseTo(-117.2, 6);
  });
});
