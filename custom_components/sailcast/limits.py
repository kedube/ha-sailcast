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


# NWS event names. Other countries' warnings map to the closest group as
# they're added. Any other event ending in "Watch" is a watch.
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
    }
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


def warning_group(event: str) -> WarningGroup | None:
    """Return the group an official warning belongs to, if any."""
    if group := WARNING_EVENTS.get(event):
        return group
    if event.endswith(" Watch"):
        return WarningGroup.WATCH
    return None
