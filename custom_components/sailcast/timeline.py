"""The hourly conditions timeline, one per spot.

Every source is turned into one list of hours. Values are in SI units, except
wind and current, which are in knots because every threshold is set in knots.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class Alert:
    """An official warning for a marine zone, in effect from start to end."""

    event: str
    zone: str
    start: datetime
    end: datetime
    headline: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Hour:
    """The conditions at a spot for the hour that begins at `start`.

    Wind is the middle value of the forecast models, and `wind_models` keeps
    each model's value in a fixed order. Current is positive on the flood and
    negative on the ebb, and its direction is where the water flows to. Tide
    heights are above the station's chart datum.
    """

    start: datetime
    daylight: bool
    wind: float
    gust: float
    wind_direction: float
    wind_models: tuple[float | None, ...] = ()
    temperature: float | None = None
    rain_chance: float | None = None
    weather_code: int | None = None
    visibility: float | None = None
    cape: float | None = None
    wave_height: float | None = None
    wave_period: float | None = None
    wave_direction: float | None = None
    water_temperature: float | None = None
    tide_height: float | None = None
    tide_rising: bool | None = None
    current: float | None = None
    current_direction: float | None = None
    alerts: tuple[Alert, ...] = ()
