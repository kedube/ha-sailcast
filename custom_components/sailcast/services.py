"""The sailcast.get_forecast action.

It returns a sailor's ratings, scores and windows at a spot for templates and
scripts: each day and each hour from now, in each of the sailor's boats, with
every boat size rated at their skill. Wind and current are in knots; heights
and temperatures follow Home Assistant's unit system.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Final

from homeassistant.const import UnitOfLength, UnitOfTemperature
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import DistanceConverter, TemperatureConverter
import probatio

from .const import DOMAIN
from .coordinator import SailCastConfigEntry
from .outlook import BoatOutlook, Outlook, SpotConditions
from .profiles import Boat, Sailor, SizeClass, Spot
from .scoring import Window, steady_level
from .timeline import HOUR

SERVICE_GET_FORECAST: Final = "get_forecast"
ATTR_SPOT: Final = "spot"
ATTR_SAILOR: Final = "sailor"
ATTR_BOAT: Final = "boat"

GET_FORECAST_SCHEMA: Final = probatio.Schema(
    {
        probatio.Required(ATTR_SPOT): cv.string,
        probatio.Required(ATTR_SAILOR): cv.string,
        probatio.Optional(ATTR_BOAT): cv.string,
    }
)


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register SailCast's actions."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_FORECAST,
        _async_get_forecast,
        schema=GET_FORECAST_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )


async def _async_get_forecast(call: ServiceCall) -> ServiceResponse:
    entries: list[SailCastConfigEntry] = call.hass.config_entries.async_loaded_entries(
        DOMAIN
    )
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="not_loaded"
        )
    data = entries[0].runtime_data
    spot: Spot = _find(data.profiles.spots.values(), call.data[ATTR_SPOT], ATTR_SPOT)
    sailor: Sailor = _find(
        data.profiles.sailors.values(), call.data[ATTR_SAILOR], ATTR_SAILOR
    )
    results = data.results.data
    outlook = results.outlook(sailor.id, spot.id)
    conditions = results.conditions.get(spot.id)
    if outlook is None or conditions is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_forecast",
            translation_placeholders={"spot": spot.name},
        )
    boats = outlook.boats
    if ATTR_BOAT in call.data:
        boat: Boat = _find(
            (item.boat for item in boats), call.data[ATTR_BOAT], ATTR_BOAT, sailor
        )
        boats = tuple(item for item in boats if item.boat.id == boat.id)
    return _response(call.hass, outlook, boats, conditions)


def _find[T: (Spot, Sailor, Boat)](
    profiles: Iterable[T], wanted: str, kind: str, sailor: Sailor | None = None
) -> T:
    """Return the profile with a name (any case) or ID."""
    for profile in profiles:
        if wanted.casefold() in (profile.name.casefold(), profile.id.casefold()):
            return profile
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=f"unknown_{kind}",
        translation_placeholders={
            kind: wanted,
            "sailor": sailor.name if sailor else "",
        },
    )


def _response(
    hass: HomeAssistant,
    outlook: Outlook,
    boats: tuple[BoatOutlook, ...],
    conditions: SpotConditions,
) -> dict[str, Any]:
    us = hass.config.units.length_unit == UnitOfLength.MILES
    height_unit = UnitOfLength.FEET if us else UnitOfLength.METERS
    temperature_unit = hass.config.units.temperature_unit

    def height(value: float | None) -> float | None:
        if value is None:
            return None
        meters = DistanceConverter.convert(value, UnitOfLength.METERS, height_unit)
        return round(meters, 2)

    def temperature(value: float | None) -> float | None:
        if value is None:
            return None
        return round(
            TemperatureConverter.convert(
                value, UnitOfTemperature.CELSIUS, temperature_unit
            ),
            1,
        )

    now = dt_util.utcnow()
    hours = []
    for index, hour in enumerate(conditions.hours):
        if hour.start + HOUR <= now:
            continue
        hours.append(
            {
                "time": hour.start.isoformat(),
                "daylight": hour.daylight,
                "wind": round(hour.wind, 1),
                "gust": round(hour.gust, 1),
                "wind_direction": round(hour.wind_direction),
                "temperature": temperature(hour.temperature),
                "rain_chance": hour.rain_chance,
                "wave_height": height(hour.wave_height),
                "water_temperature": temperature(hour.water_temperature),
                "tide_height": height(hour.tide_height),
                # Adding 0.0 turns a rounded -0.0 at slack water into 0.0.
                "current": None
                if hour.current is None
                else round(hour.current, 2) + 0.0,
                "warnings": [alert.event for alert in hour.alerts],
                "ratings": {
                    size.value: outlook.sizes[size][index].level.key
                    for size in SizeClass
                },
                "boats": [
                    {
                        "boat": boat.boat.name,
                        "rating": boat.hours[index].rating.level.key,
                        "score": boat.hours[index].score,
                        "available": boat.hours[index].available,
                        "reasons": [
                            reason.key for reason in boat.hours[index].rating.reasons
                        ],
                    }
                    for boat in boats
                ],
            }
        )
    zone = dt_util.get_default_time_zone()
    days = []
    for day_index, day in enumerate(conditions.days):
        daytime = [
            index
            for index, hour in enumerate(conditions.hours)
            if hour.daylight and hour.start.astimezone(zone).date() == day.date
        ]
        ratings: dict[str, dict[str, str]] = {}
        if daytime:
            for size in SizeClass:
                levels = [outlook.sizes[size][index].level for index in daytime]
                ratings[size.value] = {
                    "best": steady_level(levels).key,
                    "worst": max(levels).key,
                }
        first = boats[0].days[day_index] if boats else None
        days.append(
            {
                "date": day.date.isoformat(),
                "sunrise": day.sunrise.isoformat(),
                "sunset": day.sunset.isoformat(),
                "confidence": first.confidence if first else None,
                "model_spread": round(first.spread, 1)
                if first and first.spread is not None
                else None,
                "ratings": ratings,
                "boats": [
                    {
                        "boat": boat.boat.name,
                        "score": boat.days[day_index].score,
                        "best_window": _window(boat.days[day_index].best),
                        "windows": [
                            _window(window) for window in boat.days[day_index].windows
                        ],
                    }
                    for boat in boats
                ],
            }
        )
    return {
        "spot": outlook.spot.name,
        "sailor": outlook.sailor.name,
        "skill": outlook.sailor.skill.value,
        "units": {
            "wind": "kn",
            "current": "kn",
            "wave_height": height_unit,
            "tide_height": height_unit,
            "temperature": temperature_unit,
        },
        "days": days,
        "hours": hours,
    }


def _window(window: Window | None) -> dict[str, Any] | None:
    if window is None:
        return None
    return {
        "start": window.start.isoformat(),
        "end": window.end.isoformat(),
        "score": window.score,
    }
