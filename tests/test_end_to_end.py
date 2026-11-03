"""The recorded San Diego week, run through everything, against hand-checked cases.

Each case below was worked out by hand from the recorded numbers and the
plan's rules, so a change that moves a rating or score shows up here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.sailcast.const import DOMAIN, NAME, SUBENTRY_SAILOR

from .conftest import CRUISER, HARBOR, KEELBOAT, RECORDED


async def forecast(hass: HomeAssistant, spot: str, sailor: str) -> dict[str, Any]:
    """Return get_forecast's response."""
    response = await hass.services.async_call(
        DOMAIN,
        "get_forecast",
        {"spot": spot, "sailor": sailor},
        blocking=True,
        return_response=True,
    )
    assert isinstance(response, dict)
    return response


def hour_at(response: dict[str, Any], when: datetime) -> dict[str, Any]:
    """Return one hour from get_forecast's response."""
    return next(
        hour
        for hour in response["hours"]
        if datetime.fromisoformat(hour["time"]) == when
    )


async def test_calm_afternoon_on_the_river(
    hass: HomeAssistant, loaded: MockConfigEntry
) -> None:
    """Monday 2 PM on the river, for a beginner in the 20 ft keelboat.

    The models give 5.4, 7.1 and 6.1 kt, so 6.1 kt, with gusts to 14.2 kt:
    under the beginner's 10 kt, under the boat's 22 kt gusts, and 8.1 kt over
    the mean isn't gusty. No waves on the river, so it's good. The score
    loses 14.4 for light air (0.9 kt under 7 kt) and 3.3 for gusts (1.1 kt
    past 7 kt over the mean): 82.
    """
    assert hass.states.get("sensor.sam_river_rating").state == "good"
    assert hass.states.get("sensor.sam_river_score").state == "82"
    assert hass.states.get("binary_sensor.sam_river_good_to_sail").state == "on"


async def test_ocean_swell_at_the_harbor(
    hass: HomeAssistant, loaded: MockConfigEntry
) -> None:
    """Monday 2 PM at the harbor: 1.38 m waves.

    That's past the keelboat's 4 ft (1.22 m) at every skill level, and past
    the cruiser's 3 ft (0.91 m) caution but under its 6 ft.
    """
    for sailor in ("Alex", "Sam"):
        hour = hour_at(
            await forecast(hass, "Harbor", sailor),
            datetime(2026, 11, 2, 22, tzinfo=UTC),
        )
        assert hour["wave_height"] == 1.38  # meters, with metric units
        assert hour["ratings"]["small_keelboat"] == "not_recommended"
        assert hour["ratings"]["cruiser"] == "caution"
        keelboat = hour["boats"][0]
        assert keelboat["boat"] == "Keelboat"
        assert keelboat["reasons"] == ["waves"]
        assert keelboat["score"] <= 25
    assert hass.states.get("sensor.alex_harbor_rating").state == "not_recommended"


async def test_weekend_window_on_the_river(
    hass: HomeAssistant, loaded: MockConfigEntry
) -> None:
    """Alex sails weekends from 9 AM, so the next window is Saturday's."""
    state = hass.states.get("sensor.alex_next_sailing_window")
    assert state.state == "2026-11-07T21:00:00+00:00"
    assert state.attributes["spot"] == "River"
    assert state.attributes["boat"] == "Keelboat"
    # The window ends at sunset, not on the hour.
    assert state.attributes["end"] == "2026-11-08T00:53:00+00:00"
    assert hass.states.get("binary_sensor.alex_river_good_to_sail").state == "off"


@pytest.fixture
async def advisory_entry(
    hass: HomeAssistant,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> MockConfigEntry:
    """Return an entry whose harbor is in the zone with the recorded advisory.

    Its sailors cover all three skill levels.
    """
    harbor = ConfigSubentryData(
        **(HARBOR | {"data": HARBOR["data"] | {"marine_zone": "PZZ745"}})
    )
    sailors = [
        ConfigSubentryData(
            data={
                "skill": skill,
                "boats": ["boat_keelboat", "boat_cruiser"],
                "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
                "start": None,
                "end": None,
            },
            subentry_id=f"sailor_{skill}",
            subentry_type=SUBENTRY_SAILOR,
            title=skill.title(),
            unique_id=None,
        )
        for skill in ("beginner", "intermediate", "advanced")
    ]
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=NAME,
        data={},
        subentries_data=[harbor, KEELBOAT, CRUISER, *sailors],
    )
    entry.add_to_hass(hass)
    freezer.move_to(RECORDED)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.parametrize("sailor", ["Beginner", "Intermediate", "Advanced"])
async def test_small_craft_advisory(
    hass: HomeAssistant, advisory_entry: MockConfigEntry, sailor: str
) -> None:
    """An advisory holds small boats at not recommended for every skill level.

    That's dinghies and small keelboats, from its onset to its end: 1 PM
    Tuesday to 4 AM Wednesday, Pacific time.
    """
    response = await forecast(hass, "Harbor", sailor)
    covered = [hour for hour in response["hours"] if hour["warnings"]]
    assert covered[0]["time"] == "2026-11-03T21:00:00+00:00"
    assert covered[-1]["time"] == "2026-11-04T11:00:00+00:00"
    for hour in covered:
        assert hour["warnings"] == ["Small Craft Advisory"]
        for size in ("dinghy", "small_keelboat"):
            assert hour["ratings"][size] in ("not_recommended", "dangerous")
        for size in ("cruiser", "large_cruiser"):
            assert hour["ratings"][size] != "good"
    # Tuesday 2 PM: 1.18 m waves alone would make the keelboat caution.
    tuesday = hour_at(response, datetime(2026, 11, 3, 22, tzinfo=UTC))
    keelboat = tuesday["boats"][0]
    assert keelboat["rating"] == "not_recommended"
    assert keelboat["reasons"][0] == "warning"
    # The hour before the onset isn't covered.
    before = hour_at(response, datetime(2026, 11, 3, 20, tzinfo=UTC))
    assert before["warnings"] == []


async def test_warning_sensor_during_the_advisory(
    hass: HomeAssistant,
    advisory_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The marine warning sensor is off before the onset and on during it."""
    state = hass.states.get("binary_sensor.harbor_marine_warning")
    assert state.state == "off"
    assert state.attributes["warnings"][0]["event"] == "Small Craft Advisory"
    freezer.move_to(datetime(2026, 11, 3, 22, 30, tzinfo=UTC))
    await advisory_entry.runtime_data.results.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.harbor_marine_warning").state == "on"
    assert hass.states.get("sensor.beginner_harbor_rating").state == ("not_recommended")
