"""Data providers. Each turns one service's responses into plain data.

The rating code never sees a provider's format, so adding a country's tide
or warning service doesn't touch it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
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


def from_unix(seconds: float) -> datetime:
    """Return an aware UTC time from Unix seconds."""
    return datetime.fromtimestamp(seconds, UTC)
