"""Constants for SailCast."""

from typing import Final

DOMAIN: Final = "sailcast"
NAME: Final = "SailCast"

SUBENTRY_SPOT: Final = "spot"
SUBENTRY_BOAT: Final = "boat"
SUBENTRY_SAILOR: Final = "sailor"

CONF_AHEAD: Final = "ahead"
CONF_AUTO_CALENDAR: Final = "auto_calendar"
# Automatic adding's days and spots, where the form also has a sailor's days.
CONF_AUTO_DAYS: Final = "auto_days"
CONF_AUTO_SPOTS: Final = "auto_spots"
CONF_BOATS: Final = "boats"
CONF_CALENDAR: Final = "calendar"
CONF_COLDEST: Final = "coldest"
CONF_COMFORT: Final = "comfort"
CONF_CURRENT_STATION: Final = "current_station"
CONF_DAYS: Final = "days"
CONF_DEFAULT_BOAT: Final = "default_boat"
CONF_END: Final = "end"
CONF_EXPOSED: Final = "exposed"
CONF_IDEAL_HIGH: Final = "ideal_high"
CONF_IDEAL_LOW: Final = "ideal_low"
CONF_LENGTH: Final = "length"
CONF_MARINE_ZONE: Final = "marine_zone"
CONF_MIN_SCORE: Final = "min_score"
CONF_OFFSHORE: Final = "offshore"
CONF_OTHER_BOATS: Final = "other_boats"
CONF_RAIN: Final = "rain"
CONF_SIZE_CLASS: Final = "size_class"
CONF_SKILL: Final = "skill"
CONF_SOURCE_NAMES: Final = "source_names"
CONF_SPOTS: Final = "spots"
CONF_START: Final = "start"
CONF_TIDE_STATION: Final = "tide_station"
CONF_USER: Final = "user"
CONF_WATER_TYPE: Final = "water_type"

# Sent whenever the results, planned sails or profiles change, so open panels
# can ask for the forecast again.
SIGNAL_UPDATED: Final = f"{DOMAIN}_updated"
