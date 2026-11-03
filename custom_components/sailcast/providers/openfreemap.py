"""OpenFreeMap's map tiles: OpenStreetMap's water, for working out fetch.

The tiles follow the OpenMapTiles schema, whose `water` layer holds the sea,
lakes, rivers and ponds as polygons. They're Mapbox Vector Tiles, which are
protocol buffers; the small reader here decodes just what SailCast needs, so
it has no third-party requirements. The tiles' address changes with each
weekly build, so it's read from OpenFreeMap's TileJSON first.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
import gzip
import math
from typing import Any, Final

import aiohttp

from . import ProviderError, fetch_bytes, fetch_json

TILEJSON_URL: Final = "https://tiles.openfreemap.org/planet"
ZOOM: Final = 12
# How far around a spot the tiles reach, in km.
REACH_KM: Final = 20.0
# Water that isn't open water.
SKIPPED: Final = frozenset({"swimming_pool"})

_LAYERS: Final = 3
_LAYER_NAME: Final = 1
_LAYER_FEATURES: Final = 2
_LAYER_KEYS: Final = 3
_LAYER_VALUES: Final = 4
_LAYER_EXTENT: Final = 5
_FEATURE_TAGS: Final = 2
_FEATURE_TYPE: Final = 3
_FEATURE_GEOMETRY: Final = 4
_POLYGON: Final = 3
_MOVE_TO, _LINE_TO, _CLOSE_PATH = 1, 2, 7

type Ring = tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class WaterTile:
    """The open water in one tile, as polygons in the tile's own units.

    Each polygon is a list of rings, outer and inner alike; a point is in the
    polygon if it's inside an odd number of them. Units run from 0 to `extent`
    across the tile, with y growing southward, and can stray a little past
    the edges.
    """

    z: int
    x: int
    y: int
    extent: int
    polygons: tuple[tuple[Ring, ...], ...]


async def async_get_template(session: aiohttp.ClientSession) -> str:
    """Return the address of the current tiles, with {z}, {x} and {y} in it."""
    tilejson = await fetch_json(session, TILEJSON_URL)
    try:
        template = tilejson["tiles"][0]
    except (KeyError, IndexError, TypeError) as err:
        raise ProviderError("OpenFreeMap's TileJSON has no tiles") from err
    if not isinstance(template, str) or "{z}" not in template:
        raise ProviderError("OpenFreeMap's TileJSON has an odd tile address")
    return template


async def async_get_water(
    session: aiohttp.ClientSession, template: str, z: int, x: int, y: int
) -> WaterTile:
    """Return the open water in one tile."""
    body = await fetch_bytes(session, template.format(z=z, x=x, y=y))
    return water(body, z, x, y)


def tiles_around(
    latitude: float, longitude: float, km: float, zoom: int = ZOOM
) -> set[tuple[int, int, int]]:
    """Return the tiles that cover a distance around a point."""
    lat_span = km / 111.195
    lon_span = km / (111.195 * max(0.01, math.cos(math.radians(latitude))))
    x0, y0 = tile_of(latitude + lat_span, longitude - lon_span, zoom)
    x1, y1 = tile_of(latitude - lat_span, longitude + lon_span, zoom)
    return {
        (zoom, x, y)
        for x in range(int(x0), int(x1) + 1)
        for y in range(int(y0), int(y1) + 1)
    }


def tile_of(latitude: float, longitude: float, zoom: int) -> tuple[float, float]:
    """Return where a point is in tiles at a zoom, with the fraction kept."""
    n = 2**zoom
    x = (longitude + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(latitude))) / math.pi) / 2 * n
    return x, y


def position(tile: WaterTile, column: float, row: float) -> tuple[float, float]:
    """Return the latitude and longitude of a place in a tile's units."""
    n = 2**tile.z
    longitude = (tile.x + column / tile.extent) / n * 360 - 180
    latitude = math.degrees(
        math.atan(math.sinh(math.pi * (1 - 2 * (tile.y + row / tile.extent) / n)))
    )
    return latitude, longitude


def water(body: bytes, z: int, x: int, y: int) -> WaterTile:
    """Read the open water from a tile."""
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    try:
        for number, value in _fields(body):
            if number == _LAYERS and isinstance(value, bytes):
                layer = _layer(value)
                if layer is not None:
                    extent, polygons = layer
                    return WaterTile(z, x, y, extent, polygons)
    except (IndexError, ValueError, UnicodeDecodeError) as err:
        raise ProviderError(f"Couldn't read map tile {z}/{x}/{y}: {err}") from err
    return WaterTile(z, x, y, 4096, ())


def only_layer(body: bytes, name: str) -> bytes:
    """Return a tile with only one of its layers, for recording small fixtures."""
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    for number, value in _fields(body):
        if number == _LAYERS and isinstance(value, bytes):
            names = [v for n, v in _fields(value) if n == _LAYER_NAME]
            if names and isinstance(names[0], bytes) and names[0].decode() == name:
                return bytes([_LAYERS << 3 | 2]) + _varint_bytes(len(value)) + value
    return b""


def _layer(body: bytes) -> tuple[int, tuple[tuple[Ring, ...], ...]] | None:
    """Return the water layer's extent and open-water polygons, or None."""
    name, extent = "", 4096
    keys: list[str] = []
    values: list[Any] = []
    features: list[bytes] = []
    for number, value in _fields(body):
        if number == _LAYER_NAME and isinstance(value, bytes):
            name = value.decode()
        elif number == _LAYER_EXTENT and isinstance(value, int):
            extent = value
        elif number == _LAYER_KEYS and isinstance(value, bytes):
            keys.append(value.decode())
        elif number == _LAYER_VALUES and isinstance(value, bytes):
            values.append(_value(value))
        elif number == _LAYER_FEATURES and isinstance(value, bytes):
            features.append(value)
    if name != "water":
        return None
    polygons = []
    for feature in features:
        kind, properties, geometry = _feature(feature, keys, values)
        if (
            kind == _POLYGON
            and properties.get("class") not in SKIPPED
            and (rings := _rings(geometry))
        ):
            polygons.append(rings)
    return extent, tuple(polygons)


def _feature(
    body: bytes, keys: list[str], values: list[Any]
) -> tuple[int, dict[str, Any], list[int]]:
    """Return a feature's type, properties and geometry commands."""
    tags: list[int] = []
    kind = 0
    geometry: list[int] = []
    for number, value in _fields(body):
        if number == _FEATURE_TAGS and isinstance(value, bytes):
            tags = _packed(value)
        elif number == _FEATURE_TYPE and isinstance(value, int):
            kind = value
        elif number == _FEATURE_GEOMETRY and isinstance(value, bytes):
            geometry = _packed(value)
    properties = {
        keys[tags[i]]: values[tags[i + 1]] for i in range(0, len(tags) - 1, 2)
    }
    return kind, properties, geometry


def _rings(geometry: list[int]) -> tuple[Ring, ...]:
    """Decode a polygon's commands into closed rings."""
    rings: list[list[tuple[float, float]]] = []
    index = x = y = 0
    while index < len(geometry):
        command, count = geometry[index] & 7, geometry[index] >> 3
        index += 1
        if command == _CLOSE_PATH:
            if rings and rings[-1][0] != rings[-1][-1]:
                rings[-1].append(rings[-1][0])
            continue
        for _ in range(count):
            x += _zigzag(geometry[index])
            y += _zigzag(geometry[index + 1])
            index += 2
            if command == _MOVE_TO:
                rings.append([(x, y)])
            elif command == _LINE_TO and rings:
                rings[-1].append((x, y))
    return tuple(tuple(ring) for ring in rings if len(ring) >= 4)


def _value(body: bytes) -> Any:
    for number, value in _fields(body):
        if number == 1 and isinstance(value, bytes):
            return value.decode()
        return value
    return None


def _fields(body: bytes) -> Iterator[tuple[int, int | bytes]]:
    """Yield a protocol buffer message's field numbers and raw values."""
    index, end = 0, len(body)
    while index < end:
        key, index = _varint(body, index)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, index = _varint(body, index)
            yield number, value
        elif wire == 2:
            length, index = _varint(body, index)
            yield number, body[index : index + length]
            index += length
        elif wire == 1:
            yield number, body[index : index + 8]
            index += 8
        elif wire == 5:
            yield number, body[index : index + 4]
            index += 4
        else:
            raise ValueError(f"unknown wire type {wire}")


def _varint(body: bytes, index: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        byte = body[index]
        index += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, index
        shift += 7


def _varint_bytes(value: int) -> bytes:
    out = bytearray()
    while True:
        byte, value = value & 0x7F, value >> 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _packed(body: bytes) -> list[int]:
    values, index = [], 0
    while index < len(body):
        value, index = _varint(body, index)
        values.append(value)
    return values


def _zigzag(value: int) -> int:
    return (value >> 1) ^ -(value & 1)
