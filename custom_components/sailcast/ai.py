"""What SailCast's AI features share: whether AI is on, and the forecast it reads.

SailCast uses AI in two ways, both optional and both through the AI provider
set up in Home Assistant, so SailCast stores no AI keys:

- The briefing (briefing.py): with the AI option on, the panel asks Home
  Assistant's AI task for a write-up of the sailor's week.
- Ask SailCast (assist.py): tools a conversation agent can use to read the
  forecast, for questions asked through Assist.

Both read the forecast built here: every spot and each of the sailor's boats,
day by day, in the reader's units and local times, as the panel shows it.
AI never sets a rating or a window; those come from SailCast's rules.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from typing import Any, Final

from homeassistant.components.ai_task.const import DATA_PREFERENCES
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import DistanceConverter, TemperatureConverter

from .const import CONF_AI_SUMMARY
from .geo import compass_point
from .limits import SKILL_WIND_LIMITS
from .outlook import BoatOutlook, Outlook, Results
from .profiles import Sailor
from .week import week

AI_TASK: Final = "ai_task"
HOUR: Final = timedelta(hours=1)
METERS_PER_NAUTICAL_MILE: Final = 1852
LANGUAGES: Final = {
    "cs": "Czech",
    "de": "German",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "it": "Italian",
    "nl": "Dutch",
    "pl": "Polish",
    "pt-BR": "Brazilian Portuguese",
    "ru": "Russian",
    "sv": "Swedish",
    "zh-Hans": "Simplified Chinese",
}
# Advice goes with the first days, where the forecast is surest.
ADVICE_DAYS: Final = 3
# Advice that only repeats what the data already says.
PLAIN_ADVICE: Final = frozenset({"day_over", "sunset", "tides", "water", "wind"})

_MARKUP: Final = re.compile(r"\*\*|__|`|^#+\s*")


class BadAnswerError(HomeAssistantError):
    """The AI's answer wasn't what SailCast asked for."""


def enabled(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Return whether the AI briefing is turned on and AI Task is loaded."""
    return (
        bool(entry.options.get(CONF_AI_SUMMARY)) and AI_TASK in hass.config.components
    )


def problem(hass: HomeAssistant, entity_id: str | None) -> str | None:
    """Return why the AI briefing can't work yet, as a form error, or None."""
    if AI_TASK not in hass.config.components:
        return "no_ai_task"
    if entity_id is None and not _preferred(hass):
        return "no_default_ai_task"
    return None


def _preferred(hass: HomeAssistant) -> str | None:
    """Return Home Assistant's default AI task for generating data."""
    if (preferences := hass.data.get(DATA_PREFERENCES)) is None:
        return None
    return preferences.gen_data_entity_id


def language_name(language: str) -> str:
    """Return a language's English name, for asking the AI to write in it."""
    return (
        LANGUAGES.get(language)
        or LANGUAGES.get(language.split("-", maxsplit=1)[0])
        or f"the language with the code {language}"
    )


def clean(answer: Any, longest: int, *, required: bool = True) -> str:
    """Return the AI's text as one paragraph, or raise if it isn't text that fits."""
    if not isinstance(answer, str):
        raise BadAnswerError("The answer wasn't text")
    text = " ".join(_MARKUP.sub("", line).strip() for line in answer.splitlines())
    text = " ".join(text.split()).strip("\"'“”«» ")
    if (required and not text) or len(text) > longest:
        raise BadAnswerError("The answer was empty or too long")
    return text


def level(key: str) -> str:
    """Return a rating's key as words, such as "not recommended"."""
    return key.replace("_", " ")


@dataclass(frozen=True, slots=True)
class BoatWeek:
    """A sailor's week at a spot in one boat, as the panel shows it."""

    outlook: Outlook
    boat: BoatOutlook
    week: dict[str, Any]


def boat_weeks(
    results: Results,
    sailor: Sailor,
    now: datetime,
    *,
    spots: Collection[str] | None = None,
    boats: Collection[str] | None = None,
) -> list[BoatWeek]:
    """Return the sailor's week at each spot in each boat, usual boat first."""
    found: list[BoatWeek] = []
    for spot_id, conditions in results.conditions.items():
        if spots is not None and spot_id not in spots:
            continue
        if (outlook := results.outlook(sailor.id, spot_id)) is None:
            continue
        found.extend(
            BoatWeek(outlook, boat, week(outlook, boat, conditions, now))
            for boat in outlook.boats
            if boats is None or boat.boat.id in boats
        )
    return found


def hours_ahead(item: BoatWeek, date: str, now: datetime) -> list[dict[str, Any]]:
    """Return a day's hours still to come that the boat can sail in."""
    lights = item.boat.boat.lights
    return [
        hour
        for hour in item.week["hours"]
        if (hour["daylight"] or lights)
        and local_date(hour["time"]) == date
        and datetime.fromisoformat(hour["time"]) + HOUR > now
    ]


def local_date(when: str) -> str:
    """Return the local date of a time, as YYYY-MM-DD."""
    return dt_util.as_local(datetime.fromisoformat(when)).date().isoformat()


def week_data(
    hass: HomeAssistant,
    weeks: Sequence[BoatWeek],
    sailor: Sailor,
    now: datetime,
    *,
    dates: Collection[str] | None = None,
    detail: bool = True,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Return the sailor's coming days for the AI, and the windows by their IDs.

    Each day has each spot's conditions and warnings, and for each boat its
    score, its ratings hour by hour as spans, and its windows. Windows get IDs
    the AI can refer to; the second value maps them to SailCast's own window.
    With `detail`, the first days also have tides and SailCast's advice.
    """
    units = Units(hass)
    windows: dict[str, dict[str, Any]] = {}
    days: dict[str, dict[str, Any]] = {}
    spots: dict[str, dict[str, Any]] = {}
    boats: dict[str, dict[str, Any]] = {}
    for item in weeks:
        spot, boat = item.outlook.spot, item.boat.boat
        spots.setdefault(
            spot.id,
            {"name": spot.name, "water": level(spot.water_type.value)}
            | ({"notes": spot.notes} if spot.notes else {}),
        )
        boats.setdefault(
            boat.id,
            {
                "name": boat.name,
                "size": level(boat.size_class.value),
                "navigation_lights": boat.lights,
            },
        )
    by_spot: dict[str, list[BoatWeek]] = {}
    for item in weeks:
        by_spot.setdefault(item.outlook.spot.id, []).append(item)
    for spot_weeks in by_spot.values():
        first = spot_weeks[0]
        for index, base in enumerate(first.week["days"]):
            date = base["date"]
            if dates is not None and date not in dates:
                continue
            soon = index < ADVICE_DAYS and detail
            spot_boats = []
            warned: set[str] = set()
            for item in spot_weeks:
                day = item.week["days"][index]
                hours = hours_ahead(item, date, now)
                if day["over"] or not hours:
                    continue
                warned.update(event for hour in hours for event in hour["warnings"])
                entry: dict[str, Any] = {
                    "boat": item.boat.boat.name,
                    "score": day["score"],
                    "ratings": spans(hours, units),
                }
                if day["windows"]:
                    entry["windows"] = []
                    for window in day["windows"]:
                        number = f"w{len(windows) + 1}"
                        windows[number] = {
                            "spot": item.outlook.spot.id,
                            "boat": item.boat.boat.id,
                            "date": date,
                            "start": window["start"],
                            "end": window["end"],
                            "score": window["score"],
                        }
                        entry["windows"].append(_window(number, window, units))
                if soon:
                    entry["advice"] = [
                        units.advice(advice)
                        for advice in day["advice"]
                        if advice["key"] not in PLAIN_ADVICE
                    ]
                spot_boats.append(entry)
            if not spot_boats:
                continue
            summary = base["summary"] or {}
            spot_day: dict[str, Any] = {
                "spot": first.outlook.spot.name,
                "confidence": base["confidence"],
                **_conditions(summary, units),
                "warnings": [
                    {
                        "event": alert["event"],
                        "from": units.when(alert["start"]),
                        "until": units.when(alert["end"]),
                    }
                    for alert in first.week["alerts"]
                    if alert["event"] in warned
                ],
            }
            if soon and base["tides"]:
                spot_day["tides"] = [
                    {
                        "time": units.clock(tide["time"]),
                        "type": "high" if tide["high"] else "low",
                        "height": units.height(tide["height"]),
                    }
                    for tide in base["tides"]
                ]
            spot_day["boats"] = spot_boats
            days.setdefault(
                date,
                {
                    "date": date,
                    "weekday": f"{datetime.fromisoformat(date):%A}",
                    "sunrise": units.clock(base["sunrise"]),
                    "sunset": units.clock(base["sunset"]),
                    "sailing_hours": _sailing_hours(base["hours"]),
                    "spots": [],
                },
            )["spots"].append(spot_day)
    data = {
        "now": units.when(now.isoformat()),
        "units": units.names,
        "sailor": {
            "name": sailor.name,
            "skill": sailor.skill.value,
            "wind_limit": SKILL_WIND_LIMITS[sailor.skill],
        },
        "boats": list(boats.values()),
        "spots": list(spots.values()),
        "days": [days[date] for date in sorted(days)],
    }
    return data, windows


def day_hours(
    hass: HomeAssistant, weeks: Sequence[BoatWeek], date: str, now: datetime
) -> dict[str, Any] | None:
    """Return one day at one spot hour by hour, for each boat, for the AI.

    `weeks` are one spot's boats. Hours still to come that some boat can sail
    in are listed with the conditions and each boat's rating and score.
    """
    if not weeks:
        return None
    units = Units(hass)
    first = weeks[0]
    index = next(
        (i for i, day in enumerate(first.week["days"]) if day["date"] == date), None
    )
    if index is None:
        return None
    base = first.week["days"][index]
    times: dict[str, dict[str, Any]] = {}
    warned: set[str] = set()
    for item in weeks:
        for hour in hours_ahead(item, date, now):
            row = times.setdefault(
                hour["time"],
                {
                    "time": units.clock(hour["time"]),
                    "wind": round(hour["wind"]),
                    "gusts": round(hour["gust"]),
                    "wind_from": compass_point(hour["direction"]).upper(),
                    "waves": units.height(hour["wave_height"]),
                    "air_temperature": units.temperature(hour["temperature"]),
                    "rain_chance": hour["rain_chance"],
                    "boats": [],
                },
            )
            warned.update(hour["warnings"])
            rating: dict[str, Any] = {
                "boat": item.boat.boat.name,
                "rating": level(hour["rating"]),
                "score": hour["score"],
            }
            if hour["rating"] != "good":
                rating["reasons"] = [units.reason(reason) for reason in hour["reasons"]]
            row["boats"].append(rating)
    return {
        "spot": first.outlook.spot.name,
        "date": date,
        "weekday": f"{datetime.fromisoformat(date):%A}",
        "units": units.names,
        "sunrise": units.clock(base["sunrise"]),
        "sunset": units.clock(base["sunset"]),
        "sailing_hours": _sailing_hours(base["hours"]),
        "windows": [
            {"boat": item.boat.boat.name} | _window(None, window, units)
            for item in weeks
            for window in item.week["days"][index]["windows"]
        ],
        "warnings": [
            {
                "event": alert["event"],
                "from": units.when(alert["start"]),
                "until": units.when(alert["end"]),
            }
            for alert in first.week["alerts"]
            if alert["event"] in warned
        ],
        "tides": [
            {
                "time": units.clock(tide["time"]),
                "type": "high" if tide["high"] else "low",
                "height": units.height(tide["height"]),
            }
            for tide in base["tides"]
        ],
        "hours": [times[time] for time in sorted(times)],
    }


def spans(hours: Sequence[Mapping[str, Any]], units: Units) -> list[dict[str, Any]]:
    """Return hours' ratings as spans of the same rating, with why for the others."""
    found: list[dict[str, Any]] = []
    last_end: datetime | None = None
    for hour in hours:
        start = datetime.fromisoformat(hour["time"])
        rating = level(hour["rating"])
        if not found or found[-1]["rating"] != rating or last_end != start:
            found.append(
                {"from": units.clock(hour["time"]), "to": "", "rating": rating}
            )
        last_end = start + HOUR
        found[-1]["to"] = units.clock(last_end.isoformat())
        if hour["rating"] == "good":
            continue
        reasons = found[-1].setdefault("reasons", [])
        for reason in hour["reasons"]:
            converted = units.reason(reason)
            if all(old["reason"] != converted["reason"] for old in reasons):
                reasons.append(converted)
    return found


def _window(
    number: str | None, window: Mapping[str, Any], units: Units
) -> dict[str, Any]:
    found: dict[str, Any] = {"id": number} if number else {}
    found |= {
        "from": units.clock(window["start"]),
        "to": units.clock(window["end"]),
        "score": window["score"],
    }
    if window["wind_low"] is not None and window["wind_high"] is not None:
        found["wind"] = [round(window["wind_low"]), round(window["wind_high"])]
    if window["gust"] is not None:
        found["gusts"] = round(window["gust"])
    if window["direction"] is not None:
        found["wind_from"] = compass_point(window["direction"]).upper()
    return found


def _conditions(summary: Mapping[str, Any], units: Units) -> dict[str, Any]:
    """Return a day's conditions at a spot, leaving out what isn't known."""
    found = {
        "wind": [round(summary["wind_low"]), round(summary["wind_high"])]
        if "wind_low" in summary
        else None,
        "gusts": round(summary["gust"]) if "gust" in summary else None,
        "wind_from": compass_point(summary["direction"]).upper()
        if "direction" in summary
        else None,
        "trend": summary.get("trend"),
        "waves": units.heights(summary.get("waves")),
        "air_temperature": units.temperatures(summary.get("temperature")),
        "water_temperature": units.temperature(summary.get("water_temperature")),
        "rain_chance": summary.get("rain_chance"),
        "visibility": units.visibility(summary.get("visibility")),
    }
    return {key: value for key, value in found.items() if value is not None}


def _sailing_hours(hours: Mapping[str, Any] | None) -> dict[str, str] | None:
    """Return when the sailor can go that day; a missing end means sunrise or sunset."""
    if hours is None:
        return None
    return {
        key: str(hours[name])[:5]
        for key, name in (("from", "start"), ("to", "end"))
        if hours.get(name)
    }


class Units:
    """Values from the timeline's units (knots, meters, °C, UTC) to the reader's."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Read the units from Home Assistant's unit system."""
        self.feet = hass.config.units.length_unit == UnitOfLength.MILES
        self.fahrenheit = (
            hass.config.units.temperature_unit == UnitOfTemperature.FAHRENHEIT
        )
        self.names = {
            "wind": "kt",
            "height": "ft" if self.feet else "m",
            "temperature": "°F" if self.fahrenheit else "°C",
            "visibility": "nautical miles",
            "rain_chance": "%",
            "times": "local, 24-hour clock",
        }

    def height(self, meters: float | None) -> float | None:
        """Return a height in feet or meters."""
        if meters is None:
            return None
        if self.feet:
            meters = DistanceConverter.convert(
                meters, UnitOfLength.METERS, UnitOfLength.FEET
            )
        return round(meters, 1)

    def heights(self, pair: Sequence[float] | None) -> list[float | None] | None:
        """Return a range of heights in feet or meters."""
        return [self.height(value) for value in pair] if pair else None

    def temperature(self, celsius: float | None) -> float | None:
        """Return a temperature in °F or °C."""
        if celsius is None:
            return None
        if self.fahrenheit:
            celsius = TemperatureConverter.convert(
                celsius, UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT
            )
        return round(celsius)

    def temperatures(self, pair: Sequence[float] | None) -> list[float | None] | None:
        """Return a range of temperatures in °F or °C."""
        return [self.temperature(value) for value in pair] if pair else None

    @staticmethod
    def visibility(meters: float | None) -> float | None:
        """Return a visibility in nautical miles."""
        return None if meters is None else round(meters / METERS_PER_NAUTICAL_MILE, 1)

    @staticmethod
    def clock(when: str) -> str:
        """Return a time as the local time of day, such as 14:00."""
        return f"{dt_util.as_local(datetime.fromisoformat(when)):%H:%M}"

    @staticmethod
    def when(when: str) -> str:
        """Return a time as the local weekday and time, such as Sat 14:00."""
        return f"{dt_util.as_local(datetime.fromisoformat(when)):%a %H:%M}"

    def reason(self, reason: Mapping[str, Any]) -> dict[str, Any]:
        """Return a rating's reason with its values in the reader's units."""
        return {"reason": reason["key"]} | self._values(reason.get("values", {}))

    def advice(self, item: Mapping[str, Any]) -> dict[str, Any]:
        """Return a piece of SailCast's advice with its values in the reader's units."""
        values = dict(item["values"])
        values.pop("events", None)
        if item["key"] == "waves":
            values = {name: self.height(value) for name, value in values.items()}
        return {"advice": item["key"]} | self._values(values)

    def _values(self, values: Mapping[str, Any]) -> dict[str, Any]:
        converted: dict[str, Any] = {}
        for name, value in values.items():
            if name in ("time", "start", "end"):
                converted[name] = self.clock(value)
            elif name == "height":
                converted[name] = self.height(value)
            elif name == "temperature":
                converted[name] = self.temperature(value)
            elif name == "visibility":
                converted[name] = self.visibility(value)
            elif name == "direction":
                converted[name] = compass_point(value).upper()
            elif name == "size":
                converted[name] = str(value).replace("_", " ")
            else:
                converted[name] = round(value, 1) if isinstance(value, float) else value
        return converted
