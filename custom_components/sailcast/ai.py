"""The optional AI summary of a day, through Home Assistant's AI Task.

When it's turned on in SailCast's options, the panel's day view offers a
button that asks the AI provider set up in Home Assistant for two or three
sentences about the day. SailCast sends the day's conditions, its ratings,
windows and warnings and its own advice, in the reader's units, and asks for
the reader's language. The instructions say the summary must never contradict
or soften a rating; the panel shows the ratings beside it, and AI never sets
one. SailCast stores no AI keys.

Summaries are written only when someone asks, never in the background, and
are kept for the day, through settings changes that reload SailCast. One
stays current while the ratings, windows and warnings it describes stay the
same; after that the panel offers a new one.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import json
import re
from typing import Any, Final

from homeassistant.components.ai_task import async_generate_data
from homeassistant.components.ai_task.const import DATA_PREFERENCES
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength, UnitOfTemperature
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from homeassistant.util.hass_dict import HassKey
from homeassistant.util.unit_conversion import DistanceConverter, TemperatureConverter

from .const import CONF_AI_SUMMARY, DOMAIN
from .geo import compass_point
from .limits import SKILL_WIND_LIMITS
from .outlook import BoatOutlook, Outlook

AI_TASK: Final = "ai_task"
# How long a provider gets to answer.
WAIT: Final = 90
# Two or three sentences fit in this many characters, in any language.
LONGEST: Final = 900
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
INSTRUCTIONS: Final = """\
You write the summary at the top of a sailing forecast for one day. Write two \
or three sentences in {language}, as plain text: no Markdown, lists, headings \
or emoji.

The data is SailCast's forecast for {sailor}, sailing a {size} at {spot} on \
{weekday}. Use only this data and don't add anything to it.

- The safety ratings come from SailCast's rules and are final. Never \
contradict or soften them, and never call the conditions safer than rated. If \
any hour is rated caution, not recommended or dangerous, say so, when, and \
the main reason.
- If there are official warnings, name them first.
- Mention the best sailing window, if there is one, and its wind and gusts.
- Don't recommend clothing, wetsuits, drysuits or other gear, and don't give \
navigation advice.
- Use the units given, and write times the way {language} speakers usually do.

The data, as JSON:
{data}"""

_MARKUP: Final = re.compile(r"\*\*|__|`|^#+\s*")
DATA_SUMMARIES: HassKey[Summaries] = HassKey(f"{DOMAIN}_summaries")

type Key = tuple[str, str, str, str, str]
"""A summary's spot, sailor, boat, date and language."""

type Facts = Mapping[str, list[Any]]
"""Each hour's rating, whether it's in a window, and its warnings."""


class BadAnswerError(HomeAssistantError):
    """The AI's answer didn't look like a summary."""


def enabled(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Return whether the AI summary is turned on and AI Task is loaded."""
    return (
        bool(entry.options.get(CONF_AI_SUMMARY)) and AI_TASK in hass.config.components
    )


def problem(hass: HomeAssistant, entity_id: str | None) -> str | None:
    """Return why the AI summary can't work yet, as a form error, or None."""
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


def facts(week: Mapping[str, Any], date: str, now: datetime) -> dict[str, list[Any]]:
    """Return what a day's summary depends on, for its daylight hours to come."""
    day = next((day for day in week["days"] if day["date"] == date), None)
    if day is None:
        return {}
    zone = dt_util.get_default_time_zone()
    windows = [
        (datetime.fromisoformat(window["start"]), datetime.fromisoformat(window["end"]))
        for window in day["windows"]
    ]
    found = {}
    for hour in week["hours"]:
        start = datetime.fromisoformat(hour["time"])
        if (
            not hour["daylight"]
            or start.astimezone(zone).date().isoformat() != date
            or start.timestamp() + 3600 <= now.timestamp()
        ):
            continue
        found[hour["time"]] = [
            hour["rating"],
            any(begin <= start < end for begin, end in windows),
            sorted(hour["warnings"]),
        ]
    return found


def day_data(
    hass: HomeAssistant,
    outlook: Outlook,
    boat: BoatOutlook,
    week: Mapping[str, Any],
    *,
    date: str,
    now: datetime,
) -> dict[str, Any] | None:
    """Return a day's forecast for the AI, in the reader's units and local times."""
    day = next((day for day in week["days"] if day["date"] == date), None)
    if day is None:
        return None
    units = _Units(hass)
    ahead = facts(week, date, now)
    hours = [hour for hour in week["hours"] if hour["time"] in ahead]
    summary = day["summary"] or {}
    size = boat.boat.size_class.value
    rating = day["sizes"].get(size)
    data: dict[str, Any] = {
        "date": date,
        "units": units.names,
        "spot": {"name": outlook.spot.name, "water": outlook.spot.water_type.value},
        "boat": {"name": boat.boat.name, "size": size.replace("_", " ")},
        "sailor": {
            "skill": outlook.sailor.skill.value,
            "wind_limit": SKILL_WIND_LIMITS[outlook.sailor.skill],
        },
        "score": day["score"],
        "confidence": day["confidence"],
        "sunrise": units.clock(day["sunrise"]),
        "sunset": units.clock(day["sunset"]),
        "rating": {
            "most_of_the_day": _level(rating["best"]),
            "worst": _level(rating["worst"]),
            "worst_at": units.clock(rating["worst_at"]),
            "reasons": [units.reason(reason) for reason in rating["reasons"]],
        }
        if rating
        else None,
        "windows": [
            {
                "start": units.clock(window["start"]),
                "end": units.clock(window["end"]),
                "score": window["score"],
                "best": index == day["best"],
            }
            for index, window in enumerate(day["windows"])
        ],
        "conditions": {
            "wind": [summary.get("wind_low"), summary.get("wind_high")],
            "gusts": summary.get("gust"),
            "from": compass_point(summary["direction"]).upper()
            if "direction" in summary
            else None,
            "trend": summary.get("trend"),
            "waves": units.heights(summary.get("waves")),
            "air_temperature": units.temperatures(summary.get("temperature")),
            "water_temperature": units.temperature(summary.get("water_temperature")),
            "rain_chance": summary.get("rain_chance"),
            "visibility": units.visibility(summary.get("visibility")),
        },
        "tides": [
            {
                "time": units.clock(tide["time"]),
                "type": "high" if tide["high"] else "low",
                "height": units.height(tide["height"]),
            }
            for tide in day["tides"]
        ],
        "official_warnings": [
            {
                "event": alert["event"],
                "from": units.when(alert["start"]),
                "until": units.when(alert["end"]),
            }
            for alert in week["alerts"]
            if any(alert["event"] in hour["warnings"] for hour in hours)
        ],
        "advice": [units.advice(item) for item in day["advice"]],
        "hours": [
            {
                "time": units.clock(hour["time"]),
                "rating": _level(hour["rating"]),
                "score": hour["score"],
                "wind": round(hour["wind"]),
                "gusts": round(hour["gust"]),
                "from": compass_point(hour["direction"]).upper(),
                "waves": units.height(hour["wave_height"]),
                "reasons": [units.reason(reason) for reason in hour["reasons"]],
            }
            for hour in hours
        ],
    }
    return data


def instructions(
    data: Mapping[str, Any],
    outlook: Outlook,
    boat: BoatOutlook,
    language: str,
    weekday: str,
) -> str:
    """Return what the AI is asked."""
    return INSTRUCTIONS.format(
        language=LANGUAGES.get(language)
        or LANGUAGES.get(language.split("-", maxsplit=1)[0])
        or f"the language with the code {language}",
        sailor=outlook.sailor.name,
        size=boat.boat.size_class.value.replace("_", " "),
        spot=outlook.spot.name,
        weekday=weekday,
        data=json.dumps(data, ensure_ascii=False, separators=(",", ":")),
    )


def clean(answer: Any) -> str:
    """Return the AI's answer as one paragraph, or raise if it isn't one."""
    if not isinstance(answer, str):
        raise BadAnswerError("The answer wasn't text")
    text = " ".join(_MARKUP.sub("", line).strip() for line in answer.splitlines())
    text = " ".join(text.split()).strip("\"'“”«» ")
    if not text or len(text) > LONGEST:
        raise BadAnswerError("The answer wasn't two or three sentences")
    return text


@dataclass(frozen=True, slots=True)
class Summary:
    """A day's summary, when it was written, and what it was written from."""

    text: str
    made: datetime
    facts: Facts

    def current(self, now_facts: Facts) -> bool:
        """Return whether the hours still to come look as they did."""
        return all(self.facts.get(hour) == found for hour, found in now_facts.items())

    def as_dict(self, now_facts: Facts) -> dict[str, Any]:
        """Return the summary for the panel."""
        return {
            "text": self.text,
            "made": self.made.isoformat(),
            "current": self.current(now_facts),
        }


class Summaries:
    """The day's summaries, written when someone asks and kept for the day."""

    def __init__(self) -> None:
        """Start with none."""
        self._kept: dict[Key, Summary] = {}
        self._locks: dict[Key, asyncio.Lock] = {}

    def get(self, key: Key) -> Summary | None:
        """Return the summary kept for a day, if there is one."""
        return self._kept.get(key)

    async def async_write(
        self,
        hass: HomeAssistant,
        key: Key,
        found: Facts,
        asked: str,
        *,
        entity_id: str | None,
        context: Context | None,
    ) -> Summary:
        """Return a current summary, asking the AI for one if needed."""
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            if (kept := self._kept.get(key)) and kept.current(found):
                return kept
            async with asyncio.timeout(WAIT):
                result = await async_generate_data(
                    hass,
                    task_name="SailCast day summary",
                    entity_id=entity_id,
                    instructions=asked,
                    context=context,
                )
            summary = Summary(clean(result.data), dt_util.utcnow(), found)
            self._forget_before(key[3])
            self._kept[key] = summary
            return summary

    def _forget_before(self, date: str) -> None:
        """Drop summaries of days before this one."""
        for key in [key for key in self._kept if key[3] < date]:
            del self._kept[key]
            self._locks.pop(key, None)


def _level(key: str) -> str:
    return key.replace("_", " ")


class _Units:
    """Values from the timeline's units (knots, meters, °C, UTC) to the reader's."""

    def __init__(self, hass: HomeAssistant) -> None:
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
        if meters is None:
            return None
        if self.feet:
            meters = DistanceConverter.convert(
                meters, UnitOfLength.METERS, UnitOfLength.FEET
            )
        return round(meters, 1)

    def heights(self, pair: list[float] | None) -> list[float | None] | None:
        return [self.height(value) for value in pair] if pair else None

    def temperature(self, celsius: float | None) -> float | None:
        if celsius is None:
            return None
        if self.fahrenheit:
            celsius = TemperatureConverter.convert(
                celsius, UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT
            )
        return round(celsius)

    def temperatures(self, pair: list[float] | None) -> list[float | None] | None:
        return [self.temperature(value) for value in pair] if pair else None

    @staticmethod
    def visibility(meters: float | None) -> float | None:
        return None if meters is None else round(meters / METERS_PER_NAUTICAL_MILE, 1)

    @staticmethod
    def clock(when: str) -> str:
        return f"{dt_util.as_local(datetime.fromisoformat(when)):%H:%M}"

    @staticmethod
    def when(when: str) -> str:
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
