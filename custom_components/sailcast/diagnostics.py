"""Diagnostics for an issue report, without showing where anyone sails.

Spot positions, names, stations, sensors and marine zones can each point to a
place, so they're redacted along with people's names, linked users and
calendars. Errors keep their kind, the service's host and the status, but not
the addresses, which can hold a station or a position.
"""

from __future__ import annotations

import re
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .coordinator import Observed, SailCastConfigEntry, stations
from .wind import DATA_WIND

TO_REDACT = {
    "airport",
    "buoy",
    "calendar",
    "current_station",
    "latitude",
    "longitude",
    "marine_zone",
    "name",
    "sensors",
    "source_names",
    "source_points",
    "tide_station",
    "user",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SailCastConfigEntry
) -> dict[str, Any]:
    """Return each source's status, the Open-Meteo calls used and the profiles."""
    data = entry.runtime_data
    results = data.results.data
    observed = data.sources.observations.data or Observed()
    now = dt_util.utcnow()
    return {
        "profiles": async_redact_data(data.profiles.as_dict(), TO_REDACT),
        "sources": {
            source.name: {
                "last_update_success": source.last_update_success,
                "last_exception": safe_error(source.last_exception),
                "update_interval": source.update_interval.total_seconds()
                if source.update_interval
                else None,
            }
            for source in data.sources.all
        },
        "open_meteo_calls_today": round(data.budget.today, 1),
        "planned_sails": len(data.planner.store.planned),
        # Counts and ages only: a grid's corners would show where it is.
        "wind_grids": [
            {
                "points": grid.area.rows * grid.area.cols,
                "spots": len(grid.area.spots),
                "fetched": grid.fetched.isoformat(),
            }
            for grid in (hass.data[DATA_WIND].grids if DATA_WIND in hass.data else [])
        ],
        # By kind only: a station's ID would show where it is.
        "readings": [
            {
                "kind": station.kind,
                "fields": sorted(readings.fields) if readings else [],
                "newest_minutes": (
                    round((now - newest).total_seconds() / 60)
                    if readings and (newest := readings.latest)
                    else None
                ),
                "forecast_there": key in observed.forecasts,
                "failing": key in data.sources.observations.failing,
            }
            for key, station in stations(data.profiles).items()
            for readings in [observed.readings.get(key)]
        ],
        "results": {
            "spots": [
                {
                    "hours": len(conditions.hours),
                    "days": len(conditions.days),
                    "tide_events": len(conditions.tide_events),
                    "warnings": [alert.event for alert in conditions.alerts],
                    "shoreline": (
                        {
                            "on_water": conditions.shoreline.on_water,
                            "measured": conditions.shoreline.measured.isoformat(),
                        }
                        if conditions.shoreline
                        else None
                    ),
                    "nudged": sorted(item.field for item in conditions.adjustments),
                    "wave_sources": sorted(
                        {
                            hour.wave_source
                            for hour in conditions.hours
                            if hour.wave_source
                        }
                    ),
                }
                for conditions in results.conditions.values()
            ],
            "outlooks": len(results.outlooks),
        },
    }


def safe_error(error: BaseException | None) -> str | None:
    """Return an error's kind and message, with addresses cut to their host.

    Numbers with several decimals, which could be a position, are hidden too.
    """
    if error is None:
        return None
    text = re.sub(r"https?://([^/\s?:]+)\S*", r"\1", str(error))
    text = re.sub(r"-?\d+\.\d{3,}", "…", text)
    return f"{type(error).__name__}: {text}"[:300]
