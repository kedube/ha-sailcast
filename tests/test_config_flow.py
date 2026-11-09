"""Tests for setting up SailCast and adding spots, boats and sailors."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.sailcast.const import (
    DOMAIN,
    NAME,
    SUBENTRY_BOAT,
    SUBENTRY_SAILOR,
    SUBENTRY_SPOT,
)
from custom_components.sailcast.providers import metar, ndbc, noaa_coops

from .conftest import BAY, HARBOR_POINT

SPOT_INPUT = {
    "name": "Marina",
    "location": {"latitude": 32.68, "longitude": -117.17, "radius": 8000.0},
    "water_type": "bay",
    "offshore": ["w", "e"],
    "exposed": ["s"],
}
SOURCES = {
    "tide_station": "9410170",
    "current_station": "PCT0096_1",
    "marine_zone": "PZZ740",
    "buoy": "SDBC1",
    "airport": "KNZY",
}
# What the forms send for their folded sections when they're left alone.
SECTIONS = {"hours": {}, "comfort": {"rain": "some"}, "auto_calendar": {}}
NO_SENSORS = {"sensors": {}}
# What a sailor saved with the sections left alone has.
NO_EXTRAS = {
    "user": None,
    "comfort": {"ideal_low": None, "ideal_high": None, "coldest": None, "rain": "some"},
    "auto_calendar": None,
}


async def _add(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    subentry_type: str,
    user_input: dict[str, Any],
) -> dict[str, Any]:
    """Run the add form for a profile and return the result."""
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, subentry_type), context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return await hass.config_entries.subentries.async_configure(
        result["flow_id"], user_input
    )


async def _edit(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    subentry_id: str,
    user_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Open the edit form for a profile, and submit it if given input."""
    subentry_type = entry.subentries[subentry_id].subentry_type
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, subentry_type),
        context={"source": SOURCE_RECONFIGURE, "subentry_id": subentry_id},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    if user_input is None:
        return result
    return await hass.config_entries.subentries.async_configure(
        result["flow_id"], user_input
    )


def _suggested(result: dict[str, Any], field: str) -> Any:
    """Return the value a form suggests for a field."""
    for key in result["data_schema"].schema:
        if key == field:
            return key.description["suggested_value"]
    raise KeyError(field)


def _options(result: dict[str, Any], field: str) -> list[dict[str, str]]:
    """Return a select field's options."""
    return result["data_schema"].schema[field].config["options"]


def _only(entry: MockConfigEntry, subentry_type: str) -> Any:
    """Return the one subentry of a type."""
    (subentry,) = (
        subentry
        for subentry in entry.subentries.values()
        if subentry.subentry_type == subentry_type
    )
    return subentry


async def test_setup_creates_one_entry(hass: HomeAssistant) -> None:
    """Setup shows the safety note, creates the entry, and allows only one."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"] == {}

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_new_spot_starts_at_home(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """A new spot's pin starts at the home location."""
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_SPOT), context={"source": SOURCE_USER}
    )
    assert _suggested(result, "location") == {
        "latitude": hass.config.latitude,
        "longitude": hass.config.longitude,
        "radius": 15_000,
    }


async def test_add_spot(
    hass: HomeAssistant, entry: MockConfigEntry, suggestions: AiohttpClientMocker
) -> None:
    """A spot stores its pin, radius, directions in a fixed order, and sources."""
    result = await _add(hass, entry, SUBENTRY_SPOT, SPOT_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "sources"
    assert result["errors"] == {}
    # The nearest of each is suggested.
    assert {key: _suggested(result, key) for key in SOURCES} == SOURCES

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], SOURCES | NO_SENSORS
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    spot = _only(entry, SUBENTRY_SPOT)
    assert spot.title == "Marina"
    assert dict(spot.data) == {
        "latitude": 32.68,
        "longitude": -117.17,
        "radius": 8000.0,
        "water_type": "bay",
        "offshore": ["e", "w"],
        "exposed": ["s"],
        "fetch": None,
        "notes": "",
        **SOURCES,
        # Each source's name is kept, so the panel can show it.
        "source_names": {
            "tide_station": "SAN DIEGO",
            "current_station": "28th St. Pier (San Diego), 0.92 nmi. SW",
            "marine_zone": "Coastal Waters from San Mateo Point to the Mexican "
            "Border and out to 10 nm",
            "buoy": "9410170 - San Diego, CA",
            "airport": "San Diego/North Island NAS",
        },
        # And the buoy's and airport's positions, for the forecast there.
        "source_points": {
            "buoy": [32.714, -117.174],
            "airport": [32.69217, -117.20983],
        },
        "sensors": {},
    }


async def test_sensors_and_fetch(
    hass: HomeAssistant, entry: MockConfigEntry, suggestions: AiohttpClientMocker
) -> None:
    """Your own sensors are kept by reading, and fetch in km whatever the units."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    result = await _add(hass, entry, SUBENTRY_SPOT, SPOT_INPUT | {"fetch": 2})
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        SOURCES
        | {
            "sensors": {
                "wind": "sensor.dock_wind_speed",
                "wind_direction": "sensor.dock_wind_direction",
            }
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    spot = _only(entry, SUBENTRY_SPOT)
    assert spot.data["fetch"] == 3.219
    assert spot.data["sensors"] == {
        "wind": "sensor.dock_wind_speed",
        "wind_direction": "sensor.dock_wind_direction",
    }
    result = await _edit(hass, entry, spot.subentry_id)
    assert _suggested(result, "fetch") == 2.0


async def test_source_choices(
    hass: HomeAssistant, entry: MockConfigEntry, suggestions: AiohttpClientMocker
) -> None:
    """Choices are the nearest first, with None, labeled with their distance."""
    result = await _add(hass, entry, SUBENTRY_SPOT, SPOT_INPUT)
    tides = _options(result, "tide_station")
    assert tides[0] == {"value": "none", "label": "None"}
    assert tides[1] == {"value": "9410170", "label": "SAN DIEGO (9410170), 4.0 km"}
    currents = [option["value"] for option in _options(result, "current_station")]
    # One depth bin per station; weak and variable stations are left out.
    assert currents[:4] == ["none", "PCT0096_1", "PCT0091_1", "PCT0101_1"]
    assert "PCT0076_1" not in currents
    zones = [option["value"] for option in _options(result, "marine_zone")]
    assert zones == ["none", "PZZ740", "PZZ745", "nws"]


async def test_no_sources(
    hass: HomeAssistant, entry: MockConfigEntry, suggestions: AiohttpClientMocker
) -> None:
    """None leaves a source out."""
    result = await _add(hass, entry, SUBENTRY_SPOT, SPOT_INPUT)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], dict.fromkeys(SOURCES, "none") | NO_SENSORS
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    spot = _only(entry, SUBENTRY_SPOT)
    assert {key: spot.data[key] for key in SOURCES} == dict.fromkeys(SOURCES)


async def test_sources_in_miles(
    hass: HomeAssistant, entry: MockConfigEntry, suggestions: AiohttpClientMocker
) -> None:
    """With US units, distances are in miles."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    result = await _add(hass, entry, SUBENTRY_SPOT, SPOT_INPUT)
    assert _options(result, "tide_station")[1]["label"] == "SAN DIEGO (9410170), 2.5 mi"


async def test_sources_unavailable(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """If the lookups fail, the spot can still be saved without sources."""
    aioclient_mock.get(f"{noaa_coops.STATIONS_URL}/tidepredstations.json", status=503)
    aioclient_mock.get(f"{noaa_coops.STATIONS_URL}/stations.json", status=503)
    aioclient_mock.get("https://api.weather.gov/zones", status=503)
    aioclient_mock.get(ndbc.STATIONS_URL, status=503)
    aioclient_mock.get(metar.STATIONINFO_URL, status=503)
    result = await _add(hass, entry, SUBENTRY_SPOT, SPOT_INPUT)
    assert result["step_id"] == "sources"
    assert result["errors"] == {"base": "suggestions_unavailable"}
    assert {key: _suggested(result, key) for key in SOURCES} == dict.fromkeys(
        SOURCES, "none"
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], dict.fromkeys(SOURCES, "none") | NO_SENSORS
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize(
    ("changes", "field", "error"),
    [
        ({"name": "  "}, "name", "name_required"),
        ({"name": "x" * 41}, "name", "name_too_long"),
        ({"name": "harbor"}, "name", "name_taken"),
        (
            {"location": {"latitude": 32.7, "longitude": -117.2, "radius": 500.0}},
            "location",
            "radius_out_of_range",
        ),
        ({"notes": "x" * 501}, "notes", "notes_too_long"),
    ],
)
async def test_spot_errors(
    hass: HomeAssistant,
    full_entry: MockConfigEntry,
    changes: dict[str, Any],
    field: str,
    error: str,
) -> None:
    """Bad names and radii are caught before anything is saved."""
    result = await _add(hass, full_entry, SUBENTRY_SPOT, SPOT_INPUT | changes)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {field: error}


async def test_edit_spot(
    hass: HomeAssistant, full_entry: MockConfigEntry, suggestions: AiohttpClientMocker
) -> None:
    """Editing a spot shows its values, keeps its sources, and saves changes."""
    result = await _edit(hass, full_entry, "spot_harbor")
    assert _suggested(result, "name") == "Harbor"
    assert _suggested(result, "location") == {
        "latitude": 32.75,
        "longitude": -117.27,
        "radius": 10_000.0,
    }

    harbor = {"latitude": HARBOR_POINT[0], "longitude": HARBOR_POINT[1]}
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        SPOT_INPUT
        | {
            "name": "Harbor",
            "location": harbor | {"radius": 8000.0},
            "notes": " The sea breeze fills from the SW most afternoons. \n",
        },
    )
    assert result["step_id"] == "sources"
    # The saved sources are kept, including "none". A spot saved before
    # buoys and airports gets the nearest suggested.
    assert _suggested(result, "tide_station") == "9410170"
    assert _suggested(result, "current_station") == "none"
    assert _suggested(result, "marine_zone") == "PZZ740"
    assert _suggested(result, "buoy") == "SDBC1"
    assert _suggested(result, "airport") == "KSAN"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "tide_station": "9410170",
            "current_station": "none",
            "marine_zone": "PZZ740",
            "buoy": "none",
            "airport": "KSAN",
        }
        | NO_SENSORS,
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    spot = full_entry.subentries["spot_harbor"]
    assert spot.title == "Harbor"
    assert spot.data["radius"] == 8000.0
    assert spot.data["marine_zone"] == "PZZ740"
    assert spot.data["buoy"] is None
    assert spot.data["source_points"] == {"airport": [32.73645, -117.19727]}
    # Notes are kept without the spaces around them, and shown when editing.
    assert spot.data["notes"] == "The sea breeze fills from the SW most afternoons."
    result = await _edit(hass, full_entry, "spot_harbor")
    assert _suggested(result, "notes") == (
        "The sea breeze fills from the SW most afternoons."
    )


async def test_add_boat_in_feet(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """With US units, lengths are entered in feet and stored in meters."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    result = await _add(
        hass,
        entry,
        SUBENTRY_BOAT,
        {"name": "Day sailer", "size_class": "small_keelboat", "length": 20},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    boat = _only(entry, SUBENTRY_BOAT)
    assert dict(boat.data) == {
        "size_class": "small_keelboat",
        "length": 6.096,
        "lights": False,
    }

    result = await _edit(hass, entry, boat.subentry_id)
    assert _suggested(result, "length") == 20.0
    assert _suggested(result, "lights") is False


async def test_add_boat_in_meters(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """With metric units, lengths are entered and stored in meters."""
    result = await _add(
        hass,
        entry,
        SUBENTRY_BOAT,
        {"name": "Cruiser", "size_class": "cruiser", "length": 10.4, "lights": True},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    boat = _only(entry, SUBENTRY_BOAT)
    assert boat.data["length"] == 10.4
    assert boat.data["lights"] is True

    result = await _edit(hass, entry, boat.subentry_id)
    assert _suggested(result, "lights") is True


async def test_boat_length_out_of_range(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """A boat can't be shorter than 1 m or longer than 50 m."""
    result = await _add(
        hass,
        entry,
        SUBENTRY_BOAT,
        {"name": "Toy", "size_class": "dinghy", "length": 0.5},
    )
    assert result["errors"] == {"length": "length_out_of_range"}


async def test_sailor_needs_a_boat(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """A sailor can't be added before there's a boat."""
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_SAILOR), context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_boats"


async def test_add_sailor(hass: HomeAssistant, full_entry: MockConfigEntry) -> None:
    """A sailor's usual boat comes first, and days are kept in week order.

    Each day they sail keeps its own hours; the other days' are dropped.
    """
    result = await _add(
        hass,
        full_entry,
        SUBENTRY_SAILOR,
        {
            "name": "Sam",
            "skill": "beginner",
            "default_boat": "boat_cruiser",
            "other_boats": ["boat_keelboat", "boat_cruiser"],
            "days": ["sun", "fri", "sat"],
        }
        | SECTIONS
        | {
            "hours": {
                "fri_start": "17:00:00",
                "fri_end": "20:30:00",
                "sun_end": "16:30:00",
                "mon_start": "06:00:00",
            }
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    sam = next(
        subentry
        for subentry in full_entry.subentries.values()
        if subentry.title == "Sam"
    )
    assert dict(sam.data) == {
        "skill": "beginner",
        "boats": ["boat_cruiser", "boat_keelboat"],
        "days": ["fri", "sat", "sun"],
        "hours": {
            "fri": {"start": "17:00:00", "end": "20:30:00"},
            "sat": {"start": None, "end": None},
            "sun": {"start": None, "end": "16:30:00"},
        },
        **NO_EXTRAS,
    }


async def test_new_sailor_defaults(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """With one boat, a new sailor starts with it and every day picked."""
    await _add(
        hass,
        entry,
        SUBENTRY_BOAT,
        {"name": "Dinghy", "size_class": "dinghy", "length": 4.2},
    )
    boat = _only(entry, SUBENTRY_BOAT)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_SAILOR), context={"source": SOURCE_USER}
    )
    assert _suggested(result, "default_boat") == boat.subentry_id
    assert _suggested(result, "days") == [
        "mon",
        "tue",
        "wed",
        "thu",
        "fri",
        "sat",
        "sun",
    ]


@pytest.mark.parametrize(
    ("changes", "errors"),
    [
        ({"days": []}, {"days": "no_days"}),
        (
            {"hours": {"sat_start": "15:00:00", "sat_end": "09:00:00"}},
            {"sat_end": "end_before_start"},
        ),
    ],
)
async def test_sailor_errors(
    hass: HomeAssistant,
    full_entry: MockConfigEntry,
    changes: dict[str, Any],
    errors: dict[str, str],
) -> None:
    """Missing days and a day's finish before its start are caught."""
    result = await _edit(hass, full_entry, "sailor_alex")
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Alex",
            "skill": "intermediate",
            "default_boat": "boat_keelboat",
            "days": ["sat"],
        }
        | SECTIONS
        | changes,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == errors


async def test_boat_removed_while_editing(
    hass: HomeAssistant, full_entry: MockConfigEntry
) -> None:
    """A boat removed while the form is open can't be saved as the usual boat."""
    result = await _edit(hass, full_entry, "sailor_alex")
    hass.config_entries.async_remove_subentry(full_entry, "boat_cruiser")

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Alex",
            "skill": "intermediate",
            "default_boat": "boat_cruiser",
            "days": ["sat"],
        }
        | SECTIONS,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"default_boat": "unknown_boat"}


async def test_edit_sailor(hass: HomeAssistant, full_entry: MockConfigEntry) -> None:
    """Editing a sailor shows their boats split into usual and other.

    Alex was saved with one start for every day, which each of their days
    now shows.
    """
    result = await _edit(hass, full_entry, "sailor_alex")
    assert _suggested(result, "default_boat") == "boat_keelboat"
    assert _suggested(result, "other_boats") == ["boat_cruiser"]
    assert _suggested_in(result, "hours", "sat_start") == "09:00:00"
    assert _suggested_in(result, "hours", "sun_start") == "09:00:00"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Alex",
            "skill": "advanced",
            "default_boat": "boat_cruiser",
            "days": ["sat", "sun"],
        }
        | SECTIONS
        | {"hours": {"sat_start": "09:00:00"}},
    )
    assert result["type"] is FlowResultType.ABORT
    assert dict(full_entry.subentries["sailor_alex"].data) == {
        "skill": "advanced",
        "boats": ["boat_cruiser"],
        "days": ["sat", "sun"],
        "hours": {
            "sat": {"start": "09:00:00", "end": None},
            "sun": {"start": None, "end": None},
        },
        **NO_EXTRAS,
    }


async def test_spot_from_before_sources(
    hass: HomeAssistant, suggestions: AiohttpClientMocker
) -> None:
    """Editing a spot saved before sources existed suggests the nearest ones."""
    old = BAY | {"data": {k: v for k, v in BAY["data"].items() if k not in SOURCES}}
    entry = MockConfigEntry(domain=DOMAIN, title=NAME, data={}, subentries_data=[old])
    entry.add_to_hass(hass)
    result = await _edit(hass, entry, "spot_bay")
    location = {"latitude": 32.68, "longitude": -117.17, "radius": 10_000.0}
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], SPOT_INPUT | {"name": "Bay", "location": location}
    )
    assert {key: _suggested(result, key) for key in SOURCES} == SOURCES


def _suggested_in(result: dict[str, Any], section: str, field: str) -> Any:
    """Return the value a form suggests for a field in a section."""
    for key, value in result["data_schema"].schema.items():
        if key == section:
            for inner in value.schema.schema:
                if inner == field:
                    return inner.description["suggested_value"]
    raise KeyError(f"{section}.{field}")


async def test_sailor_comfort_and_calendar(
    hass: HomeAssistant, full_entry: MockConfigEntry, family: str
) -> None:
    """Comfort is kept in °C, and automatic adding needs a calendar that takes events.

    The SailCast calendars are read-only, so they can't be chosen.
    """
    hass.config.units = US_CUSTOMARY_SYSTEM
    person = await hass.auth.async_create_user("Sam")
    result = await hass.config_entries.subentries.async_init(
        (full_entry.entry_id, SUBENTRY_SAILOR), context={"source": SOURCE_USER}
    )
    assert {"value": person.id, "label": "Sam"} in _options(result, "user")
    # Weekends, good windows and three days ahead are suggested, at every spot.
    assert _suggested_in(result, "auto_calendar", "auto_days") == ["sat", "sun"]
    assert _suggested_in(result, "auto_calendar", "ahead") == "2"
    assert _suggested_in(result, "auto_calendar", "auto_spots") == ["spot_harbor"]
    sailor = {
        "name": "Sam",
        "skill": "beginner",
        "default_boat": "boat_keelboat",
        "days": ["sat"],
        "hours": {},
        "user": person.id,
        "comfort": {"ideal_low": 6, "ideal_high": 10, "coldest": 59, "rain": "any"},
        "auto_calendar": {
            "calendar": "calendar.alex_sailing",
            "auto_days": ["sun", "sat"],
            "min_score": "80",
            "ahead": "4",
            "auto_spots": ["spot_harbor"],
        },
    }
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], sailor
    )
    assert result["errors"] == {"calendar": "calendar_read_only"}

    sailor["auto_calendar"]["calendar"] = family  # type: ignore[index]
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], sailor
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    sam = next(
        subentry
        for subentry in full_entry.subentries.values()
        if subentry.title == "Sam"
    )
    assert sam.data["user"] == person.id
    assert sam.data["comfort"] == {
        "ideal_low": 6,
        "ideal_high": 10,
        "coldest": 15.0,
        "rain": "any",
    }
    assert sam.data["auto_calendar"] == {
        "calendar": "calendar.family",
        "days": ["sat", "sun"],
        "min_score": 80,
        "ahead": 4,
        "spots": ["spot_harbor"],
    }

    result = await _edit(hass, full_entry, sam.subentry_id)
    assert _suggested(result, "user") == person.id
    assert _suggested_in(result, "comfort", "coldest") == 59
    assert _suggested_in(result, "auto_calendar", "min_score") == "80"


@pytest.mark.parametrize(
    ("comfort", "errors"),
    [
        ({"ideal_low": 14, "ideal_high": 8}, {"ideal_high": "ideal_high_below_low"}),
        ({"coldest": 40}, {"coldest": "coldest_out_of_range"}),
    ],
)
async def test_sailor_comfort_errors(
    hass: HomeAssistant,
    full_entry: MockConfigEntry,
    comfort: dict[str, Any],
    errors: dict[str, str],
) -> None:
    """A backwards ideal range and far-off cold are caught."""
    result = await _edit(hass, full_entry, "sailor_alex")
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Alex",
            "skill": "intermediate",
            "default_boat": "boat_keelboat",
            "days": ["sat"],
        }
        | SECTIONS
        | {"comfort": {"rain": "some"} | comfort},
    )
    assert result["errors"] == errors


async def test_options_keep_the_worldtides_key(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """The options set WorldTides' key; an empty field removes it."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"keys": {"worldtides_key": "  a-key  "}, "ai": {}}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"worldtides_key": "a-key"}
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"keys": {"worldtides_key": ""}, "ai": {}}
    )
    assert entry.options == {}
