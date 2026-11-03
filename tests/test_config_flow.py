"""Tests for setting up SailCast and adding spots, boats and sailors."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sailcast.const import (
    DOMAIN,
    NAME,
    SUBENTRY_BOAT,
    SUBENTRY_SAILOR,
    SUBENTRY_SPOT,
)

SPOT_INPUT = {
    "name": "Marina",
    "location": {"latitude": 32.71, "longitude": -117.17, "radius": 8000.0},
    "water_type": "bay",
    "offshore": ["w", "e"],
    "exposed": ["s"],
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


async def test_add_spot(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """A spot stores its pin, radius and directions in a fixed order."""
    result = await _add(hass, entry, SUBENTRY_SPOT, SPOT_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY

    spot = _only(entry, SUBENTRY_SPOT)
    assert spot.title == "Marina"
    assert dict(spot.data) == {
        "latitude": 32.71,
        "longitude": -117.17,
        "radius": 8000.0,
        "water_type": "bay",
        "offshore": ["e", "w"],
        "exposed": ["s"],
    }


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


async def test_edit_spot(hass: HomeAssistant, full_entry: MockConfigEntry) -> None:
    """Editing a spot shows its values and saves the changes."""
    result = await _edit(hass, full_entry, "spot_harbor")
    assert _suggested(result, "name") == "Harbor"
    assert _suggested(result, "location") == {
        "latitude": 32.7,
        "longitude": -117.2,
        "radius": 10_000.0,
    }

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], SPOT_INPUT | {"name": "Harbor"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    spot = full_entry.subentries["spot_harbor"]
    assert spot.title == "Harbor"
    assert spot.data["radius"] == 8000.0


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
    assert dict(boat.data) == {"size_class": "small_keelboat", "length": 6.096}

    result = await _edit(hass, entry, boat.subentry_id)
    assert _suggested(result, "length") == 20.0


async def test_add_boat_in_meters(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """With metric units, lengths are entered and stored in meters."""
    result = await _add(
        hass,
        entry,
        SUBENTRY_BOAT,
        {"name": "Cruiser", "size_class": "cruiser", "length": 10.4},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert _only(entry, SUBENTRY_BOAT).data["length"] == 10.4


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
    """A sailor's usual boat comes first, and days are kept in week order."""
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
            "end": "16:30:00",
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
        "start": None,
        "end": "16:30:00",
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
            {"start": "15:00:00", "end": "09:00:00"},
            {"end": "end_before_start"},
        ),
    ],
)
async def test_sailor_errors(
    hass: HomeAssistant,
    full_entry: MockConfigEntry,
    changes: dict[str, Any],
    errors: dict[str, str],
) -> None:
    """Missing days and a finish before the start are caught."""
    result = await _edit(hass, full_entry, "sailor_alex")
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Alex",
            "skill": "intermediate",
            "default_boat": "boat_keelboat",
            "days": ["sat"],
        }
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
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"default_boat": "unknown_boat"}


async def test_edit_sailor(hass: HomeAssistant, full_entry: MockConfigEntry) -> None:
    """Editing a sailor shows their boats split into usual and other."""
    result = await _edit(hass, full_entry, "sailor_alex")
    assert _suggested(result, "default_boat") == "boat_keelboat"
    assert _suggested(result, "other_boats") == ["boat_cruiser"]
    assert _suggested(result, "start") == "09:00:00"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Alex",
            "skill": "advanced",
            "default_boat": "boat_cruiser",
            "days": ["sat", "sun"],
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert dict(full_entry.subentries["sailor_alex"].data) == {
        "skill": "advanced",
        "boats": ["boat_cruiser"],
        "days": ["sat", "sun"],
        "start": None,
        "end": None,
    }
