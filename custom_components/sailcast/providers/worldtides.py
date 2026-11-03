"""WorldTides: tide predictions anywhere, with your own API key.

One request gives hourly heights and the highs and lows for two weeks at a
spot's pin, from a tide gauge within reach or WorldTides' global model.
Heights are above chart datum where WorldTides has one. A request costs 3 of
the account's credits, so predictions are kept until they run short.
WorldTides answers a key it refuses, or an account out of credits, with an
error, which SailCast raises as a repair issue.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Final
from urllib.parse import urlencode

import aiohttp
from yarl import URL

from . import USER_AGENT, ProviderError, TideEvent, Tides, from_unix

API: Final = "https://www.worldtides.info/api/v3"
TIMEOUT: Final = 30
DAYS: Final = 14
# How far from the pin a tide gauge is used instead of the model.
GAUGE_KM: Final = 40
DATUM: Final = "CD"
SOURCE: Final = "worldtides"


class KeyRejectedError(ProviderError):
    """WorldTides refused the key, or the account has no credits left."""


async def async_get_tides(
    session: aiohttp.ClientSession,
    key: str,
    latitude: float,
    longitude: float,
    start: datetime,
) -> Tides:
    """Return two weeks of tide predictions at a position, from `start`."""
    params = {
        "lat": f"{latitude:.4f}",
        "lon": f"{longitude:.4f}",
        "start": int(start.timestamp()),
        "length": int(timedelta(days=DAYS).total_seconds()),
        "step": 3600,
        "datum": DATUM,
        "stationDistance": GAUGE_KM,
        "key": key,
    }
    # The outputs are bare flags, as WorldTides documents them.
    url = URL(f"{API}?heights&extremes&{urlencode(params)}", encoded=True)
    try:
        async with (
            asyncio.timeout(TIMEOUT),
            session.get(url, headers={"User-Agent": USER_AGENT}) as response,
        ):
            payload = await response.json(content_type=None)
            status = response.status
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        # Errors are named by host only: the address holds the key.
        raise ProviderError(
            f"WorldTides: {type(err).__name__} from {URL(API).host}"
        ) from None
    return parse_tides(payload, status, source(latitude, longitude))


def source(latitude: float, longitude: float) -> str:
    """Return the ID WorldTides predictions at a pin are kept under."""
    return f"{SOURCE}:{latitude:.4f},{longitude:.4f}"


def parse_tides(payload: Any, status: int, station: str) -> Tides:
    """Read heights and highs and lows, or raise the error WorldTides gave."""
    if not isinstance(payload, dict):
        raise ProviderError(f"WorldTides returned {status} with no JSON")
    if status != 200 or payload.get("status") != 200:
        message = str(payload.get("error") or f"status {status}")
        if status in (400, 401, 403) and _about_the_key(message):
            raise KeyRejectedError(message)
        raise ProviderError(f"WorldTides: {message}")
    try:
        return Tides(
            station=station,
            events=tuple(
                TideEvent(
                    from_unix(item["dt"]), float(item["height"]), item["type"] == "High"
                )
                for item in payload.get("extremes", [])
            ),
            hourly=tuple(
                (from_unix(item["dt"]), float(item["height"]))
                for item in payload.get("heights", [])
            ),
            datum=str(payload.get("responseDatum") or DATUM),
            name=payload.get("station"),
            notice=payload.get("copyright"),
        )
    except (KeyError, TypeError, ValueError) as err:
        raise ProviderError(f"Unexpected WorldTides predictions: {err}") from err


def _about_the_key(message: str) -> bool:
    """Return whether an error is about the key or the account's credits."""
    words = message.casefold()
    return "key" in words or "credit" in words
