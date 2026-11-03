"""Rijkswaterstaat: Dutch tide predictions.

The astronomical tide's high and low waters come from Rijkswaterstaat's
water data service, in centimeters above NAP, the Dutch reference level
close to mean sea level. The service doesn't publish chart datum (LAT), so
heights stay above NAP. Stations come from its catalogue, which has no
search by position, so it's fetched whole (about 2 MB) and kept for a day.
Rijkswaterstaat's water data is in the public domain (CC0).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Final

import aiohttp

from . import ProviderError, Station, TideEvent, Tides, fetch_json

API: Final = "https://ddapi20-waterwebservices.rijkswaterstaat.nl"
CATALOGUE_URL: Final = f"{API}/METADATASERVICES/OphalenCatalogus"
DATA_URL: Final = f"{API}/ONLINEWAARNEMINGENSERVICES/OphalenWaarnemingen"
PREFIX: Final = "rws"
DAYS: Final = 10
DATUM: Final = "NAP"
# The Netherlands' waters, roughly, so other places aren't looked up.
AREA: Final = (50.7, 53.8, 3.0, 7.3)
# The astronomical tide's highs and lows: their heights, and which is which.
EXTREMES: Final = {
    "Compartiment": {"Code": "OW"},
    "Grootheid": {"Code": "WATHTE"},
    "Hoedanigheid": {"Code": "NAP"},
    "Groepering": {"Code": "GETETBRKD2"},
    "ProcesType": "astronomisch",
}
KINDS: Final = {
    "Compartiment": {"Code": "OW"},
    "Grootheid": {"Code": "NVT"},
    "Groepering": {"Code": "GETETBRKD2"},
    "ProcesType": "astronomisch",
}
CATALOGUE: Final = {
    "CatalogusFilter": {
        "Compartimenten": True,
        "Grootheden": True,
        "Groeperingen": True,
        "Hoedanigheden": True,
        "ProcesTypes": True,
    }
}


def covers(latitude: float, longitude: float) -> bool:
    """Return whether a position is near enough the Netherlands to look up stations."""
    south, north, west, east = AREA
    return south <= latitude <= north and west <= longitude <= east


async def async_stations(session: aiohttp.ClientSession) -> list[Station]:
    """Return the stations with tide predictions."""
    return parse_stations(await fetch_json(session, CATALOGUE_URL, body=CATALOGUE))


async def async_get_tides(
    session: aiohttp.ClientSession, code: str, begin: datetime
) -> Tides:
    """Return ten days of high and low waters at a station, from `begin`."""
    period = {
        "Begindatumtijd": _time(begin),
        "Einddatumtijd": _time(begin + timedelta(days=DAYS)),
    }

    async def series(metadata: dict[str, Any]) -> Any:
        return await fetch_json(
            session,
            DATA_URL,
            body={
                "Locatie": {"Code": code},
                "AquoPlusWaarnemingMetadata": {"AquoMetadata": metadata},
                "Periode": period,
            },
        )

    heights = await series(EXTREMES)
    kinds = await series(KINDS)
    return parse_tides(heights, kinds, f"{PREFIX}:{code}")


def parse_stations(payload: Any) -> list[Station]:
    """Read the catalogue's stations that have high and low water predictions."""
    try:
        wanted = {
            item["AquoMetadata_MessageID"]
            for item in payload["AquoMetadataLijst"]
            if item.get("ProcesType") == EXTREMES["ProcesType"]
            and all(
                item.get(key, {}).get("Code") == value["Code"]
                for key, value in EXTREMES.items()
                if isinstance(value, dict)
            )
        }
        places = {
            link["Locatie_MessageID"]
            for link in payload["AquoMetadataLocatieLijst"]
            if link["AquoMetaData_MessageID"] in wanted
        }
        return [
            Station(
                id=item["Code"],
                name=item["Naam"],
                latitude=float(item["Lat"]),
                longitude=float(item["Lon"]),
            )
            for item in payload["LocatieLijst"]
            if item["Locatie_MessageID"] in places
        ]
    except (KeyError, TypeError, ValueError) as err:
        raise ProviderError(f"Unexpected Rijkswaterstaat catalogue: {err}") from err


def parse_tides(heights: Any, kinds: Any, station: str) -> Tides:
    """Read high and low waters, in meters above NAP."""
    try:
        high = {
            datetime.fromisoformat(item["Tijdstip"]): item["Meetwaarde"][
                "Waarde_Alfanumeriek"
            ]
            == "hoogwater"
            for item in _measurements(kinds, station)
        }
        events = []
        for item in _measurements(heights, station):
            when = datetime.fromisoformat(item["Tijdstip"])
            if when in high:
                events.append(
                    TideEvent(
                        when.astimezone(UTC),
                        round(float(item["Meetwaarde"]["Waarde_Numeriek"]) / 100, 3),
                        high=high[when],
                    )
                )
    except (KeyError, TypeError, ValueError) as err:
        raise ProviderError(f"Unexpected tides for {station}: {err}") from err
    return Tides(
        station, tuple(sorted(events, key=lambda event: event.time)), datum=DATUM
    )


def _measurements(payload: Any, station: str) -> list[dict[str, Any]]:
    """Return a response's measurements, or raise its error."""
    if not isinstance(payload, dict) or not payload.get("Succesvol"):
        message = payload.get("Foutmelding") if isinstance(payload, dict) else None
        raise ProviderError(
            f"Rijkswaterstaat has no predictions for {station}: {message}"
        )
    return [
        item
        for series in payload["WaarnemingenLijst"]
        for item in series["MetingenLijst"]
    ]


def _time(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000+00:00")
