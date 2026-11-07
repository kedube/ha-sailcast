"""Tests for what SailCast keeps between restarts for the panel."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.sailcast.profiles import Hours
from custom_components.sailcast.storage import STORAGE_KEY, PlannedSail, SailCastStore

START = datetime(2026, 11, 7, 21, tzinfo=UTC)


def sail(**values: Any) -> PlannedSail:
    """Return a planned sail on Saturday afternoon."""
    return PlannedSail(
        **(
            {
                "id": "sail1",
                "sailor": "sailor_alex",
                "boat": "boat_keelboat",
                "spot": "spot_river",
                "calendar": "calendar.family",
                "start": START,
                "end": START + timedelta(hours=3),
                "title": "Sailing: River",
            }
            | values
        )
    )


async def test_round_trip(
    hass: HomeAssistant, hass_storage: dict[str, Any], freezer: FrozenDateTimeFactory
) -> None:
    """Preferences, planned sails and skipped days are saved and read back."""
    store = SailCastStore(hass)
    await store.async_load()
    assert store.set_preferences("user1", {"spot": "spot_river", "other": "x"}) == {
        "spot": "spot_river"
    }
    store.add(sail(uid="uid1", score=80))
    store.add(sail(id="sail2", start=START - timedelta(days=1), auto=True))
    store.skip("sailor_alex", date(2026, 11, 8))
    # Changes are saved a moment later.
    assert STORAGE_KEY not in hass_storage
    freezer.tick(timedelta(seconds=5))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert hass_storage[STORAGE_KEY]["data"]["skipped"] == {
        "sailor_alex": ["2026-11-08"]
    }

    again = SailCastStore(hass)
    await again.async_load()
    assert again.preferences("user1") == {"spot": "spot_river"}
    assert again.preferences("someone") == {}
    assert [item.id for item in again.planned] == ["sail2", "sail1"]
    assert again.get("sail1") == sail(uid="uid1", score=80)
    assert again.skipped("sailor_alex") == {date(2026, 11, 8)}


async def test_forgetting(hass: HomeAssistant) -> None:
    """A removed sailor's sails and days go, and so do days that have passed."""
    store = SailCastStore(hass)
    await store.async_load()
    store.add(sail())
    store.add(sail(id="sail2", sailor="sailor_sam"))
    store.skip("sailor_alex", date(2026, 11, 1))
    store.skip("sailor_alex", date(2026, 11, 8))

    store.forget_before(date(2026, 11, 2))
    assert store.skipped("sailor_alex") == {date(2026, 11, 8)}
    assert [item.id for item in store.forget_sailor("sailor_alex")] == ["sail1"]
    assert [item.id for item in store.planned] == ["sail2"]
    assert store.skipped("sailor_alex") == set()
    assert store.remove("sail2") is not None
    assert store.remove("sail2") is None


async def test_hours_for_dates(
    hass: HomeAssistant, hass_storage: dict[str, Any], freezer: FrozenDateTimeFactory
) -> None:
    """Hours set for dates are saved, undone, and dropped once the date passes."""
    store = SailCastStore(hass)
    await store.async_load()
    store.set_hours("sailor_alex", date(2026, 11, 6), Hours())
    store.set_hours("sailor_alex", date(2026, 11, 7), None)
    store.set_hours("sailor_alex", date(2026, 11, 8), Hours("10:00:00", "12:00:00"))
    store.set_hours("sailor_sam", date(2026, 11, 8), None)
    freezer.tick(timedelta(seconds=5))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert hass_storage[STORAGE_KEY]["data"]["hours"]["sailor_alex"] == {
        "2026-11-06": {"start": None, "end": None},
        "2026-11-07": None,
        "2026-11-08": {"start": "10:00:00", "end": "12:00:00"},
    }

    again = SailCastStore(hass)
    await again.async_load()
    assert again.hours("sailor_alex") == {
        date(2026, 11, 6): Hours(),
        date(2026, 11, 7): None,
        date(2026, 11, 8): Hours("10:00:00", "12:00:00"),
    }
    again.clear_hours("sailor_alex", date(2026, 11, 8))
    again.forget_before(date(2026, 11, 7))
    assert again.hours("sailor_alex") == {date(2026, 11, 7): None}
    again.forget_sailor("sailor_sam")
    assert again.hours("sailor_sam") == {}


async def test_saved_by_another_version(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Keys from other versions are ignored."""
    data = sail().as_dict() | {"colour": "blue"}
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "key": STORAGE_KEY,
        "data": {"planned": [data]},
    }
    store = SailCastStore(hass)
    await store.async_load()
    assert store.get("sail1") == sail()
