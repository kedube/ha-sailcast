"""Waves where the ocean model can't see: wind waves over a fetch, and shelter.

Sheltered water and lakes get waves estimated from the wind and the open
water upwind, with the fetch-limited growth formula coastal engineers use
(Sverdrup, Munk and Bretschneider, for deep water). It assumes the wind has
blown long enough and the water is deep, which both lean toward bigger waves.

On open water, the ocean model's waves stand, unless they come from a
direction the spot is sheltered from. Then SailCast uses the larger of the
local estimate and half the model's height, leaning cautious because the
model's wave direction is itself coarse. Without a fetch to estimate from,
the model's waves stand.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, MutableMapping, Sequence
from enum import StrEnum
import math
from typing import Any, Final

from .geo import compass_point

GRAVITY: Final = 9.80665
METERS_PER_SECOND_PER_KNOT: Final = 0.514444


class WaveSource(StrEnum):
    """Where an hour's waves come from."""

    MODEL = "model"
    SHELTERED = "sheltered"
    ESTIMATE = "estimate"


def wind_waves(wind: float, fetch_km: float) -> tuple[float, float]:
    """Return the height (m) and period (s) of waves raised by wind (kt)."""
    speed = wind * METERS_PER_SECOND_PER_KNOT
    if speed <= 0 or fetch_km <= 0:
        return 0.0, 0.0
    reach = GRAVITY * fetch_km * 1000 / speed**2
    height = 0.283 * speed**2 / GRAVITY * math.tanh(0.0125 * reach**0.42)
    period = 7.54 * speed / GRAVITY * math.tanh(0.077 * reach**0.25)
    return height, period


def shelter(
    rows: Sequence[MutableMapping[str, Any]],
    *,
    open_water: bool,
    exposed: Collection[str] | None,
    fetch: Callable[[float], float] | None,
) -> None:
    """Set each hour's waves for where the spot is and what it's open to.

    `exposed` lists the compass points the spot is open to, or None if that
    isn't known; `fetch` gives the open water (km) upwind of a direction, or
    is None if that isn't known.
    """
    for row in rows:
        if not open_water:
            if fetch is None:
                continue
            height, period = wind_waves(row["wind"], fetch(row["wind_direction"]))
            row.update(
                wave_height=height,
                wave_period=period,
                wave_direction=row["wind_direction"],
                wave_source=WaveSource.ESTIMATE,
            )
            continue
        model = row.get("wave_height")
        if model is None:
            continue
        row["wave_source"] = WaveSource.MODEL
        direction = row.get("wave_direction")
        if (
            exposed is None
            or fetch is None
            or direction is None
            or compass_point(direction) in exposed
        ):
            continue
        height, period = wind_waves(row["wind"], fetch(row["wind_direction"]))
        row["wave_source"] = WaveSource.SHELTERED
        if height >= model / 2:
            row.update(
                wave_height=height,
                wave_period=period,
                wave_direction=row["wind_direction"],
            )
        else:
            row["wave_height"] = model / 2
