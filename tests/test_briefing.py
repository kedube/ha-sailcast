"""Tests for the AI briefing, with a stand-in AI task."""

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

from custom_components.sailcast import ai, briefing

from .conftest import set_up

type Send = Callable[..., Awaitable[dict[str, Any]]]

ASK = {"sailor": "sailor_alex", "language": "de"}
WRITE = ASK | {"write": True}
KEY = ("sailor_alex", "de")
SATURDAY_RIVER_KEELBOAT = {
    "spot": "spot_river",
    "boat": "boat_keelboat",
    "date": "2026-11-07",
    "start": "2026-11-07T21:00:00+00:00",
    "end": "2026-11-08T00:53:00+00:00",
    "score": 80,
}
SATURDAY_RIVER_CRUISER = {
    "spot": "spot_river",
    "boat": "boat_cruiser",
    "date": "2026-11-07",
    "start": "2026-11-07T22:00:00+00:00",
    "end": "2026-11-08T00:53:00+00:00",
    "score": 66,
}
SUNDAY_RIVER_KEELBOAT = {
    "spot": "spot_river",
    "boat": "boat_keelboat",
    "date": "2026-11-08",
    "start": "2026-11-08T21:00:00+00:00",
    "end": "2026-11-09T00:00:00+00:00",
    "score": 70,
}
ANSWER = {
    "headline": "Samstagnachmittag am Fluss mit dem Kielboot.",
    "summary": (
        "Unter der Woche bleibt es an Hafen und Bucht wegen der Wellen bei "
        "Vorsicht. Am Wochenende weht am Fluss leichter Wind aus Nordwest."
    ),
    "picks": [
        {"window": "w1", "why": "Der beste Wind der Woche."},
        {"window": "w3", "why": "Etwas schwächer, aber gut."},
    ],
    "days": [
        {"date": "2026-11-07", "note": "Am Fluss ab 13 Uhr gut."},
        {"date": "2026-11-08", "note": "Wieder am Fluss, von 13 bis 16 Uhr."},
    ],
    "recheck": "",
}
AI_ON = {"ai_summary": True, "ai_task": "ai_task.stand_in"}


class StandInTask(AITaskEntity):
    """An AI task that gives whatever answer it's told to, and keeps the tasks."""

    _attr_name = "Stand-in"
    _attr_supported_features = AITaskEntityFeature.GENERATE_DATA

    def __init__(self) -> None:
        """Answer with a German briefing."""
        self.answer: Any = ANSWER
        self.tasks: list[GenDataTask] = []

    async def _async_generate_data(
        self, task: GenDataTask, chat_log: ChatLog
    ) -> GenDataTaskResult:
        self.tasks.append(task)
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
    """Return the test entry, set up with the AI briefing on."""
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


def asked_data(task: GenDataTask) -> dict[str, Any]:
    """Return the forecast the AI was given."""
    return json.loads(task.instructions.split("The data, as JSON:\n", 1)[1])  # type: ignore[no-any-return]


async def test_off_by_default(
    hass: HomeAssistant, ai_off: MockConfigEntry, stand_in: StandInTask, send: Send
) -> None:
    """Without the option, the panel offers no briefing and none can be asked for."""
    assert (await send("config"))["result"]["ai"] is False
    assert (await send("briefing", **WRITE))["error"]["code"] == "ai_off"
    assert stand_in.tasks == []


async def test_needs_ai_task(
    hass: HomeAssistant, ai_on: MockConfigEntry, send: Send
) -> None:
    """With the option on but AI Task not set up, there's no briefing."""
    assert (await send("config"))["result"]["ai"] is False
    assert (await send("briefing", **WRITE))["error"]["code"] == "ai_off"


async def test_briefing(
    hass: HomeAssistant, ai_on: MockConfigEntry, stand_in: StandInTask, send: Send
) -> None:
    """A briefing is written once, in the reader's language, from the whole week."""
    assert (await send("config"))["result"]["ai"] is True
    # Until someone asks for one to be written, there's none.
    assert (await send("briefing", **ASK))["result"] is None
    assert stand_in.tasks == []

    result = (await send("briefing", **WRITE))["result"]
    assert result == {
        "headline": ANSWER["headline"],
        "summary": ANSWER["summary"],
        # Each pick is SailCast's own window, with its spot, boat, times and score.
        "picks": [
            SATURDAY_RIVER_KEELBOAT | {"why": "Der beste Wind der Woche."},
            SUNDAY_RIVER_KEELBOAT | {"why": "Etwas schwächer, aber gut."},
        ],
        "days": {
            "2026-11-07": "Am Fluss ab 13 Uhr gut.",
            "2026-11-08": "Wieder am Fluss, von 13 bis 16 Uhr.",
        },
        "recheck": "",
        "made": "2026-11-02T22:36:00+00:00",
        "current": True,
    }
    (task,) = stand_in.tasks
    assert task.name == "SailCast briefing"
    assert task.structure is briefing.ANSWER
    assert "Write in German" in task.instructions
    assert "Never contradict or soften them" in task.instructions
    assert "Picks must be windows from the data" in task.instructions
    assert "Don't recommend clothing" in task.instructions

    # Alex's week at the three spots, in both boats, in metric units.
    data = asked_data(task)
    assert data["now"] == "Mon 14:36"
    assert data["units"]["height"] == "m"
    assert data["sailor"] == {"name": "Alex", "skill": "intermediate", "wind_limit": 16}
    assert data["boats"] == [
        {"name": "Keelboat", "size": "small keelboat", "navigation_lights": False},
        {"name": "Cruiser", "size": "cruiser", "navigation_lights": False},
    ]
    assert data["spots"] == [
        {"name": "Harbor", "water": "open coast"},
        {"name": "Bay", "water": "bay"},
        {"name": "River", "water": "river"},
    ]
    days = data["days"]
    assert [day["date"] for day in days] == [f"2026-11-0{n}" for n in range(2, 9)]
    # Alex sails at the weekend, from 9 AM until sunset.
    assert days[0]["sailing_hours"] is None
    assert days[5]["sailing_hours"] == {"from": "09:00"}
    saturday = days[5]
    assert saturday["weekday"] == "Saturday"
    assert saturday["sunset"] == "16:53"
    harbor, _, river = saturday["spots"]
    assert harbor["spot"] == "Harbor"
    assert harbor["warnings"] == []
    assert harbor["wind_from"] == "NW"
    # The waves at the harbor make the whole day caution, with the reason.
    assert harbor["boats"][0]["ratings"] == [
        {
            "from": "06:00",
            "to": "17:00",
            "rating": "caution",
            "reasons": [{"reason": "waves", "height": 1.0}],
        }
    ]
    assert "windows" not in harbor["boats"][0]
    keelboat, cruiser = river["boats"]
    assert keelboat["windows"] == [
        {
            "id": "w1",
            "from": "13:00",
            "to": "16:53",
            "score": 80,
            "wind": [5, 6],
            "gusts": 15,
            "wind_from": "NW",
        }
    ]
    assert cruiser["windows"][0]["id"] == "w2"
    # Tides and advice go with the first three days only.
    assert "tides" in days[0]["spots"][0]
    assert "advice" in days[0]["spots"][0]["boats"][0]
    assert "tides" not in harbor
    assert "advice" not in keelboat

    # Asking again gives the same briefing. Another language has none yet.
    assert (await send("briefing", **WRITE))["result"] == result
    assert (await send("briefing", **ASK))["result"] == result
    assert len(stand_in.tasks) == 1
    assert (await send("briefing", **(ASK | {"language": "en"})))["result"] is None

    # A settings change reloads SailCast; the briefing stays.
    assert await hass.config_entries.async_reload(ai_on.entry_id)
    await hass.async_block_till_done()
    assert (await send("briefing", **ASK))["result"] == result


async def test_spot_notes(
    hass: HomeAssistant, ai_on: MockConfigEntry, stand_in: StandInTask, send: Send
) -> None:
    """A spot's notes go to the AI, and changing them calls for a new briefing."""
    river = ai_on.subentries["spot_river"]
    notes = "Westerly sea breeze most afternoons."
    hass.config_entries.async_update_subentry(
        ai_on, river, data=dict(river.data) | {"notes": notes}
    )
    await hass.async_block_till_done()
    await send("briefing", **WRITE)
    data = asked_data(stand_in.tasks[0])
    assert data["spots"][2] == {"name": "River", "water": "river", "notes": notes}

    hass.config_entries.async_update_subentry(
        ai_on, river, data=dict(river.data) | {"notes": "Gusty in a southerly."}
    )
    await hass.async_block_till_done()
    assert (await send("briefing", **ASK))["result"]["current"] is False


async def test_changed_forecast(
    hass: HomeAssistant, ai_on: MockConfigEntry, stand_in: StandInTask, send: Send
) -> None:
    """A briefing stops being current when a rating changes, and is written again."""
    await send("briefing", **WRITE)
    briefings = ai_on.runtime_data.briefings
    kept = briefings.get(KEY)
    assert kept is not None
    # As if an hour had been rated dangerous when the briefing was written.
    first = next(iter(kept.facts))
    briefings._kept[KEY] = briefing.Briefing(
        **{name: getattr(kept, name) for name in ("headline", "summary", "picks")},
        days=kept.days,
        recheck=kept.recheck,
        made=kept.made,
        facts={**kept.facts, first: "dangerous|"},
    )
    assert (await send("briefing", **ASK))["result"]["current"] is False
    stand_in.answer = ANSWER | {"headline": "Ein neuer Text."}
    result = (await send("briefing", **WRITE))["result"]
    assert result["headline"] == "Ein neuer Text."
    assert result["current"] is True
    assert len(stand_in.tasks) == 2


async def test_hours_gone_by(
    hass: HomeAssistant,
    ai_on: MockConfigEntry,
    stand_in: StandInTask,
    send: Send,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Hours going by don't make a briefing out of date."""
    await send("briefing", **WRITE)
    freezer.tick(timedelta(hours=2))
    assert (await send("briefing", **ASK))["result"]["current"] is True


async def test_answer_checked(
    hass: HomeAssistant, ai_on: MockConfigEntry, stand_in: StandInTask, send: Send
) -> None:
    """Picks must be windows SailCast sent, and notes days it sent."""
    stand_in.answer = json.dumps(
        {
            "headline": "**Samstag** am Fluss.",
            "summary": "Zeile eins.\nZeile zwei.",
            "picks": [
                {"window": "w9", "why": "Gibt es nicht."},
                {"window": " w2 ", "why": "Mit dem Kreuzer."},
                {"window": "w2", "why": "Doppelt."},
                "kaputt",
                {"window": "w1"},
                {"window": "w3", "why": "Sonntag."},
            ],
            "days": [
                {"date": "2026-11-07", "note": "Gut."},
                {"date": "2026-11-07", "note": "Doppelt."},
                {"date": "2026-12-01", "note": "Nicht in dieser Woche."},
                {"date": "2026-11-08", "note": ""},
            ],
            "recheck": None,
        }
    )
    result = (await send("briefing", **WRITE))["result"]
    assert result["headline"] == "Samstag am Fluss."
    assert result["summary"] == "Zeile eins. Zeile zwei."
    assert result["picks"] == [
        SATURDAY_RIVER_CRUISER | {"why": "Mit dem Kreuzer."},
        SATURDAY_RIVER_KEELBOAT | {"why": ""},
        SUNDAY_RIVER_KEELBOAT | {"why": "Sonntag."},
    ]
    assert result["days"] == {"2026-11-07": "Gut."}
    assert result["recheck"] == ""


@pytest.mark.parametrize(
    "case",
    [
        ("Einfach Text.", "bad_answer"),
        (["eine", "Liste"], "bad_answer"),
        ({"summary": "Ohne Überschrift."}, "bad_answer"),
        (ANSWER | {"summary": "x" * 1000}, "bad_answer"),
        (ANSWER | {"headline": "  "}, "bad_answer"),
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
    """An answer that isn't a briefing, or a provider that fails, gives an error."""
    stand_in.answer, code = case
    assert (await send("briefing", **WRITE))["error"]["code"] == code
    assert ai_on.runtime_data.briefings.get(KEY) is None


async def test_nothing_to_brief(
    hass: HomeAssistant,
    ai_on: MockConfigEntry,
    stand_in: StandInTask,
    send: Send,
    freezer: FrozenDateTimeFactory,
) -> None:
    """There's no briefing for a sailor who isn't there, or once the week is over."""
    response = await send("briefing", **(WRITE | {"sailor": "sailor_kim"}))
    assert response["error"]["code"] == "not_found"
    freezer.move_to(datetime(2026, 11, 20, 18, tzinfo=UTC))
    assert (await send("briefing", **WRITE))["error"]["code"] == "not_found"
    assert stand_in.tasks == []


async def test_kept_through_restart(
    hass: HomeAssistant,
    ai_on: MockConfigEntry,
    stand_in: StandInTask,
    send: Send,
    hass_storage: dict[str, Any],
) -> None:
    """A briefing is saved a moment after it's written, and read after a restart."""
    result = (await send("briefing", **WRITE))["result"]
    assert briefing.STORAGE_KEY not in hass_storage
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=5))
    await hass.async_block_till_done()
    (saved,) = hass_storage[briefing.STORAGE_KEY]["data"]["briefings"]
    assert saved["key"] == list(KEY)
    # The hours it depends on are saved as one string.
    assert isinstance(saved["facts"], str)

    restarted = briefing.Briefings(hass)
    await restarted.async_load()
    kept = restarted.get(KEY)
    assert kept is not None
    assert kept.as_dict(kept.facts) == result


async def test_saved_briefings_checked(
    hass: HomeAssistant, hass_storage: dict[str, Any], freezer: FrozenDateTimeFactory
) -> None:
    """Old saved briefings, and unreadable ones, are left out."""
    freezer.move_to(datetime(2026, 11, 7, 18, tzinfo=UTC))
    saved = {
        "headline": "Samstag.",
        "summary": "Gut.",
        "picks": [],
        "days": {},
        "recheck": "",
        "made": "2026-11-07T08:00:00+00:00",
        "facts": "{}",
    }
    hass_storage[briefing.STORAGE_KEY] = {
        "version": briefing.STORAGE_VERSION,
        "key": briefing.STORAGE_KEY,
        "data": {
            "briefings": [
                {"key": list(KEY)} | saved,
                {"key": ["sailor_sam", "de"]}
                | saved
                | {"made": "2026-11-04T08:00:00+00:00"},
                {"key": ["sailor_sam", "en"]} | saved | {"facts": "kaputt"},
                {"key": ["sailor_kim"]} | saved,
            ]
        },
    }
    briefings = briefing.Briefings(hass)
    await briefings.async_load()
    kept = briefings.get(KEY)
    assert kept is not None
    assert kept.headline == "Samstag."
    assert briefings.get(("sailor_sam", "de")) is None
    assert briefings.get(("sailor_sam", "en")) is None


async def test_old_summaries_removed(
    hass: HomeAssistant,
    sailcast_entry: MockConfigEntry,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
) -> None:
    """The day summaries saved before the briefing are deleted."""
    hass_storage[briefing.OLD_STORAGE_KEY] = {
        "version": 1,
        "key": briefing.OLD_STORAGE_KEY,
        "data": {"summaries": []},
    }
    await set_up(hass, sailcast_entry, freezer)
    await hass.async_block_till_done()
    assert briefing.OLD_STORAGE_KEY not in hass_storage


def test_clean() -> None:
    """Answers lose Markdown, line breaks and surrounding quotes."""
    assert (
        ai.clean('"**Good** sailing.\n\nGusts later."', 100)
        == "Good sailing. Gusts later."
    )
    assert ai.clean("# Saturday\nLight air.", 100) == "Saturday Light air."
    assert ai.clean("", 100, required=False) == ""
    with pytest.raises(ai.BadAnswerError):
        ai.clean("", 100)
    with pytest.raises(ai.BadAnswerError):
        ai.clean("Too long.", 5)


def test_languages() -> None:
    """The AI is asked for each of SailCast's languages by name."""
    assert ai.language_name("pt-BR") == "Brazilian Portuguese"
    assert ai.language_name("de-CH") == "German"
    assert ai.language_name("eo") == "the language with the code eo"
    assert set(ai.LANGUAGES) == {
        *("en", "de", "fr", "nl", "es", "zh-Hans"),
        *("it", "pl", "sv", "ru", "cs", "pt-BR"),
    }


async def test_options(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """The AI briefing needs AI Task, and an AI task or Home Assistant's default."""
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

    # So will one picked here; turning the briefing off forgets it.
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
