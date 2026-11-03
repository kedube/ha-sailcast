"""The Canadian Hydrographic Service: Canadian tide predictions.

CHS's water level API gives each station's high and low tides and hourly
heights, in meters above chart datum, in UTC. It has no search by position,
so the list of stations with predictions (about 750 KB) is fetched whole
and kept for a day. Highs and lows come without saying which is which, so
each is compared with its neighbors. Great Lakes stations have no
predictions. The limits are 3 requests a second and 30 a minute.

CHS's licence rules out navigation and commercial use, and asks for its
notice to be shown with the data. It doesn't let the data be passed on, so
SailCast's tests use made-up predictions.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Final

import aiohttp

from . import ProviderError, Station, TideEvent, Tides, fetch_json

API: Final = "https://api-iwls.dfo-mpo.gc.ca/api/v1"
PREFIX: Final = "chs"
DAYS: Final = 10
DATUM: Final = "CD"
# Canada's waters, roughly, so other places aren't looked up.
AREA: Final = (41.5, 84.0, -142.0, -52.0)
# The notice CHS's licence asks for, word for word, naming who it's for.
NOTICE: Final = (
    "This product is not to be used for navigation. This product was made by or"
    " for the owner of this Home Assistant and contains intellectual property"
    " (Data) of the Canadian Hydrographic Service of the Department of Fisheries"
    " and Oceans. The copyrights in the Data are and remain the property of His"
    " Majesty the King in Right of Canada and shall not be sold, licensed,"
    " leased, assigned or given to a third party. The incorporation of the Data"
    " in this product does not constitute an endorsement or an approval of this"
    " product by the Canadian Hydrographic Service, the Department of Fisheries"
    " and Oceans or His Majesty the King in Right of Canada"
)


def covers(latitude: float, longitude: float) -> bool:
    """Return whether a position is near enough Canada to look up stations."""
    south, north, west, east = AREA
    return south <= latitude <= north and west <= longitude <= east


async def async_stations(session: aiohttp.ClientSession) -> list[Station]:
    """Return the stations with high and low tide predictions."""
    payload = await fetch_json(
        session, f"{API}/stations", {"time-series-code": "wlp-hilo"}
    )
    return parse_stations(payload)


async def async_get_tides(
    session: aiohttp.ClientSession, station_id: str, begin: datetime
) -> Tides:
    """Return ten days of highs and lows and hourly heights, from `begin`."""
    period = {
        "from": _time(begin),
        "to": _time(begin + timedelta(days=DAYS)),
    }
    url = f"{API}/stations/{station_id}/data"
    extremes = await fetch_json(session, url, {"time-series-code": "wlp-hilo"} | period)
    hourly = await fetch_json(
        session,
        url,
        {"time-series-code": "wlp", "resolution": "SIXTY_MINUTES"} | period,
    )
    return parse_tides(extremes, hourly, f"{PREFIX}:{station_id}")


def parse_stations(payload: Any) -> list[Station]:
    """Read stations, named by their official name and code."""
    try:
        return [
            Station(
                id=item["id"],
                name=item["officialName"],
                latitude=float(item["latitude"]),
                longitude=float(item["longitude"]),
                code=item.get("code"),
            )
            for item in payload
            if any(series.get("code") == "wlp-hilo" for series in item["timeSeries"])
        ]
    except (KeyError, TypeError, ValueError) as err:
        raise ProviderError(f"Unexpected CHS station list: {err}") from err


def parse_tides(extremes: Any, hourly: Any, station: str) -> Tides:
    """Read highs and lows, telling them apart by their neighbors."""
    try:
        points = [
            (_parse_time(item["eventDate"]), float(item["value"])) for item in extremes
        ]
        heights = tuple(
            (_parse_time(item["eventDate"]), float(item["value"])) for item in hourly
        )
    except (KeyError, TypeError, ValueError) as err:
        raise ProviderError(f"Unexpected tides for {station}: {err}") from err
    events = []
    for index, (when, height) in enumerate(points):
        # Above the middle of the tides either side is a high, even where
        # two highs come together.
        neighbors = [
            other
            for _, other in points[max(index - 1, 0) : index]
            + points[index + 1 : index + 2]
        ]
        if neighbors:
            middle = sum(neighbors) / len(neighbors)
            events.append(TideEvent(when, height, high=height > middle))
    return Tides(station, tuple(events), heights, datum=DATUM, notice=NOTICE)


def _time(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)
