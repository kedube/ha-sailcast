"""Spot, boat and sailor profiles.

Each profile is a subentry of the SailCast entry. The setup dialogs use the
checks here, and the panel's settings will use the same ones, so a profile
saved either way is valid.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Container, Iterable, Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_RADIUS

from .const import (
    CONF_BOATS,
    CONF_CURRENT_STATION,
    CONF_DAYS,
    CONF_END,
    CONF_EXPOSED,
    CONF_LENGTH,
    CONF_MARINE_ZONE,
    CONF_OFFSHORE,
    CONF_SIZE_CLASS,
    CONF_SKILL,
    CONF_START,
    CONF_TIDE_STATION,
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

# Boat lengths, in meters.
MIN_LENGTH = 1.0
MAX_LENGTH = 50.0

DIRECTIONS = ("n", "ne", "e", "se", "s", "sw", "w", "nw")


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


@dataclass(frozen=True, slots=True, kw_only=True)
class Spot:
    """A place to sail, and where its tides, currents and warnings come from.

    The current station includes its depth bin, as in "PCT0056_1".
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
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Boat:
    """A boat. Its length is in meters."""

    id: str
    name: str
    size_class: SizeClass
    length: float

    @classmethod
    def from_subentry(cls, subentry: ConfigSubentry) -> Boat:
        """Read a boat from its subentry."""
        return cls(
            id=subentry.subentry_id,
            name=subentry.title,
            size_class=SizeClass(subentry.data[CONF_SIZE_CLASS]),
            length=subentry.data[CONF_LENGTH],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Sailor:
    """A sailor, with their boats and when they can sail.

    The first boat is their default. A missing start or end means sunrise or
    sunset.
    """

    id: str
    name: str
    skill: Skill
    boats: tuple[str, ...]
    days: tuple[str, ...]
    start: str | None = None
    end: str | None = None

    @classmethod
    def from_subentry(cls, subentry: ConfigSubentry, boats: Container[str]) -> Sailor:
        """Read a sailor, leaving out boats that have been removed since."""
        data = subentry.data
        return cls(
            id=subentry.subentry_id,
            name=subentry.title,
            skill=Skill(data[CONF_SKILL]),
            boats=tuple(boat for boat in data[CONF_BOATS] if boat in boats),
            days=tuple(data[CONF_DAYS]),
            start=data.get(CONF_START),
            end=data.get(CONF_END),
        )


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
        return cls(
            spots={
                subentry.subentry_id: Spot.from_subentry(subentry)
                for subentry in by_type[SUBENTRY_SPOT]
            },
            boats=boats,
            sailors={
                subentry.subentry_id: Sailor.from_subentry(subentry, boats)
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
    if not MIN_RADIUS <= data[CONF_RADIUS] <= MAX_RADIUS:
        return {CONF_RADIUS: "radius_out_of_range"}
    return {}


def check_boat(data: Mapping[str, Any]) -> dict[str, str]:
    """Return errors in a boat's data, by field."""
    if not MIN_LENGTH <= data[CONF_LENGTH] <= MAX_LENGTH:
        return {CONF_LENGTH: "length_out_of_range"}
    return {}


def check_sailor(data: Mapping[str, Any], boats: Container[str]) -> dict[str, str]:
    """Return errors in a sailor's data, by field."""
    errors = {}
    if not data[CONF_BOATS] or any(boat not in boats for boat in data[CONF_BOATS]):
        errors[CONF_BOATS] = "unknown_boat"
    if not data[CONF_DAYS]:
        errors[CONF_DAYS] = "no_days"
    start, end = data.get(CONF_START), data.get(CONF_END)
    if start and end and start >= end:
        errors[CONF_END] = "end_before_start"
    return errors
