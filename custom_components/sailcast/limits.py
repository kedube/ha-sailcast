"""SailCast's safety limits, in one versioned table.

Each number is where a rating starts. docs/safety-limits.md is generated from
this file by scripts/safety_limits_doc.py, and a test checks that it's
current. Every change to a limit needs a test case, and in the first version
limits only ever get stricter.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum, StrEnum
import re
from types import MappingProxyType
from typing import Final

from .profiles import SizeClass, Skill

VERSION: Final = 1

FOOT: Final = 0.3048  # meters
NAUTICAL_MILE: Final = 1852.0  # meters


class Level(IntEnum):
    """A safety rating, from best to worst."""

    GOOD = 0
    CAUTION = 1
    NOT_RECOMMENDED = 2
    DANGEROUS = 3

    @property
    def key(self) -> str:
        """Return the rating's name in states and translations."""
        return self.name.lower()


@dataclass(frozen=True, slots=True, kw_only=True)
class BoatLimits:
    """Where each rating starts for one boat size, at every skill level.

    For wind and gusts the boat sets caution and dangerous; not recommended
    for sustained wind comes from the sailor's skill. Wave heights are
    significant heights in meters, set in whole feet. The ideal wind is the
    light-air end and the top for an advanced sailor.
    """

    wind: tuple[float, float]
    gust: tuple[float, float]
    wave: tuple[float, float, float]
    ideal_wind: tuple[float, float]
    gusty: float
    small: bool


def _feet(*heights: float) -> tuple[float, float, float]:
    low, middle, high = (height * FOOT for height in heights)
    return low, middle, high


BOAT_LIMITS: Final[Mapping[SizeClass, BoatLimits]] = MappingProxyType(
    {
        SizeClass.DINGHY: BoatLimits(
            wind=(15, 21),
            gust=(20, 25),
            wave=_feet(1, 2, 4),
            ideal_wind=(5, 14),
            gusty=10,
            small=True,
        ),
        SizeClass.SMALL_KEELBOAT: BoatLimits(
            wind=(18, 25),
            gust=(22, 30),
            wave=_feet(2, 4, 6.5),
            ideal_wind=(7, 17),
            gusty=10,
            small=True,
        ),
        SizeClass.CRUISER: BoatLimits(
            wind=(22, 28),
            gust=(28, 34),
            wave=_feet(3, 6, 10),
            ideal_wind=(8, 20),
            gusty=15,
            small=False,
        ),
        SizeClass.LARGE_CRUISER: BoatLimits(
            wind=(25, 34),
            gust=(34, 41),
            wave=_feet(4, 8, 12),
            ideal_wind=(8, 22),
            gusty=15,
            small=False,
        ),
    }
)

# Sustained wind over these is "not recommended". Gusts don't count. Advanced
# sailors have no limit.
SKILL_WIND_LIMITS: Final[Mapping[Skill, float | None]] = MappingProxyType(
    {Skill.BEGINNER: 10, Skill.INTERMEDIATE: 16, Skill.ADVANCED: None}
)

# Wind against current: wind of at least this much (kt), within this many
# degrees of straight against the current, with current (kt) of at least
# these factors times the wave period (s). The period is at least MIN_PERIOD.
AGAINST_CURRENT_WIND: Final = 10.0
AGAINST_CURRENT_ANGLE: Final = 60.0
AGAINST_CURRENT_MODIFIER: Final = 0.25
AGAINST_CURRENT_FLOOR: Final = 0.5
AGAINST_CURRENT_MIN_PERIOD: Final = 3.0

# Offshore wind for dinghies (kt): one level worse, then at least not
# recommended.
OFFSHORE_MODIFIER_WIND: Final = 8.0
OFFSHORE_FLOOR_WIND: Final = 12.0

# Wind chill for dinghies and small keelboats (°C): one level worse at or
# below freezing.
WIND_CHILL: Final = 0.0

# Forecast visibility (nautical miles): caution below the first number, not
# recommended below the second. It never makes an hour dangerous.
VISIBILITY_SMALL: Final = (2.0, 1.0)
VISIBILITY_CRUISER: Final = (1.0, 0.5)
# Visibility measured nearby (nautical miles) below which the hour under way
# is dangerous.
MEASURED_VISIBILITY_SMALL: Final = 0.5
MEASURED_VISIBILITY_CRUISER: Final = 0.25

# Thunderstorms: forecast as WMO weather codes 95 and up. "Possible" means
# CAPE (J/kg) and rain chance (%) of at least these.
THUNDERSTORM_CODE: Final = 95
THUNDERSTORM_CAPE: Final = 1000.0
THUNDERSTORM_RAIN: Final = 40.0


class WarningGroup(StrEnum):
    """Official warnings that share a minimum rating."""

    ADVISORY = "advisory"
    FOG_AND_SPRAY = "fog_and_spray"
    GALE = "gale"
    STORM = "storm"
    WATCH = "watch"


# Event names, matched whatever their capitals. US marine warnings first,
# then the NWS's warnings for lakes without a marine zone, then Canada's
# marine warnings, which share names with some US ones. A watch is any other
# event ending in "watch" that's about wind, storms or the sea, so a flood or
# fire weather watch on a lake doesn't count.
WARNING_EVENTS: Final[Mapping[str, WarningGroup]] = MappingProxyType(
    {
        "Small Craft Advisory": WarningGroup.ADVISORY,
        "Brisk Wind Advisory": WarningGroup.ADVISORY,
        "Dense Fog Advisory": WarningGroup.FOG_AND_SPRAY,
        "Dense Smoke Advisory": WarningGroup.FOG_AND_SPRAY,
        "Freezing Spray Advisory": WarningGroup.FOG_AND_SPRAY,
        "Gale Warning": WarningGroup.GALE,
        "Hazardous Seas Warning": WarningGroup.GALE,
        "Heavy Freezing Spray Warning": WarningGroup.GALE,
        "Storm Warning": WarningGroup.STORM,
        "Hurricane Force Wind Warning": WarningGroup.STORM,
        "Tropical Storm Warning": WarningGroup.STORM,
        "Hurricane Warning": WarningGroup.STORM,
        "Storm Surge Warning": WarningGroup.STORM,
        "Special Marine Warning": WarningGroup.STORM,
        "Tsunami Warning": WarningGroup.STORM,
        # The NWS on lakes.
        "Lake Wind Advisory": WarningGroup.ADVISORY,
        "Wind Advisory": WarningGroup.ADVISORY,
        "Freezing Fog Advisory": WarningGroup.FOG_AND_SPRAY,
        "High Wind Warning": WarningGroup.GALE,
        "Extreme Wind Warning": WarningGroup.STORM,
        "Severe Thunderstorm Warning": WarningGroup.STORM,
        "Tornado Warning": WarningGroup.STORM,
        "Snow Squall Warning": WarningGroup.STORM,
        # Environment and Climate Change Canada.
        "Strong wind warning": WarningGroup.ADVISORY,
        "Freezing spray warning": WarningGroup.GALE,
        "Squall warning": WarningGroup.STORM,
        "Waterspout warning": WarningGroup.STORM,
    }
)
_EVENT_GROUPS: Final = {
    event.casefold(): group for event, group in WARNING_EVENTS.items()
}
WATCH_WORDS: Final = (
    "wind",
    "gale",
    "storm",
    "squall",
    "tornado",
    "waterspout",
    "hurricane",
    "seas",
    "spray",
    "surge",
    "tsunami",
    "blizzard",
)

# The lowest rating while a warning is in effect, at every skill level.
WARNING_FLOORS: Final[Mapping[WarningGroup, Mapping[SizeClass, Level]]] = (
    MappingProxyType(
        {
            WarningGroup.ADVISORY: {
                SizeClass.DINGHY: Level.NOT_RECOMMENDED,
                SizeClass.SMALL_KEELBOAT: Level.NOT_RECOMMENDED,
                SizeClass.CRUISER: Level.CAUTION,
                SizeClass.LARGE_CRUISER: Level.CAUTION,
            },
            WarningGroup.FOG_AND_SPRAY: {
                SizeClass.DINGHY: Level.NOT_RECOMMENDED,
                SizeClass.SMALL_KEELBOAT: Level.NOT_RECOMMENDED,
                SizeClass.CRUISER: Level.CAUTION,
                SizeClass.LARGE_CRUISER: Level.CAUTION,
            },
            WarningGroup.GALE: {
                SizeClass.DINGHY: Level.DANGEROUS,
                SizeClass.SMALL_KEELBOAT: Level.DANGEROUS,
                SizeClass.CRUISER: Level.DANGEROUS,
                SizeClass.LARGE_CRUISER: Level.NOT_RECOMMENDED,
            },
            WarningGroup.STORM: dict.fromkeys(SizeClass, Level.DANGEROUS),
            WarningGroup.WATCH: dict.fromkeys(SizeClass, Level.CAUTION),
        }
    )
)


# MeteoAlarm's warnings in Europe, by kind and level: "Yellow wind warning".
# Each country sets its own thresholds; yellow wind is around force 6 to 8 at
# sea, so it starts where a Small Craft Advisory does. Other kinds, such as
# rain or heat, don't change the rating.
AWARENESS_GROUPS: Final[Mapping[tuple[str, str], WarningGroup]] = MappingProxyType(
    {
        ("wind", "yellow"): WarningGroup.ADVISORY,
        ("wind", "orange"): WarningGroup.GALE,
        ("wind", "red"): WarningGroup.STORM,
        ("thunderstorm", "yellow"): WarningGroup.ADVISORY,
        ("thunderstorm", "orange"): WarningGroup.STORM,
        ("thunderstorm", "red"): WarningGroup.STORM,
        ("coastal event", "yellow"): WarningGroup.ADVISORY,
        ("coastal event", "orange"): WarningGroup.GALE,
        ("coastal event", "red"): WarningGroup.STORM,
        ("fog", "yellow"): WarningGroup.FOG_AND_SPRAY,
        ("fog", "orange"): WarningGroup.FOG_AND_SPRAY,
        ("fog", "red"): WarningGroup.FOG_AND_SPRAY,
    }
)
_AWARENESS = re.compile(r"^(yellow|orange|red) (.+) warning$")


def warning_group(event: str) -> WarningGroup | None:
    """Return the group an official warning belongs to, if any."""
    name = event.casefold()
    if group := _EVENT_GROUPS.get(name):
        return group
    if match := _AWARENESS.match(name):
        return AWARENESS_GROUPS.get((match.group(2), match.group(1)))
    if name.endswith(" watch") and any(word in name for word in WATCH_WORDS):
        return WarningGroup.WATCH
    return None
