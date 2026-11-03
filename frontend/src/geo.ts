/** Shapes on the map. */
import type { Feature, Polygon } from "geojson";

const EARTH_RADIUS = 6_371_000;

/** A circle around a point, as a GeoJSON polygon. */
export function circle(
  latitude: number,
  longitude: number,
  meters: number,
  steps = 64,
): Feature<Polygon> {
  const lat = (latitude * Math.PI) / 180;
  const lon = (longitude * Math.PI) / 180;
  const angular = meters / EARTH_RADIUS;
  const ring: [number, number][] = [];
  for (let step = 0; step <= steps; step++) {
    const bearing = (step / steps) * 2 * Math.PI;
    const lat2 = Math.asin(
      Math.sin(lat) * Math.cos(angular) + Math.cos(lat) * Math.sin(angular) * Math.cos(bearing),
    );
    const lon2 =
      lon +
      Math.atan2(
        Math.sin(bearing) * Math.sin(angular) * Math.cos(lat),
        Math.cos(angular) - Math.sin(lat) * Math.sin(lat2),
      );
    ring.push([(lon2 * 180) / Math.PI, (lat2 * 180) / Math.PI]);
  }
  return { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [ring] } };
}
