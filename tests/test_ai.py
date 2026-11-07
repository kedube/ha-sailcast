"""Tests for the optional AI summary, with a stand-in AI task."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
import json
from typing import Any
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.ai_task import (
    AITaskEntity,
    AITaskEntityFeature,
    GenDataTask,
    GenDataTaskResult,
)
from homeassistant.components.ai_task.const import DATA_COMPONENT, DATA_PREFERENCES
from homeassistant.components.conversation import ChatLog
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.sailcast import ai

from .conftest import set_up

type Send = Callable[..., Awaitable[dict[str, Any]]]

SATURDAY = {
    "spot": "spot_river",
    "sailor": "sailor_alex",
    "date": "2026-11-07",
    "language": "de",
}
KEY = ("spot_river", "sailor_alex", "boat_keelboat", "2026-11-07", "de")
ANSWER = (
    "Leichter Wind aus Nordwest. Das beste Fenster ist von 13 Uhr bis Sonnenuntergang."
)
AI_ON = {"ai_summary": True, "ai_task": "ai_task.stand_in"}


class StandInTask(AITaskEntity):
    """An AI task that gives whatever answer it's told to, and keeps the questions."""

    _attr_name = "Stand-in"
    _attr_supported_features = AITaskEntityFeature.GENERATE_DATA

    def __init__(self) -> None:
        """Answer with a German summary."""
        self.answer: Any = ANSWER
        self.asked: list[str] = []

    async def _async_generate_data(
        self, task: GenDataTask, chat_log: ChatLog
    ) -> GenDataTaskResult:
        self.asked.append(task.instructions)
        if isinstance(self.answer, Exception):
            raise self.answer
        return GenDataTaskResult(
            conversation_id=chat_log.conversation_id, data=self.answer
        )


@pytest.fixture(autouse=True)
async def mock_http(hass: HomeAssistant) -> Any:
    """Serve real HTTP for the WebSocket client, as in the panel's tests."""
    hass.config.components.update({"frontend", "panel_custom"})
    assert await async_setup_component(hass, "http", {})
    hass.http.async_register_static_paths = AsyncMock()  # type: ignore[method-assign]
    return hass.http


async def set_up_ai_task(hass: HomeAssistant) -> None:
    """Set up AI Task, which needs Home Assistant's own integration first."""
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "ai_task", {})


@pytest.fixture
async def stand_in(hass: HomeAssistant) -> StandInTask:
    """Set up AI Task with the stand-in."""
    await set_up_ai_task(hass)
    task = StandInTask()
    await hass.data[DATA_COMPONENT].async_add_entities([task])
    return task


@pytest.fixture
async def ai_on(
    hass: HomeAssistant,
    sailcast_entry: MockConfigEntry,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> MockConfigEntry:
    """Return the test entry, set up with the AI summary on."""
    hass.config_entries.async_update_entry(sailcast_entry, options=AI_ON)
    await set_up(hass, sailcast_entry, freezer)
    return sailcast_entry


@pytest.fixture
async def ai_off(
    hass: HomeAssistant,
    sailcast_entry: MockConfigEntry,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> MockConfigEntry:
    """Return the test entry, set up with the options it starts with."""
    await set_up(hass, sailcast_entry, freezer)
    return sailcast_entry


@pytest.fixture
async def send(hass: HomeAssistant, hass_ws_client: WebSocketGenerator) -> Send:
    """Return a function that sends a panel command."""
    client = await hass_ws_client(hass)

    async def send(type_: str, **values: Any) -> dict[str, Any]:
        await client.send_json_auto_id({"type": f"sailcast/{type_}", **values})
        return await client.receive_json()  # type: ignore[no-any-return]

    return send


async def test_off_by_default(
    hass: HomeAssistant, ai_off: MockConfigEntry, stand_in: StandInTask, send: Send
) -> None:
    """Without the option, the panel offers no summary and none can be asked for."""
    assert (await send("config"))["result"]["ai"] is False
    response = await send("ai_summary", **SATURDAY)
    assert response["error"]["code"] == "ai_off"
    forecast = await send(
        "forecast", spot="spot_river", sailor="sailor_alex", language="de"
    )
    assert all("ai" not in day for day in forecast["result"]["days"])
    assert stand_in.asked == []


async def test_needs_ai_task(
    hass: HomeAssistant, ai_on: MockConfigEntry, send: Send
) -> None:
    """With the option on but AI Task not set up, there's no summary."""
    assert (await send("config"))["result"]["ai"] is False
    assert (await send("ai_summary", **SATURDAY))["error"]["code"] == "ai_off"


async def test_summary(
    hass: HomeAssistant, ai_on: MockConfigEntry, stand_in: StandInTask, send: Send
) -> None:
    """A summary is written in the reader's language, once, and kept for the day."""
    assert (await send("config"))["result"]["ai"] is True
    response = await send("ai_summary", **SATURDAY)
    assert response["result"] == {
        "text": ANSWER,
        "made": "2026-11-02T22:36:00+00:00",
        "current": True,
    }
    (asked,) = stand_in.asked
    assert "two or three sentences in German" in asked
    assert "Don't recommend clothing, wetsuits, drysuits or other gear" in asked
    assert "Never contradict or soften them" in asked
    data = json.loads(asked.split("The data, as JSON:\n", 1)[1])
    # The river spot's Saturday, for Alex in the keelboat, in metric units.
    assert data["date"] == "2026-11-07"
    assert data["boat"] == {
        "name": "Keelboat",
        "size": "small keelboat",
        "navigation_lights": False,
    }
    assert data["sailor"] == {"skill": "intermediate", "wind_limit": 16}
    assert data["units"]["height"] == "m"
    assert data["windows"] == [
        {"start": "13:00", "end": "16:53", "score": 80, "best": True}
    ]
    assert data["rating"]["most_of_the_day"] == "good"
    assert {"advice": "gusty"} in data["advice"]
    assert {"advice": "sunset", "time": "16:53"} in data["advice"]

    # Asking again, or opening the day again, gives the same summary.
    assert (await send("ai_summary", **SATURDAY))["result"]["text"] == ANSWER
    assert len(stand_in.asked) == 1
    forecast = await send(
        "forecast", spot="spot_river", sailor="sailor_alex", language="de"
    )
    days = forecast["result"]["days"]
    assert days[5]["ai"] == response["result"]
    assert days[4]["ai"] is None
    # Another language gets its own.
    english = await send(
        "forecast", spot="spot_river", sailor="sailor_alex", language="en"
    )
    assert english["result"]["days"][5]["ai"] is None

    # A settings change reloads SailCast; the summary stays.
    assert await hass.config_entries.async_reload(ai_on.entry_id)
    await hass.async_block_till_done()
    forecast = await send(
        "forecast", spot="spot_river", sailor="sailor_alex", language="de"
    )
    assert forecast["result"]["days"][5]["ai"]["text"] == ANSWER


async def test_kept_through_restart(
    hass: HomeAssistant,
    ai_on: MockConfigEntry,
    stand_in: StandInTask,
    send: Send,
    hass_storage: dict[str, Any],
) -> None:
    """A summary is saved a moment after it's written, and read after a restart."""
    response = await send("ai_summary", **SATURDAY)
    assert ai.STORAGE_KEY not in hass_storage
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=5))
    await hass.async_block_till_done()
    saved = hass_storage[ai.STORAGE_KEY]["data"]["summaries"]
    assert [item["key"] for item in saved] == [list(KEY)]

    restarted = ai.Summaries(hass)
    await restarted.async_load()
    kept = restarted.get(KEY)
    assert kept is not None
    assert kept.as_dict(kept.facts) == response["result"]


async def test_saved_summaries_checked(
    hass: HomeAssistant, hass_storage: dict[str, Any], freezer: FrozenDateTimeFactory
) -> None:
    """Saved summaries of days gone by, and unreadable ones, are left out."""
    freezer.move_to(datetime(2026, 11, 7, 18, tzinfo=UTC))
    made = "2026-11-06T18:00:00+00:00"
    yesterday = (*KEY[:3], "2026-11-06", "de")
    hass_storage[ai.STORAGE_KEY] = {
        "version": ai.STORAGE_VERSION,
        "key": ai.STORAGE_KEY,
        "data": {
            "summaries": [
                {"key": list(KEY), "text": ANSWER, "made": made, "facts": {}},
                {"key": list(yesterday), "text": "Gestern.", "made": made, "facts": {}},
                {"key": list(KEY[:4]), "text": "Ohne Sprache.", "made": made},
                {"key": list(KEY), "text": "Ohne Zeit.", "facts": {}},
            ]
        },
    }
    summaries = ai.Summaries(hass)
    await summaries.async_load()
    kept = summaries.get(KEY)
    assert kept is not None
    assert kept.text == ANSWER
    assert summaries.get(yesterday) is None


async def test_changed_forecast(
    hass: HomeAssistant, ai_on: MockConfigEntry, stand_in: StandInTask, send: Send
) -> None:
    """A summary stops being current when its ratings change, and is written again."""
    await send("ai_summary", **SATURDAY)
    summaries = ai_on.runtime_data.summaries
    kept = summaries.get(KEY)
    assert kept is not None
    # As if an hour had been rated caution when the summary was written.
    first = next(iter(kept.facts))
    summaries._kept[KEY] = ai.Summary(
        kept.text, kept.made, {**kept.facts, first: ["caution", False, []]}
    )
    forecast = await send(
        "forecast", spot="spot_river", sailor="sailor_alex", language="de"
    )
    assert forecast["result"]["days"][5]["ai"]["current"] is False
    stand_in.answer = "Ein neuer Text."
    response = await send("ai_summary", **SATURDAY)
    assert response["result"]["text"] == "Ein neuer Text."
    assert response["result"]["current"] is True
    assert len(stand_in.asked) == 2


@pytest.mark.parametrize(
    "case",
    [
        ({"summary": ANSWER}, "bad_answer"),
        ("x" * 1000, "bad_answer"),
        ("  ", "bad_answer"),
        (HomeAssistantError("The provider is down"), "ai_failed"),
    ],
)
async def test_failures(
    hass: HomeAssistant,
    ai_on: MockConfigEntry,
    stand_in: StandInTask,
    send: Send,
    case: tuple[Any, str],
) -> None:
    """An answer that isn't a summary, or a provider that fails, gives an error."""
    stand_in.answer, code = case
    response = await send("ai_summary", **SATURDAY)
    assert response["error"]["code"] == code
    assert ai_on.runtime_data.summaries.get(KEY) is None


async def test_nothing_left(
    hass: HomeAssistant,
    ai_on: MockConfigEntry,
    stand_in: StandInTask,
    send: Send,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A day that isn't forecast, or whose daylight is over, has nothing to say."""
    response = await send("ai_summary", **(SATURDAY | {"date": "2026-11-12"}))
    assert response["error"]["code"] == "not_found"
    # Monday evening, after sunset.
    freezer.move_to(datetime(2026, 11, 3, 2, tzinfo=UTC))
    response = await send("ai_summary", **(SATURDAY | {"date": "2026-11-02"}))
    assert response["error"]["code"] == "not_found"
    assert stand_in.asked == []


def test_clean() -> None:
    """Answers lose Markdown, line breaks and surrounding quotes."""
    assert (
        ai.clean('"**Good** sailing.\n\nGusts later."') == "Good sailing. Gusts later."
    )
    assert ai.clean("# Saturday\nLight air.") == "Saturday Light air."


def test_languages() -> None:
    """The AI is asked for each of SailCast's languages by name."""
    assert ai.LANGUAGES["pt-BR"] == "Brazilian Portuguese"
    assert set(ai.LANGUAGES) == {
        *("en", "de", "fr", "nl", "es", "zh-Hans"),
        *("it", "pl", "sv", "ru", "cs", "pt-BR"),
    }


async def test_options(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """The AI summary needs AI Task, and an AI task or Home Assistant's default."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    turn_on = {"keys": {}, "ai": {"ai_summary": True}}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], turn_on
    )
    assert result["errors"] == {"base": "no_ai_task"}

    await set_up_ai_task(hass)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], turn_on
    )
    assert result["errors"] == {"base": "no_default_ai_task"}

    # Home Assistant's default AI task will do.
    hass.data[DATA_PREFERENCES].async_set_preferences(
        gen_data_entity_id="ai_task.stand_in"
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], turn_on
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"ai_summary": True}

    # So will one picked here; turning the summary off forgets it.
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"keys": {}, "ai": {"ai_summary": True, "ai_task": "ai_task.other"}},
    )
    assert entry.options == {"ai_summary": True, "ai_task": "ai_task.other"}
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"keys": {}, "ai": {"ai_summary": False, "ai_task": "ai_task.other"}},
    )
    assert entry.options == {}
