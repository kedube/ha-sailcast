"""Spot, boat and sailor profiles.

Each profile is a subentry of the SailCast entry. The setup dialogs use the
checks here, and the panel's settings will use the same ones, so a profile
saved either way is valid.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Container, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import date
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_RADIUS, WEEKDAYS

from .const import (
    CONF_AHEAD,
    CONF_AIRPORT,
    CONF_AUTO_CALENDAR,
    CONF_AUTO_DAYS,
    CONF_AUTO_SPOTS,
    CONF_BOATS,
    CONF_BUOY,
    CONF_CALENDAR,
    CONF_COLDEST,
    CONF_COMFORT,
    CONF_CURRENT_STATION,
    CONF_DAYS,
    CONF_END,
    CONF_EXPOSED,
    CONF_FETCH,
    CONF_HOURS,
    CONF_IDEAL_HIGH,
    CONF_IDEAL_LOW,
    CONF_LENGTH,
    CONF_LIGHTS,
    CONF_MARINE_ZONE,
    CONF_MIN_SCORE,
    CONF_NOTES,
    CONF_OFFSHORE,
    CONF_RAIN,
    CONF_SENSORS,
    CONF_SIZE_CLASS,
    CONF_SKILL,
    CONF_SOURCE_NAMES,
    CONF_SOURCE_POINTS,
    CONF_SPOTS,
    CONF_START,
    CONF_TIDE_STATION,
    CONF_USER,
    CONF_WATER_TYPE,
    SUBENTRY_BOAT,
    SUBENTRY_SAILOR,
    SUBENTRY_SPOT,
)

MAX_NAME_LENGTH = 40

# The radius sets the wind map's area around a spot, in meters.
DEFAULT_RADIUS = 15_000
MIN_RADIUS = 2_000
MAX_RADIUS = 50_000

# The open water upwind that can be set by hand, in km.
FETCH_RANGE: Final = (0.05, 100.0)

# A spot's notes: local knowledge for the AI, such as when the sea breeze fills.
MAX_NOTES_LENGTH: Final = 500

# The readings a spot can take from your own sensors.
SENSOR_FIELDS: Final = (
    "wind",
    "gust",
    "wind_direction",
    "temperature",
    "water_temperature",
)

# Boat lengths, in meters.
MIN_LENGTH = 1.0
MAX_LENGTH = 50.0


# A sailor's ideal wind, in knots, and the coldest air they enjoy, in °C.
MAX_IDEAL_WIND: Final = 40.0
COLDEST_RANGE: Final = (-20.0, 35.0)

# Automatic calendar adding: the lowest scores a sailor can choose, and how
# far ahead, as the last day counted from today (1 is today and tomorrow).
MIN_SCORES: Final = (60, 80)
AHEAD_DAYS: Final = (1, 2, 4, 6)


class WaterType(StrEnum):
    """The kind of water a spot is on."""

    OPEN_COAST = "open_coast"
    BAY = "bay"
    RIVER = "river"
    LAKE = "lake"


class SizeClass(StrEnum):
    """Boat sizes. Each has its own safety limits."""

    DINGHY = "dinghy"
    SMALL_KEELBOAT = "small_keelboat"
    CRUISER = "cruiser"
    LARGE_CRUISER = "large_cruiser"


class Skill(StrEnum):
    """Skill levels. Each sets the sailor's limit for sustained wind."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class RainTolerance(StrEnum):
    """How much a chance of rain lowers a sailor's scores."""

    AVOID = "avoid"
    SOME = "some"
    ANY = "any"


@dataclass(frozen=True, slots=True, kw_only=True)
class Spot:
    """A place to sail, and where its tides, currents, warnings and readings come from.

    The current station includes its depth bin, as in "PCT0056_1". The
    sources' names are kept when they're chosen, by source, and so are the
    buoy's and airport's positions, for the forecast there. `sensors` maps
    readings such as "wind" to your own sensors. `fetch`, the open water
    upwind in km, is set by hand only to override the shoreline. `notes` are
    the sailors' local knowledge, which only the AI reads.
    """

    id: str
    name: str
    latitude: float
    longitude: float
    radius: float
    water_type: WaterType
    offshore: tuple[str, ...] = ()
    exposed: tuple[str, ...] = ()
    tide_station: str | None = None
    current_station: str | None = None
    marine_zone: str | None = None
    buoy: str | None = None
    airport: str | None = None
    sensors: Mapping[str, str] = field(default_factory=dict, hash=False)
    fetch: float | None = None
    source_names: Mapping[str, str] = field(default_factory=dict, hash=False)
    source_points: Mapping[str, tuple[float, float]] = field(
        default_factory=dict, hash=False
    )
    notes: str = ""

    @property
    def open_water(self) -> bool:
        """Return whether the ocean wave model applies here."""
        return self.water_type in (WaterType.OPEN_COAST, WaterType.BAY)

    @classmethod
    def from_subentry(cls, subentry: ConfigSubentry) -> Spot:
        """Read a spot from its subentry."""
        data = subentry.data
        return cls(
            id=subentry.subentry_id,
            name=subentry.title,
            latitude=data[CONF_LATITUDE],
            longitude=data[CONF_LONGITUDE],
            radius=data[CONF_RADIUS],
            water_type=WaterType(data[CONF_WATER_TYPE]),
            offshore=tuple(data.get(CONF_OFFSHORE, ())),
            exposed=tuple(data.get(CONF_EXPOSED, ())),
            tide_station=data.get(CONF_TIDE_STATION),
            current_station=data.get(CONF_CURRENT_STATION),
            marine_zone=data.get(CONF_MARINE_ZONE),
            buoy=data.get(CONF_BUOY),
            airport=data.get(CONF_AIRPORT),
            sensors=dict(data.get(CONF_SENSORS) or {}),
            fetch=data.get(CONF_FETCH),
            source_names=dict(data.get(CONF_SOURCE_NAMES) or {}),
            source_points={
                key: (float(point[0]), float(point[1]))
                for key, point in (data.get(CONF_SOURCE_POINTS) or {}).items()
            },
            notes=data.get(CONF_NOTES) or "",
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Boat:
    """A boat. Its length is in meters.

    A boat with navigation lights can sail after dark, so every hour counts
    for it, not only daylight hours.
    """

    id: str
    name: str
    size_class: SizeClass
    length: float
    lights: bool = False

    @classmethod
    def from_subentry(cls, subentry: ConfigSubentry) -> Boat:
        """Read a boat from its subentry. Older boats have no lights."""
        return cls(
            id=subentry.subentry_id,
            name=subentry.title,
            size_class=SizeClass(subentry.data[CONF_SIZE_CLASS]),
            length=subentry.data[CONF_LENGTH],
            lights=subentry.data.get(CONF_LIGHTS, False),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Comfort:
    """What a sailor enjoys. It changes their scores, never a safety rating.

    The ideal wind (kt) can only narrow the range their boat and skill allow.
    Cold lowers scores below `coldest` (°C), or 10 °C if it isn't set.
    """

    ideal_low: float | None = None
    ideal_high: float | None = None
    coldest: float | None = None
    rain: RainTolerance = RainTolerance.SOME

    @classmethod
    def from_data(cls, data: Mapping[str, Any] | None) -> Comfort:
        """Read comfort settings, which older sailors don't have."""
        data = data or {}
        return cls(
            ideal_low=data.get(CONF_IDEAL_LOW),
            ideal_high=data.get(CONF_IDEAL_HIGH),
            coldest=data.get(CONF_COLDEST),
            rain=RainTolerance(data.get(CONF_RAIN, RainTolerance.SOME)),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class AutoCalendar:
    """Automatic adding: each chosen day's best window goes into a calendar.

    `ahead` is the last day to add, counted from today, and `min_score` the
    lowest window score. Spots that have been removed are left out.
    """

    calendar: str
    days: tuple[str, ...]
    min_score: int
    ahead: int
    spots: tuple[str, ...]

    @classmethod
    def from_data(
        cls, data: Mapping[str, Any] | None, spots: Container[str]
    ) -> AutoCalendar | None:
        """Read the settings, or None if automatic adding is off."""
        if not data or not data.get(CONF_CALENDAR):
            return None
        return cls(
            calendar=data[CONF_CALENDAR],
            days=tuple(data[CONF_DAYS]),
            min_score=data[CONF_MIN_SCORE],
            ahead=data[CONF_AHEAD],
            spots=tuple(spot for spot in data[CONF_SPOTS] if spot in spots),
        )


@dataclass(frozen=True, slots=True)
class Hours:
    """When a sailor can sail on a day, from `start` to `end`.

    Both are times of day such as "17:00:00". A missing start or end means
    sunrise or sunset, or midnight in a boat with navigation lights.
    """

    start: str | None = None
    end: str | None = None

    @classmethod
    def from_data(cls, data: Mapping[str, Any] | None) -> Hours:
        """Read the hours, which may have neither time."""
        data = data or {}
        return cls(start=data.get(CONF_START), end=data.get(CONF_END))


@dataclass(frozen=True, slots=True, kw_only=True)
class Sailor:
    """A sailor, with their boats and when they can sail.

    The first boat is their default. `week` has their hours on each day of
    the week they sail, by key such as "sat"; the days left out they don't.
    `user` is the Home Assistant user the panel opens on this sailor for.
    """

    id: str
    name: str
    skill: Skill
    boats: tuple[str, ...]
    week: Mapping[str, Hours] = field(default_factory=dict, hash=False)
    user: str | None = None
    comfort: Comfort = Comfort()
    auto_calendar: AutoCalendar | None = None

    @property
    def days(self) -> tuple[str, ...]:
        """Return the days of the week they sail, Monday first."""
        return tuple(day for day in WEEKDAYS if day in self.week)

    def hours_on(
        self, day: date, changes: Mapping[date, Hours | None] = MappingProxyType({})
    ) -> Hours | None:
        """Return their hours on a date, or None if they don't sail that day.

        A change made for the date comes first, then the weekday's hours.
        """
        if day in changes:
            return changes[day]
        return self.week.get(WEEKDAYS[day.weekday()])

    @classmethod
    def from_subentry(
        cls,
        subentry: ConfigSubentry,
        boats: Container[str],
        spots: Container[str] = (),
    ) -> Sailor:
        """Read a sailor, leaving out boats and spots removed since."""
        data = subentry.data
        return cls(
            id=subentry.subentry_id,
            name=subentry.title,
            skill=Skill(data[CONF_SKILL]),
            boats=tuple(boat for boat in data[CONF_BOATS] if boat in boats),
            week=week_hours(data),
            user=data.get(CONF_USER),
            comfort=Comfort.from_data(data.get(CONF_COMFORT)),
            auto_calendar=AutoCalendar.from_data(data.get(CONF_AUTO_CALENDAR), spots),
        )


def week_hours(data: Mapping[str, Any]) -> dict[str, Hours]:
    """Return a sailor's saved hours on each day they sail, Monday first.

    Sailors saved before each day had hours of its own have one start and
    end, which every day they sail gets.
    """
    days = in_order(data[CONF_DAYS], WEEKDAYS)
    if (hours := data.get(CONF_HOURS)) is None:
        return dict.fromkeys(days, Hours(data.get(CONF_START), data.get(CONF_END)))
    return {day: Hours.from_data(hours.get(day)) for day in days}


@dataclass(frozen=True, slots=True)
class Profiles:
    """Every spot, boat and sailor in the SailCast entry, by subentry ID."""

    spots: dict[str, Spot]
    boats: dict[str, Boat]
    sailors: dict[str, Sailor]

    @classmethod
    def from_entry(cls, entry: ConfigEntry) -> Profiles:
        """Read the profiles from the entry's subentries."""
        by_type: defaultdict[str, list[ConfigSubentry]] = defaultdict(list)
        for subentry in entry.subentries.values():
            by_type[subentry.subentry_type].append(subentry)
        boats = {
            subentry.subentry_id: Boat.from_subentry(subentry)
            for subentry in by_type[SUBENTRY_BOAT]
        }
        spots = {
            subentry.subentry_id: Spot.from_subentry(subentry)
            for subentry in by_type[SUBENTRY_SPOT]
        }
        return cls(
            spots=spots,
            boats=boats,
            sailors={
                subentry.subentry_id: Sailor.from_subentry(subentry, boats, spots)
                for subentry in by_type[SUBENTRY_SAILOR]
            },
        )

    def as_dict(self) -> dict[str, list[dict[str, Any]]]:
        """Return the profiles as lists sorted by name, for the panel."""
        return {
            "spots": _sorted_dicts(self.spots.values()),
            "boats": _sorted_dicts(self.boats.values()),
            "sailors": _sorted_dicts(self.sailors.values()),
        }


def _sorted_dicts(profiles: Iterable[Spot | Boat | Sailor]) -> list[dict[str, Any]]:
    return [
        asdict(profile)
        for profile in sorted(profiles, key=lambda profile: profile.name.casefold())
    ]


def in_order(values: Iterable[str], order: Iterable[str]) -> list[str]:
    """Return the chosen values in a fixed order, such as Monday to Sunday."""
    chosen = set(values)
    return [value for value in order if value in chosen]


def check_name(name: str, taken: Iterable[str]) -> str | None:
    """Return an error if the name is empty, too long or already used."""
    name = name.strip()
    if not name:
        return "name_required"
    if len(name) > MAX_NAME_LENGTH:
        return "name_too_long"
    if name.casefold() in {other.casefold() for other in taken}:
        return "name_taken"
    return None


def check_spot(data: Mapping[str, Any]) -> dict[str, str]:
    """Return errors in a spot's data, by field."""
    errors = {}
    if not MIN_RADIUS <= data[CONF_RADIUS] <= MAX_RADIUS:
        errors[CONF_RADIUS] = "radius_out_of_range"
    fetch = data.get(CONF_FETCH)
    if fetch is not None and not FETCH_RANGE[0] <= fetch <= FETCH_RANGE[1]:
        errors[CONF_FETCH] = "fetch_out_of_range"
    if len(data.get(CONF_NOTES) or "") > MAX_NOTES_LENGTH:
        errors[CONF_NOTES] = "notes_too_long"
    sensors = data.get(CONF_SENSORS) or {}
    if any(
        key not in SENSOR_FIELDS or not str(entity_id).startswith("sensor.")
        for key, entity_id in sensors.items()
    ):
        errors[CONF_SENSORS] = "invalid_sensor"
    return errors


def check_boat(data: Mapping[str, Any]) -> dict[str, str]:
    """Return errors in a boat's data, by field."""
    if not MIN_LENGTH <= data[CONF_LENGTH] <= MAX_LENGTH:
        return {CONF_LENGTH: "length_out_of_range"}
    return {}


def check_sailor(
    data: Mapping[str, Any], boats: Container[str], spots: Container[str] = ()
) -> dict[str, str]:
    """Return errors in a sailor's data, by field."""
    errors = {}
    if not data[CONF_BOATS] or any(boat not in boats for boat in data[CONF_BOATS]):
        errors[CONF_BOATS] = "unknown_boat"
    if not data[CONF_DAYS]:
        errors[CONF_DAYS] = "no_days"
    errors.update(check_hours(data.get(CONF_HOURS) or {}))
    errors.update(check_comfort(data.get(CONF_COMFORT) or {}))
    errors.update(check_auto_calendar(data.get(CONF_AUTO_CALENDAR), spots))
    return errors


def check_hours(hours: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    """Return errors in each day's hours, under the day's end, such as mon_end."""
    errors = {}
    for day, times in hours.items():
        start, end = times.get(CONF_START), times.get(CONF_END)
        if start and end and start >= end:
            errors[f"{day}_{CONF_END}"] = "end_before_start"
    return errors


def check_comfort(comfort: Mapping[str, Any]) -> dict[str, str]:
    """Return errors in a sailor's comfort settings, by field."""
    errors = {}
    low, high = comfort.get(CONF_IDEAL_LOW), comfort.get(CONF_IDEAL_HIGH)
    for key, value in ((CONF_IDEAL_LOW, low), (CONF_IDEAL_HIGH, high)):
        if value is not None and not 0 <= value <= MAX_IDEAL_WIND:
            errors[key] = "ideal_out_of_range"
    if low is not None and high is not None and low >= high and not errors:
        errors[CONF_IDEAL_HIGH] = "ideal_high_below_low"
    coldest = comfort.get(CONF_COLDEST)
    if coldest is not None and not COLDEST_RANGE[0] <= coldest <= COLDEST_RANGE[1]:
        errors[CONF_COLDEST] = "coldest_out_of_range"
    return errors


def check_auto_calendar(
    auto: Mapping[str, Any] | None, spots: Container[str]
) -> dict[str, str]:
    """Return errors in automatic adding, which is off without a calendar.

    Days and spots are reported as auto_days and auto_spots, apart from the
    sailor's own days.
    """
    if not auto or not auto.get(CONF_CALENDAR):
        return {}
    errors = {}
    if not auto.get(CONF_DAYS):
        errors[CONF_AUTO_DAYS] = "no_days"
    if not auto.get(CONF_SPOTS) or any(spot not in spots for spot in auto[CONF_SPOTS]):
        errors[CONF_AUTO_SPOTS] = "no_spots"
    if auto.get(CONF_MIN_SCORE) not in MIN_SCORES:
        errors[CONF_MIN_SCORE] = "invalid_min_score"
    if auto.get(CONF_AHEAD) not in AHEAD_DAYS:
        errors[CONF_AHEAD] = "invalid_ahead"
    return errors
