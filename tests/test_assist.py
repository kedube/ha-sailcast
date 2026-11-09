"""Tests for Ask SailCast: the forecast as tools for conversation agents."""

from __future__ import annotations

from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import llm
import pytest
from pytest_homeassistant.common import MockConfigEntry, MockUser
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from custom_components.sailcast.assist import NOT_SET_UP
from custom_components.sailcast.const import DOMAIN
from custom_components.sailcast.storage import DATA_STORE

from .conftest import set_up


def context(user: str | None = None) -> llm.LLMContext:
    """Return a conversation's context, as asked by a user."""
    return llm.LLMContext(
        platform="test",
        context=Context(user_id=user),
        language="en",
        assistant="conversation",
        device_id=None,
    )


async def call(
    hass: HomeAssistant, tool: str, args: dict[str, Any], user: str | None = None
) -> llm.ToolResult:
    """Call one of SailCast's tools."""
    api = await llm.async_get_api(hass, DOMAIN, context(user))
    return await api.async_call_tool(llm.ToolInput(tool_name=tool, tool_args=args))


@pytest.fixture
async def loaded(
    hass: HomeAssistant,
    sailcast_entry: MockConfigEntry,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    hass_admin_user: MockUser,
) -> MockConfigEntry:
    """Return the test entry, set up, with Alex linked to the admin user."""
    alex = sailcast_entry.subentries["sailor_alex"]
    hass.config_entries.async_update_subentry(
        sailcast_entry, alex, data=dict(alex.data) | {"user": hass_admin_user.id}
    )
    await set_up(hass, sailcast_entry, freezer)
    return sailcast_entry


async def test_offered_to_agents(
    hass: HomeAssistant, loaded: MockConfigEntry, hass_admin_user: MockUser
) -> None:
    """Conversation agents can choose SailCast, which knows who's asking."""
    assert any(
        api.id == DOMAIN and api.name == "SailCast" for api in llm.async_get_apis(hass)
    )
    api = await llm.async_get_api(hass, DOMAIN, context(hass_admin_user.id))
    assert [tool.name for tool in api.tools] == ["sailcast_week", "sailcast_day"]
    assert all(tool.annotations.read_only for tool in api.tools)
    prompt = api.api_prompt
    assert "Never contradict or soften them" in prompt
    assert "It's Monday 2026-11-02 14:36." in prompt
    assert "Saturday 2026-11-07" in prompt
    assert "Alex (intermediate; boats: Keelboat, Cruiser)" in prompt
    assert "Sam (beginner; boats: Keelboat)" in prompt
    assert "The person asking is Alex." in prompt
    assert "Spots: Harbor, Bay, River." in prompt
    assert "heights in m" in prompt

    # Someone who isn't a sailor is asked about by name.
    other = await llm.async_get_api(hass, DOMAIN, context("someone-else"))
    assert "The person asking" not in other.api_prompt


async def test_week(
    hass: HomeAssistant, loaded: MockConfigEntry, hass_admin_user: MockUser
) -> None:
    """The week tool gives the person asking their week, or part of it."""
    result = await call(hass, "sailcast_week", {}, hass_admin_user.id)
    assert not result.error
    forecast = result.data["forecast"]
    assert isinstance(forecast, dict)
    assert forecast["sailor"]["name"] == "Alex"
    assert len(forecast["days"]) == 7
    # No advice or tides: the day tool has the details.
    assert "advice" not in forecast["days"][0]["spots"][0]["boats"][0]
    assert "tides" not in forecast["days"][0]["spots"][0]

    # Names are matched whatever their case.
    result = await call(
        hass,
        "sailcast_week",
        {"spot": "river", "boat": "KEELBOAT", "date": "2026-11-07"},
        hass_admin_user.id,
    )
    forecast = result.data["forecast"]
    assert isinstance(forecast, dict)
    (saturday,) = forecast["days"]
    (river,) = saturday["spots"]
    (keelboat,) = river["boats"]
    assert river["spot"] == "River"
    assert keelboat["windows"][0] | {"id": None} == {
        "id": None,
        "from": "13:00",
        "to": "16:53",
        "score": 80,
        "wind": [5, 6],
        "gusts": 15,
        "wind_from": "NW",
    }

    # Sam's week, asked for by name: a beginner in the keelboat.
    result = await call(hass, "sailcast_week", {"sailor": "Sam"}, hass_admin_user.id)
    forecast = result.data["forecast"]
    assert isinstance(forecast, dict)
    assert forecast["sailor"] == {"name": "Sam", "skill": "beginner", "wind_limit": 10}
    assert [boat["name"] for boat in forecast["boats"]] == ["Keelboat"]


async def test_day(
    hass: HomeAssistant, loaded: MockConfigEntry, hass_admin_user: MockUser
) -> None:
    """The day tool gives one day at one spot, hour by hour, for each boat."""
    result = await call(
        hass,
        "sailcast_day",
        {"date": "2026-11-07", "spot": "River"},
        hass_admin_user.id,
    )
    assert not result.error
    day = result.data["forecast"]
    assert isinstance(day, dict)
    assert day["spot"] == "River"
    assert day["weekday"] == "Saturday"
    assert day["sailing_hours"] == {"from": "09:00"}
    assert [window["boat"] for window in day["windows"]] == ["Keelboat", "Cruiser"]
    assert day["tides"]
    hours = day["hours"]
    assert hours[0]["time"] == "06:00"
    assert hours[-1]["time"] == "16:00"
    assert [boat["boat"] for boat in hours[0]["boats"]] == ["Keelboat", "Cruiser"]
    assert all(boat["rating"] == "good" for boat in hours[-1]["boats"])
    # At the harbor the waves make every hour caution, which says why.
    result = await call(
        hass,
        "sailcast_day",
        {"date": "2026-11-07", "spot": "Harbor"},
        hass_admin_user.id,
    )
    day = result.data["forecast"]
    assert isinstance(day, dict)
    assert day["hours"][0]["boats"][0] == {
        "boat": "Keelboat",
        "rating": "caution",
        "score": 22,
        "reasons": [{"reason": "waves", "height": 1.0}],
    }

    # Without a spot, it's the one the person asking picked in the panel.
    hass.data[DATA_STORE].set_preferences(hass_admin_user.id, {"spot": "spot_bay"})
    result = await call(
        hass, "sailcast_day", {"date": "2026-11-07"}, hass_admin_user.id
    )
    day = result.data["forecast"]
    assert isinstance(day, dict)
    assert day["spot"] == "Bay"


@pytest.mark.parametrize(
    "case",
    [
        ("sailcast_week", {"spot": "Lake"}, "admin", "There's no spot called Lake."),
        ("sailcast_week", {"sailor": "Kim"}, "admin", "There's no sailor called Kim."),
        (
            "sailcast_week",
            {"sailor": "Sam", "boat": "Cruiser"},
            "admin",
            "Sam has no boat called Cruiser.",
        ),
        (
            "sailcast_week",
            {},
            None,
            "Ask which sailor this is for: Alex, Sam",
        ),
        ("sailcast_week", {"date": "2026-12-25"}, "admin", "no forecast"),
        ("sailcast_day", {}, "admin", "Say which day"),
        ("sailcast_day", {"date": "2026-12-25"}, "admin", "no forecast"),
    ],
)
async def test_questions_it_cant_answer(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    hass_admin_user: MockUser,
    case: tuple[str, dict[str, Any], str | None, str],
) -> None:
    """A question about something SailCast doesn't have says what's wrong."""
    tool, args, user, error = case
    result = await call(
        hass, tool, args, hass_admin_user.id if user == "admin" else None
    )
    assert result.error
    message = result.data["error"]
    assert isinstance(message, str)
    assert error in message


async def test_not_set_up(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    hass_admin_user: MockUser,
) -> None:
    """Without SailCast loaded, agents are told it isn't set up."""
    assert await hass.config_entries.async_unload(loaded.entry_id)
    api = await llm.async_get_api(hass, DOMAIN, context(hass_admin_user.id))
    assert api.api_prompt == NOT_SET_UP
    assert api.tools == []
