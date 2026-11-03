"""Distances on the Earth's surface, in kilometers."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise
import math
from typing import Any

EARTH_RADIUS_KM = 6371.0
KM_PER_DEGREE = math.pi * EARTH_RADIUS_KM / 180
# The eight compass points, clockwise from north.
DIRECTIONS = ("n", "ne", "e", "se", "s", "sw", "w", "nw")

type Ring = Sequence[Sequence[float]]


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance between two points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def distance_to_area_km(lat: float, lon: float, geometry: dict[str, Any]) -> float:
    """Return how far a point is from a GeoJSON polygon, or 0 inside it.

    It works on a flat projection around the point, which is close enough for
    the few tens of kilometers that matter here.
    """
    if geometry["type"] == "Polygon":
        polygons = [geometry["coordinates"]]
    elif geometry["type"] == "MultiPolygon":
        polygons = geometry["coordinates"]
    else:
        raise ValueError(f"Unsupported geometry {geometry['type']}")
    scale = math.cos(math.radians(lat))

    def project(point: Sequence[float]) -> tuple[float, float]:
        return (
            (point[0] - lon) * scale * KM_PER_DEGREE,
            (point[1] - lat) * KM_PER_DEGREE,
        )

    nearest = math.inf
    for polygon in polygons:
        rings = [[project(point) for point in ring] for ring in polygon]
        if _inside(rings[0]) and not any(_inside(hole) for hole in rings[1:]):
            return 0.0
        for ring in rings:
            for a, b in pairwise(ring):
                nearest = min(nearest, _to_segment(a, b))
    return nearest


def _inside(ring: Sequence[tuple[float, float]]) -> bool:
    """Return whether the origin is inside a ring, by ray casting."""
    inside = False
    for (x1, y1), (x2, y2) in pairwise(ring):
        if (y1 > 0) != (y2 > 0) and x1 + (x2 - x1) * -y1 / (y2 - y1) > 0:
            inside = not inside
    return inside


def _to_segment(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Return the distance from the origin to a line segment."""
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / length))
    return math.hypot(ax + t * dx, ay + t * dy)


def compass_point(direction: float) -> str:
    """Return the nearest of the eight compass points, such as "ne".

    A direction halfway between two points goes to the next one clockwise.
    """
    return DIRECTIONS[math.floor(direction % 360 / 45 + 0.5) % len(DIRECTIONS)]


def angle_between(a: float, b: float) -> float:
    """Return the angle between two directions, from 0 to 180 degrees."""
    difference = abs(a - b) % 360
    return 360 - difference if difference > 180 else difference


def mean_direction(values: Sequence[float | None]) -> float:
    """Return the average of compass directions, so 350° and 10° make 0°."""
    known = [math.radians(value) for value in values if value is not None]
    if not known:
        return 0.0
    x = sum(math.cos(value) for value in known)
    y = sum(math.sin(value) for value in known)
    return math.degrees(math.atan2(y, x)) % 360
