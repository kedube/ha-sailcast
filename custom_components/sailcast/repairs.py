"""Repair issues: what only you can fix, in Settings → System → Repairs.

SailCast raises an issue when a spot's pin is on land, when a buoy, airport or
one of your sensors has sent nothing for half a day, when a tide or current
station has failed for a day, and when Open-Meteo's free daily calls run low.
Each issue clears itself once things are right again.
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import CONF_CURRENT_STATION, CONF_TIDE_STATION, DOMAIN
from .coordinator import SLOW_DOWN_AT, Observed, stations
from .providers import Readings

if TYPE_CHECKING:
    from .coordinator import SailCastData
    from .profiles import Spot

# A source that's sent nothing for this long has gone quiet.
QUIET: Final = timedelta(hours=12)
# Tide and current predictions are fetched daily, so a day of failures counts.
FAILING: Final = timedelta(days=1)


type Issues = dict[str, tuple[str, dict[str, str]]]


@callback
def async_update_issues(hass: HomeAssistant, data: SailCastData, now: datetime) -> None:
    """Raise the issues that apply now, and clear the rest."""
    wanted: Issues = {}
    _pins_on_land(data, wanted)
    _quiet_stations(data, now, wanted)
    _failing_predictions(data, now, wanted)
    _quiet_sensors(hass, data, now, wanted)
    if data.budget.today >= SLOW_DOWN_AT:
        wanted["budget_low"] = ("budget_low", {"calls": f"{data.budget.today:,.0f}"})
    for issue_id, (key, placeholders) in wanted.items():
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=key,
            translation_placeholders=placeholders,
        )
    async_clear_issues(hass, keep=wanted.keys())


def _pins_on_land(data: SailCastData, wanted: Issues) -> None:
    for spot in data.profiles.spots.values():
        shoreline = data.sources.shoreline(spot)
        if shoreline is not None and not shoreline.on_water:
            wanted[f"pin_on_land_{spot.id}"] = ("pin_on_land", {"spot": spot.name})


def _quiet_stations(data: SailCastData, now: datetime, wanted: Issues) -> None:
    observations = data.sources.observations
    observed = observations.data or Observed()
    spots = list(data.profiles.spots.values())
    for key, station in stations(data.profiles).items():
        latest = (observed.readings.get(key) or Readings()).latest
        if now - (latest or observations.started) < QUIET:
            continue
        users = [spot for spot in spots if getattr(spot, station.kind) == station.id]
        wanted[f"quiet_{station.kind}_{station.id}"] = (
            f"quiet_{station.kind}",
            {
                "station": _label(users, station.kind, station.id),
                "spots": _names(users),
            },
        )


def _failing_predictions(data: SailCastData, now: datetime, wanted: Issues) -> None:
    spots = list(data.profiles.spots.values())
    for key, since in data.sources.predictions.failing.items():
        if now - since < FAILING:
            continue
        kind, _, station_id = key.partition(":")
        conf = CONF_TIDE_STATION if kind == "tide" else CONF_CURRENT_STATION
        users = [spot for spot in spots if getattr(spot, conf) == station_id]
        wanted[f"failing_{kind}_{station_id}"] = (
            f"failing_{kind}",
            {"station": _label(users, conf, station_id), "spots": _names(users)},
        )


def _quiet_sensors(
    hass: HomeAssistant, data: SailCastData, now: datetime, wanted: Issues
) -> None:
    sensors: dict[str, list[Spot]] = {}
    for spot in data.profiles.spots.values():
        for entity_id in spot.sensors.values():
            sensors.setdefault(entity_id, []).append(spot)
    for entity_id, users in sensors.items():
        state = hass.states.get(entity_id)
        if state is None:
            since = data.sources.observations.started
        elif state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            since = state.last_changed
        else:
            since = state.last_reported
        if now - since >= QUIET:
            wanted[f"quiet_sensor_{entity_id}"] = (
                "quiet_sensor",
                {"sensor": entity_id, "spots": _names(users)},
            )


@callback
def async_clear_issues(hass: HomeAssistant, keep: Collection[str] = ()) -> None:
    """Clear SailCast's issues, except those to keep."""
    for domain, issue_id in list(ir.async_get(hass).issues):
        if domain == DOMAIN and issue_id not in keep:
            ir.async_delete_issue(hass, DOMAIN, issue_id)


def _label(users: list[Spot], key: str, station: str) -> str:
    """Return a station's ID with its name, as saved with a spot that uses it."""
    for spot in users:
        if name := spot.source_names.get(key):
            return f"{station} ({name})"
    return station


def _names(users: list[Spot]) -> str:
    return ", ".join(sorted(spot.name for spot in users))
