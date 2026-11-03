"""Data providers. Each turns one service's responses into plain data.

The rating code never sees a provider's format, so adding a country's tide
or warning service doesn't touch it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
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
    """One measured value and when it was measured."""

    value: float
    time: datetime


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


async def fetch_json(
    session: aiohttp.ClientSession,
    url: str,
    params: Mapping[str, str | int | float] | None = None,
    *,
    headers: Mapping[str, str] | None = None,
) -> Any:
    """Return a URL's JSON. Any failure raises ProviderError."""
    try:
        async with (
            asyncio.timeout(TIMEOUT),
            session.get(
                url,
                params=params,
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
) -> bytes:
    """Return a URL's body, or its first `limit` bytes. Failures raise ProviderError.

    A server that ignores a Range header sends the whole file, so the limit
    also stops reading early.
    """
    try:
        async with (
            asyncio.timeout(TIMEOUT),
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
