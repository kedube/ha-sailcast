"""Diagnostics for an issue report, without showing where anyone sails.

Spot positions, names, stations and marine zones can each point to a place,
so they're redacted along with people's names, linked users and calendars.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .coordinator import SailCastConfigEntry

TO_REDACT = {
    "calendar",
    "current_station",
    "latitude",
    "longitude",
    "marine_zone",
    "name",
    "source_names",
    "tide_station",
    "user",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SailCastConfigEntry
) -> dict[str, Any]:
    """Return each source's status, the Open-Meteo calls used and the profiles."""
    data = entry.runtime_data
    results = data.results.data
    return {
        "profiles": async_redact_data(data.profiles.as_dict(), TO_REDACT),
        "sources": {
            source.name: {
                "last_update_success": source.last_update_success,
                "last_exception": repr(source.last_exception)
                if source.last_exception
                else None,
                "update_interval": source.update_interval.total_seconds()
                if source.update_interval
                else None,
            }
            for source in data.sources.all
        },
        "open_meteo_calls_today": round(data.budget.today, 1),
        "planned_sails": len(data.planner.store.planned),
        "results": {
            "spots": [
                {
                    "hours": len(conditions.hours),
                    "days": len(conditions.days),
                    "tide_events": len(conditions.tide_events),
                    "warnings": [alert.event for alert in conditions.alerts],
                }
                for conditions in results.conditions.values()
            ],
            "outlooks": len(results.outlooks),
        },
    }
