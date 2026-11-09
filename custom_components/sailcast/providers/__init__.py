"""Data providers. Each turns one service's responses into plain data.

The rating code never sees a provider's format, so adding a country's tide
or warning service doesn't touch it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

import aiohttp

# Weather.gov and aviationweather.gov require a User-Agent that names the app.
USER_AGENT: Final = (
    "SailCast for Home Assistant (https://github.com/kedube/ha-sailcast)"
)
TIMEOUT: Final = 30


class ProviderError(Exception):
    """A provider couldn't get or read its data."""


@dataclass(frozen=True, slots=True)
class Reading:
    """One measured value and when it was measured.

    `from_height` is set on wind and gusts scaled to the 10 m that forecasts
    are for: the height above the water they were measured at, in meters.
    """

    value: float
    time: datetime
    from_height: float | None = None


@dataclass(frozen=True, slots=True)
class Readings:
    """The latest reading of each field at one buoy, airport or set of sensors.

    Fields arrive on their own schedules, so each keeps its own time. Wind is
    in knots and directions in degrees it comes from; everything else is in
    SI units.
    """

    fields: Mapping[str, Reading] = field(default_factory=dict)

    def get(self, key: str) -> Reading | None:
        """Return a field's latest reading, if there is one."""
        return self.fields.get(key)

    @property
    def latest(self) -> datetime | None:
        """Return when the newest reading of any field was measured."""
        return max((reading.time for reading in self.fields.values()), default=None)


@dataclass(frozen=True, slots=True)
class Station:
    """A tide or current station.

    `code` is the number people know a station by, where that isn't its ID.
    """

    id: str
    name: str
    latitude: float
    longitude: float
    code: str | None = None


@dataclass(frozen=True, slots=True)
class TideEvent:
    """A high or low tide, in meters above the predictions' datum."""

    time: datetime
    height: float
    high: bool


@dataclass(frozen=True, slots=True)
class Tides:
    """A source's tide predictions. Some stations have no hourly heights.

    `datum` is what heights are measured from: a chart datum such as "MLLW",
    "CD" or "LAT", or "MSL" for the ocean model's rough curve. `name` is the
    station a provider chose, for sources found by position, and `notice` is
    a credit the provider asks to be shown with its data.
    """

    station: str
    events: tuple[TideEvent, ...]
    hourly: tuple[tuple[datetime, float], ...] = ()
    datum: str = "MLLW"
    name: str | None = None
    notice: str | None = None


def turning_points(hourly: Sequence[tuple[datetime, float]]) -> tuple[TideEvent, ...]:
    """Return the highs and lows of hourly heights.

    Each is placed on the parabola through its hour and the hours either
    side, so its time falls between the hours.
    """
    events = []
    for before, here, after in zip(hourly, hourly[1:], hourly[2:], strict=False):
        rise, fall = here[1] - before[1], after[1] - here[1]
        if (rise > 0 >= fall) or (rise < 0 <= fall):
            curve = before[1] - 2 * here[1] + after[1]
            shift = (before[1] - after[1]) / (2 * curve) if curve else 0.0
            events.append(
                TideEvent(
                    here[0] + (after[0] - here[0]) * shift,
                    here[1] - (before[1] - after[1]) * shift / 4,
                    high=rise > 0,
                )
            )
    return tuple(events)


async def fetch_json(
    session: aiohttp.ClientSession,
    url: str,
    params: Mapping[str, str | int | float] | None = None,
    *,
    headers: Mapping[str, str] | None = None,
    body: Any = None,
) -> Any:
    """Return a URL's JSON, posting `body` as JSON if there is one.

    Any failure raises ProviderError.
    """
    try:
        async with (
            asyncio.timeout(TIMEOUT),
            session.request(
                "GET" if body is None else "POST",
                url,
                params=params,
                json=body,
                headers={"User-Agent": USER_AGENT, **(headers or {})},
            ) as response,
        ):
            if response.status >= 400:
                detail = (await response.text())[:200]
                raise ProviderError(f"{url} returned {response.status}: {detail}")
            return await response.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise ProviderError(f"{url}: {str(err) or type(err).__name__}") from err


async def fetch_bytes(
    session: aiohttp.ClientSession,
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    limit: int | None = None,
    wait: float = TIMEOUT,
) -> bytes:
    """Return a URL's body, or its first `limit` bytes. Failures raise ProviderError.

    A server that ignores a Range header sends the whole file, so the limit
    also stops reading early.
    """
    try:
        async with (
            asyncio.timeout(wait),
            session.get(
                url, headers={"User-Agent": USER_AGENT, **(headers or {})}
            ) as response,
        ):
            if response.status >= 400:
                raise ProviderError(f"{url} returned {response.status}")
            if limit is None:
                return await response.read()
            chunks: list[bytes] = []
            remaining = limit
            while remaining > 0 and (chunk := await response.content.read(remaining)):
                chunks.append(chunk)
                remaining -= len(chunk)
            return b"".join(chunks)
    except (aiohttp.ClientError, TimeoutError) as err:
        raise ProviderError(f"{url}: {str(err) or type(err).__name__}") from err


def from_unix(seconds: float) -> datetime:
    """Return an aware UTC time from Unix seconds."""
    return datetime.fromtimestamp(seconds, UTC)
