"""Where a spot's official warnings come from, and fetching them.

A spot's warnings come from one source, kept in its `marine_zone`:

- an NWS marine zone's ID, with no prefix, such as "PZZ740"
- "nws": the NWS's alerts for the pin itself, for lakes with no marine zone
- "eccc:<area>" or "eccc:<area>/<part>": a Canadian marine area, or one
  part of it where it's split
- "meteoalarm": MeteoAlarm's warnings for the pin, in Europe

Alerts are kept under the source, or for "nws" and "meteoalarm", under the
pin, so a whole area's source also takes the warnings for each of its parts.
"""

from __future__ import annotations

from collections.abc import Awaitable, Collection, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import tzinfo
from typing import TYPE_CHECKING, Final

import aiohttp

from .providers import ProviderError, eccc, meteoalarm, nws
from .timeline import Alert

if TYPE_CHECKING:
    from .profiles import Spot

# The NWS, by marine zone or, as a source of its own, at the pin.
NWS: Final = "nws"
ECCC: Final = eccc.PREFIX
METEOALARM: Final = meteoalarm.PREFIX
AT_PIN: Final = (NWS, METEOALARM)


@dataclass
class Fetched:
    """The alerts fetched for some keys, and the keys whose fetch failed."""

    alerts: list[Alert] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def provider(source: str) -> str:
    """Return who provides a warning source or key: "nws", "eccc" or "meteoalarm"."""
    name, sep, _ = source.partition(":")
    if sep:
        return name
    # A source at the pin is named for its provider; anything else is a zone.
    return source if source in AT_PIN else NWS


def key(spot: Spot) -> str | None:
    """Return the key a spot's warnings are kept under, if it has a source."""
    source = spot.marine_zone
    if source in AT_PIN:
        return f"{source}:{spot.latitude:.4f},{spot.longitude:.4f}"
    return source


def pin(kept: str) -> tuple[float, float]:
    """Return the pin a key for alerts at a pin holds."""
    latitude, longitude = (float(part) for part in kept.partition(":")[2].split(","))
    return latitude, longitude


def applies(alert: Alert, kept: str) -> bool:
    """Return whether an alert is for a key, or one of the key's parts."""
    return alert.zone == kept or alert.zone.startswith(f"{kept}/")


async def async_fetch(
    session: aiohttp.ClientSession,
    keys: Collection[str],
    zone: tzinfo,
    places: Mapping[str, meteoalarm.Place],
    details: dict[str, meteoalarm.Details],
) -> Fetched:
    """Return the alerts for every key: one request per zone list, pin, area or country.

    `places` are the regions and countries near each MeteoAlarm pin, and
    `details` the text of MeteoAlarm's warnings, kept between fetches. A
    failure is noted for the keys it affects, and the rest go on.
    """
    fetched = Fetched()
    zones = sorted(k for k in keys if ":" not in k)
    pins = sorted(k for k in keys if provider(k) == NWS and ":" in k)
    areas: dict[str, list[str]] = {}
    countries: dict[str, list[str]] = {}
    for kept in keys:
        if provider(kept) == ECCC:
            area = kept.partition(":")[2].partition("/")[0]
            areas.setdefault(area, []).append(kept)
        elif provider(kept) == METEOALARM:
            if kept not in places:
                fetched.failed[kept] = "MeteoAlarm's regions couldn't be read"
                continue
            for country in places[kept].countries:
                countries.setdefault(country, []).append(kept)

    async def gather(affected: list[str], request: Awaitable[list[Alert]]) -> None:
        try:
            fetched.alerts.extend(await request)
        except ProviderError as err:
            fetched.failed.update(dict.fromkeys(affected, str(err)))

    if zones:
        await gather(zones, nws.async_get_alerts(session, zones))
    for kept in pins:
        await gather([kept], nws.async_get_alerts_at(session, *pin(kept), kept))
    for area, affected in sorted(areas.items()):
        await gather(affected, eccc.async_get_warnings(session, area, zone))
    seen: set[str] = set()
    for country, affected in sorted(countries.items()):
        await gather(
            affected,
            _async_meteoalarm(
                session, country, affected, places=places, details=details, seen=seen
            ),
        )
    for link in set(details) - seen:
        del details[link]
    return fetched


async def _async_meteoalarm(
    session: aiohttp.ClientSession,
    country: str,
    keys: list[str],
    *,
    places: Mapping[str, meteoalarm.Place],
    details: dict[str, meteoalarm.Details],
    seen: set[str],
) -> list[Alert]:
    """Return a country's MeteoAlarm warnings for each pin they're for.

    Each warning's full text is read once, for its sender, description and
    advice. If that fails, the warning still counts, with the country's
    weather service as its sender.
    """
    found = []
    for warning in await meteoalarm.async_get_warnings(session, country):
        for kept in keys:
            if not meteoalarm.applies(warning, places[kept], *pin(kept)):
                continue
            seen.add(warning.link)
            if warning.link not in details:
                with suppress(ProviderError):
                    details[warning.link] = await meteoalarm.async_get_details(
                        session, warning.link
                    )
            text = details.get(warning.link)
            found.append(
                Alert(
                    event=warning.event,
                    zone=kept,
                    start=warning.onset,
                    end=warning.expires,
                    headline=warning.area,
                    issued=warning.sent,
                    issuer=(text and text.sender) or meteoalarm.COUNTRIES[country][1],
                    details=text.text if text else None,
                )
            )
    return found
