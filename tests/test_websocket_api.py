"""Tests for the panel's WebSocket commands, through a real WebSocket client."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.auth.models import User
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker
from pytest_homeassistant.typing import MockHAClientWebSocket, WebSocketGenerator

from custom_components.sailcast.const import DOMAIN, SIGNAL_UPDATED, SUBENTRY_SAILOR
from custom_components.sailcast.storage import DATA_STORE
from custom_components.sailcast.wind import STOP_AT

from .conftest import HARBOR_POINT, RECORDED, mock_suggestions, mock_wind

type Send = Callable[..., Awaitable[dict[str, Any]]]

ALEX_RIVER = {"spot": "spot_river", "sailor": "sailor_alex"}


@pytest.fixture(autouse=True)
async def mock_http(hass: HomeAssistant) -> Any:
    """Serve real HTTP for the WebSocket client.

    The panel's module isn't built for tests, so serving it is skipped, and
    the frontend's package isn't installed.
    """
    hass.config.components.update({"frontend", "panel_custom"})
    assert await async_setup_component(hass, "http", {})
    hass.http.async_register_static_paths = AsyncMock()  # type: ignore[method-assign]
    return hass.http


@pytest.fixture
async def send(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> Callable[..., Awaitable[dict[str, Any]]]:
    """Return a function that sends a command as an administrator."""
    client = await hass_ws_client(hass)
    return _sender(client)


def _sender(client: MockHAClientWebSocket) -> Send:
    async def send(type_: str, **values: Any) -> dict[str, Any]:
        await client.send_json_auto_id({"type": f"sailcast/{type_}", **values})
        return await client.receive_json()  # type: ignore[no-any-return]

    return send


async def test_config(
    hass: HomeAssistant,
    family: str,
    loaded: MockConfigEntry,
    send: Send,
    hass_admin_user: User,
) -> None:
    """The panel gets the profiles, limits, calendars and people to link."""
    result = (await send("config"))["result"]
    assert [spot["name"] for spot in result["spots"]] == ["Bay", "Harbor", "River"]
    assert [sailor["name"] for sailor in result["sailors"]] == ["Alex", "Sam"]
    assert result["limits"]["small_keelboat"]["wind"] == [18, 25]
    assert result["skills"] == {"beginner": 10, "intermediate": 16, "advanced": None}
    # SailCast's own calendars are read-only, so only Family is offered.
    assert result["calendars"] == [
        {
            "entity_id": "calendar.family",
            "name": "Family",
            "via": "Local calendar",
            "update": True,
            "delete": True,
        }
    ]
    assert {"id": hass_admin_user.id, "name": hass_admin_user.name} in result["users"]


async def test_not_set_up(hass: HomeAssistant, send: Send) -> None:
    """Without SailCast set up, the panel is told so."""
    assert await async_setup_component(hass, DOMAIN, {})
    response = await send("config")
    assert response["error"] == {
        "code": "not_found",
        "message": "SailCast isn't set up",
    }


async def test_forecast(
    hass: HomeAssistant, loaded: MockConfigEntry, send: Send
) -> None:
    """The week from now on, with windows, ratings, summaries and advice."""
    result = (await send("forecast", **ALEX_RIVER))["result"]
    assert (result["spot"], result["sailor"], result["boat"]) == (
        "spot_river",
        "sailor_alex",
        "boat_keelboat",
    )
    assert result["now"] == RECORDED.isoformat()
    assert result["fetched"] == RECORDED.isoformat()
    # The forecast runs to 3 PM on the seventh day.
    assert len(result["hours"]) == 7 * 24 - 8
    assert result["sources"]["tide_station"] == {"id": "9410196", "name": None}
    assert result["sources"]["current_station"] is None

    days = result["days"]
    assert [day["date"] for day in days][:2] == ["2026-11-02", "2026-11-03"]
    # Alex sails weekends, so Monday has no score.
    assert days[0]["available"] is False
    assert days[0]["score"] is None
    saturday = days[5]
    assert saturday["windows"] == [
        {
            "start": "2026-11-07T21:00:00+00:00",
            "end": "2026-11-08T00:53:00+00:00",
            "score": 80,
            "hours": 4,
            # Light air: 5.4 to 6.2 kt costs 13 to 26 points an hour.
            "wind_low": 5.4,
            "wind_high": 6.2,
            "gust": 14.8,
            "direction": 298,
        }
    ]
    assert saturday["best"] == 0
    assert saturday["score"] == 80
    assert set(saturday["sizes"]) == {
        "dinghy",
        "small_keelboat",
        "cruiser",
        "large_cruiser",
    }
    assert saturday["advice"][0]["key"] == "wind"
    assert saturday["advice"][-1] == {
        "key": "sunset",
        "icon": "sunset",
        "values": {"time": "2026-11-08T00:53:00+00:00"},
        "hot": False,
    }
    hour = result["hours"][14]
    assert hour["time"] == "2026-11-02T22:00:00+00:00"
    assert set(hour) >= {"wind", "gust", "models", "rating", "score", "sizes"}


async def test_forecast_from_now_on(
    hass: HomeAssistant, loaded: MockConfigEntry, send: Send
) -> None:
    """Today's windows and score count only the hours still to come.

    Sam's river window ran from 11 AM, but at 2:36 PM it's under way from the
    2 PM hour.
    """
    result = (await send("forecast", spot="spot_river", sailor="sailor_sam"))["result"]
    (window,) = result["days"][0]["windows"]
    assert window["start"] == "2026-11-02T22:00:00+00:00"
    assert window["end"] == "2026-11-03T00:57:00+00:00"


async def test_forecast_unknown(
    hass: HomeAssistant, loaded: MockConfigEntry, send: Send
) -> None:
    """A spot or sailor without a forecast is an error."""
    response = await send("forecast", spot="spot_gone", sailor="sailor_alex")
    assert response["error"]["code"] == "not_found"


async def test_subscribe(hass: HomeAssistant, send: Send, hass_ws_client: Any) -> None:
    """Subscribers hear whenever SailCast's results or settings change."""
    assert await async_setup_component(hass, DOMAIN, {})
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "sailcast/subscribe"})
    assert (await client.receive_json())["success"]
    async_dispatcher_send(hass, SIGNAL_UPDATED)
    event = await client.receive_json()
    assert event["type"] == "event"
    assert "updated" in event["event"]


async def test_preferences(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    send: Send,
    hass_admin_user: User,
) -> None:
    """Preferences follow the user, starting with the sailor linked to them."""
    assert (await send("preferences/get"))["result"] == {}
    sailor = loaded.subentries["sailor_sam"]
    hass.config_entries.async_update_subentry(
        loaded, sailor, data=dict(sailor.data) | {"user": hass_admin_user.id}
    )
    await hass.async_block_till_done()
    assert (await send("preferences/get"))["result"] == {"sailor": "sailor_sam"}

    result = (await send("preferences/set", spot="spot_river", theme="night"))["result"]
    assert result == {"spot": "spot_river", "theme": "night"}
    assert (await send("preferences/set", theme=None))["result"] == {
        "spot": "spot_river"
    }
    assert (await send("preferences/get"))["result"] == {
        "spot": "spot_river",
        "sailor": "sailor_sam",
    }


async def test_save_boat(
    hass: HomeAssistant, loaded: MockConfigEntry, send: Send
) -> None:
    """A new boat is checked like the setup dialog checks it, then saved."""
    boat = {"size_class": "dinghy", "length": 4.2}
    taken = await send("settings/save", kind="boat", name="keelboat", data=boat)
    assert taken["result"] == {"errors": {"name": "name_taken"}}
    long = await send(
        "settings/save", kind="boat", name="Dinghy", data=boat | {"length": 60}
    )
    assert long["result"] == {"errors": {"length": "length_out_of_range"}}

    result = (await send("settings/save", kind="boat", name=" Dinghy ", data=boat))[
        "result"
    ]
    await hass.async_block_till_done()
    saved = loaded.subentries[result["profile"]]
    # Without the setting, a boat has no navigation lights.
    assert (saved.title, dict(saved.data)) == ("Dinghy", boat | {"lights": False})
    assert len(loaded.runtime_data.profiles.boats) == 3

    await send(
        "settings/save",
        kind="boat",
        profile=saved.subentry_id,
        name="Dinghy",
        data=boat | {"lights": True},
    )
    await hass.async_block_till_done()
    assert loaded.runtime_data.profiles.boats[saved.subentry_id].lights is True


async def test_save_sailor(
    hass: HomeAssistant, family: str, loaded: MockConfigEntry, send: Send
) -> None:
    """A sailor's hours, comfort and automatic adding are checked and kept in order.

    The days they sail are the ones with hours, each with its own.
    """
    data = {
        "skill": "beginner",
        "boats": ["boat_cruiser", "boat_keelboat", "boat_cruiser"],
        "hours": {"sun": {"start": "09:00"}, "fri": {"start": "17:30", "end": None}},
        "comfort": {"ideal_low": 6, "ideal_high": 12, "coldest": 8.5, "rain": "avoid"},
        "auto_calendar": {
            "calendar": "calendar.sam_sailing",
            "days": ["sun", "sat"],
            "min_score": 60,
            "ahead": 2,
            "spots": ["spot_river"],
        },
    }
    response = await send(
        "settings/save", kind="sailor", profile="sailor_sam", name="Sam", data=data
    )
    # SailCast's own calendars can't take new events.
    assert response["result"] == {"errors": {"calendar": "calendar_read_only"}}

    data["auto_calendar"]["calendar"] = family  # type: ignore[index]
    response = await send(
        "settings/save", kind="sailor", profile="sailor_sam", name="Sam", data=data
    )
    assert response["result"] == {"profile": "sailor_sam"}
    await hass.async_block_till_done()
    assert dict(loaded.subentries["sailor_sam"].data) == {
        "skill": "beginner",
        "boats": ["boat_cruiser", "boat_keelboat"],
        "days": ["fri", "sun"],
        "hours": {
            "fri": {"start": "17:30:00", "end": None},
            "sun": {"start": "09:00:00", "end": None},
        },
        "user": None,
        "comfort": {"ideal_low": 6, "ideal_high": 12, "coldest": 8.5, "rain": "avoid"},
        "auto_calendar": {
            "calendar": "calendar.family",
            "days": ["sat", "sun"],
            "min_score": 60,
            "ahead": 2,
            "spots": ["spot_river"],
        },
    }


async def test_save_spot(
    hass: HomeAssistant, loaded: MockConfigEntry, send: Send
) -> None:
    """A spot keeps its directions in compass order and its sources' names."""
    data = {
        "latitude": HARBOR_POINT[0],
        "longitude": HARBOR_POINT[1],
        "radius": 12_000,
        "water_type": "open_coast",
        "offshore": ["e", "ne"],
        "exposed": ["w", "sw"],
        "tide_station": "9410230",
        "source_names": {"tide_station": "La Jolla"},
    }
    result = (await send("settings/save", kind="spot", name="Cove", data=data))[
        "result"
    ]
    await hass.async_block_till_done()
    saved = dict(loaded.subentries[result["profile"]].data)
    assert saved["offshore"] == ["ne", "e"]
    assert saved["exposed"] == ["sw", "w"]
    assert saved["radius"] == 12_000.0
    assert saved["source_names"] == {"tide_station": "La Jolla"}
    assert (saved["current_station"], saved["marine_zone"]) == (None, None)
    assert saved["notes"] == ""

    # Notes are kept without the spaces around them, up to 500 characters.
    result = (
        await send(
            "settings/save",
            kind="spot",
            profile=result["profile"],
            name="Cove",
            data=data | {"notes": "  Kelp off the point.\n"},
        )
    )["result"]
    await hass.async_block_till_done()
    assert loaded.subentries[result["profile"]].data["notes"] == "Kelp off the point."
    response = await send(
        "settings/save", kind="spot", name="Wordy", data=data | {"notes": "x" * 501}
    )
    assert response["result"] == {"errors": {"notes": "notes_too_long"}}

    response = await send(
        "settings/save", kind="spot", name="Far", data=data | {"radius": 100}
    )
    assert response["result"] == {"errors": {"radius": "radius_out_of_range"}}
    response = await send(
        "settings/save", kind="spot", name="Bad", data=data | {"water_type": "pond"}
    )
    assert response["error"]["code"] == "invalid_format"


async def test_settings_for_administrators_only(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    hass_read_only_access_token: str,
) -> None:
    """Other users can read everything but change no settings."""
    send = _sender(await hass_ws_client(hass, hass_read_only_access_token))
    assert (await send("forecast", **ALEX_RIVER))["success"]
    response = await send(
        "settings/save", kind="boat", name="Dinghy", data={"size_class": "dinghy"}
    )
    assert response["error"]["code"] == "unauthorized"
    response = await send("settings/delete", kind="boat", profile="boat_keelboat")
    assert response["error"]["code"] == "unauthorized"


async def test_delete(hass: HomeAssistant, loaded: MockConfigEntry, send: Send) -> None:
    """Every sailor keeps a boat, and a removed sailor's sails are forgotten."""
    response = await send("settings/delete", kind="boat", profile="boat_keelboat")
    assert response["result"] == {"errors": {"base": "boat_in_use"}, "sailor": "Sam"}
    response = await send("settings/delete", kind="spot", profile="sailor_sam")
    assert response["error"]["code"] == "not_found"

    response = await send("settings/delete", kind=SUBENTRY_SAILOR, profile="sailor_sam")
    assert response["result"] == {"profile": "sailor_sam"}
    await hass.async_block_till_done()
    assert "sailor_sam" not in loaded.runtime_data.profiles.sailors
    response = await send("settings/delete", kind="boat", profile="boat_keelboat")
    assert response["result"] == {"profile": "boat_keelboat"}


async def test_sources(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    send: Send,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """The stations and zones near a pin, nearest first, with a suggestion."""
    mock_suggestions(aioclient_mock)
    result = (
        await send(
            "settings/sources", latitude=HARBOR_POINT[0], longitude=HARBOR_POINT[1]
        )
    )["result"]
    assert result["suggested"]["tide_station"] == result["tide_station"][0]["id"]
    assert result["tide_station"][0]["distance"] < result["tide_station"][1]["distance"]
    assert result["failed"] is False
    # Stations come with their positions, for the spot map; zones don't.
    station = result["tide_station"][0]
    assert isinstance(station["latitude"], float)
    assert isinstance(station["longitude"], float)
    assert result["marine_zone"][0]["latitude"] is None
    # The nearest buoy and airport are suggested too.
    assert [buoy["id"] for buoy in result["buoy"][:2]] == ["SDBC1", "LJAC1"]
    assert result["suggested"]["buoy"] == "SDBC1"
    assert result["airport"][0]["id"] == "KSAN"
    assert result["airport"][0]["name"] == "San Diego Intl Arpt"
    assert result["suggested"]["airport"] == "KSAN"


async def test_forecast_with_readings(
    hass: HomeAssistant, observed: MockConfigEntry, send: Send
) -> None:
    """The panel gets readings, how they moved the forecast, and the waves' source."""
    result = (await send("forecast", **ALEX_RIVER))["result"]
    assert result["sources"]["airport"] == {"id": "KSAN", "name": "San Diego Intl Arpt"}
    assert result["sources"]["buoy"] is None
    assert result["sources"]["sensors"] == {}
    wind = result["readings"]["fields"]["wind"]
    assert (wind["value"], wind["kind"], wind["station"]) == (8, "airport", "KSAN")
    assert result["readings"]["sources"] == [
        {"kind": "airport", "station": "KSAN", "newest": "2026-11-02T21:51:00+00:00"}
    ]
    assert {item["field"] for item in result["adjustments"]} >= {"wind", "temperature"}
    assert result["shoreline"]["on_water"] is True
    assert {hour["wave_source"] for hour in result["hours"]} == {"estimate"}
    now = next(
        hour for hour in result["hours"] if hour["time"] == "2026-11-02T22:00:00+00:00"
    )
    assert "wind" in now["adjusted"]
    assert now["visibility_measured"] is True


async def test_shoreline(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    send: Send,
    hass_ws_client: WebSocketGenerator,
    hass_read_only_access_token: str,
) -> None:
    """A pin's open water each way, for the spot editor; administrators only."""
    result = (await send("settings/shoreline", latitude=32.715, longitude=-117.18))[
        "result"
    ]
    assert result["on_water"] is True
    assert len(result["rays"]) == 120
    assert result["exposed"] == []
    land = (await send("settings/shoreline", latitude=32.68, longitude=-117.17))[
        "result"
    ]
    assert land["on_water"] is False
    reader = _sender(await hass_ws_client(hass, hass_read_only_access_token))
    response = await reader("settings/shoreline", latitude=32.715, longitude=-117.18)
    assert response["error"]["code"] == "unauthorized"


async def test_calendar_add_and_remove(
    hass: HomeAssistant, family: str, loaded: MockConfigEntry, send: Send
) -> None:
    """A window goes into a calendar as the user, and comes out again."""
    window = {
        **ALEX_RIVER,
        "boat": "boat_keelboat",
        "calendar": family,
        "start": "2026-11-07T21:00:00Z",
        "end": "2026-11-08T00:00:00Z",
        "title": "Sailing: River",
    }
    short = await send("calendar/add", **window | {"end": "2026-11-07T21:30:00Z"})
    assert short["error"]["code"] == "invalid_format"

    planned = (await send("calendar/add", **window))["result"]
    assert planned["start"] == "2026-11-07T21:00:00+00:00"
    assert planned["status"] == {
        "rating": "good",
        "score": 79,
        "worse": False,
        "reasons": [],
    }
    assert planned["can_delete"] is True
    listed = (await send("planned/list"))["result"]
    assert [sail["id"] for sail in listed["planned"]] == [planned["id"]]
    week = (await send("forecast", **ALEX_RIVER))["result"]
    assert [sail["id"] for sail in week["planned"]] == [planned["id"]]

    assert (await send("calendar/remove", planned=planned["id"]))["result"] == {
        "deleted": True
    }
    assert (await send("planned/list"))["result"]["planned"] == []


async def test_calendar_permissions(
    hass: HomeAssistant,
    family: str,
    loaded: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    hass_read_only_access_token: str,
) -> None:
    """Someone who can't change a calendar can't add to it through SailCast."""
    send = _sender(await hass_ws_client(hass, hass_read_only_access_token))
    response = await send(
        "calendar/add",
        **ALEX_RIVER,
        boat="boat_keelboat",
        calendar=family,
        start="2026-11-07T21:00:00Z",
        end="2026-11-08T00:00:00Z",
        title="Sailing",
    )
    assert response["error"]["code"] == "unauthorized"


async def test_skipped_days(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    send: Send,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The days a sailor took out can be let back in."""
    store = hass.data[DATA_STORE]
    store.skip("sailor_alex", datetime(2026, 11, 7, tzinfo=UTC).date())
    store.skip("sailor_alex", datetime(2026, 11, 8, tzinfo=UTC).date())
    listed = (await send("planned/list"))["result"]
    assert listed["skipped"]["sailor_alex"] == ["2026-11-07", "2026-11-08"]

    result = await send("planned/skipped", sailor="sailor_alex", days=["2026-11-08"])
    assert result["result"] == ["2026-11-08"]
    assert store.skipped("sailor_alex") == {datetime(2026, 11, 8, tzinfo=UTC).date()}


async def test_hours_for_a_date(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    send: Send,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A date can be free all day, not for sailing, or have hours of its own.

    Alex sails at weekends from 9 AM. Undoing a change brings those back.
    """

    async def day(when: str) -> dict[str, Any]:
        # The results are worked out again once the debouncer's second is up.
        freezer.tick(timedelta(seconds=2))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        week = (await send("forecast", **ALEX_RIVER))["result"]
        return next(item for item in week["days"] if item["date"] == when)

    friday = await day("2026-11-06")
    assert (friday["hours"], friday["changed"], friday["available"]) == (
        None,
        False,
        False,
    )
    result = await send("hours", sailor="sailor_alex", date="2026-11-06", hours={})
    assert result["result"] == {"date": "2026-11-06"}
    friday = await day("2026-11-06")
    assert friday["hours"] == {"start": None, "end": None}
    assert friday["changed"]
    assert friday["available"]

    await send("hours", sailor="sailor_alex", date="2026-11-07", hours="off")
    saturday = await day("2026-11-07")
    assert (saturday["hours"], saturday["changed"], saturday["available"]) == (
        None,
        True,
        False,
    )
    assert saturday["windows"] == []

    late = {"start": "12:00", "end": "10:00"}
    result = await send("hours", sailor="sailor_alex", date="2026-11-08", hours=late)
    assert result["result"] == {"errors": {"end": "end_before_start"}}
    morning = {"start": "10:00", "end": "12:00"}
    await send("hours", sailor="sailor_alex", date="2026-11-08", hours=morning)
    sunday = await day("2026-11-08")
    assert sunday["hours"] == {"start": "10:00:00", "end": "12:00:00"}
    # 10 AM to noon in San Diego, in UTC.
    assert all(
        window["start"] >= "2026-11-08T18:00:00+00:00"
        and window["end"] <= "2026-11-08T20:00:00+00:00"
        for window in sunday["windows"]
    )

    await send("hours", sailor="sailor_alex", date="2026-11-07", hours="usual")
    saturday = await day("2026-11-07")
    assert saturday["hours"] == {"start": "09:00:00", "end": None}
    assert not saturday["changed"]
    assert set(hass.data[DATA_STORE].hours("sailor_alex")) == {
        date(2026, 11, 6),
        date(2026, 11, 8),
    }

    response = await send("hours", sailor="sailor_alex", date="2026-11-01", hours="off")
    assert response["error"]["code"] == "invalid_format"
    response = await send("hours", sailor="sailor_gone", date="2026-11-07", hours="off")
    assert response["error"]["code"] == "not_found"


async def test_hours_for_a_date_by_their_sailor(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    hass_read_only_access_token: str,
    hass_read_only_user: User,
) -> None:
    """Other users can change the hours of the sailor linked to them, no one else's."""
    send = _sender(await hass_ws_client(hass, hass_read_only_access_token))
    response = await send("hours", sailor="sailor_alex", date="2026-11-07", hours="off")
    assert response["error"]["code"] == "unauthorized"

    subentry = loaded.subentries["sailor_alex"]
    hass.config_entries.async_update_subentry(
        loaded, subentry, data={**subentry.data, "user": hass_read_only_user.id}
    )
    await hass.async_block_till_done()
    response = await send("hours", sailor="sailor_alex", date="2026-11-07", hours="off")
    assert response["result"] == {"date": "2026-11-07"}
    assert hass.data[DATA_STORE].hours("sailor_alex") == {date(2026, 11, 7): None}


async def test_wind_grid(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    send: Send,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """The test spots' circles overlap, so they share one grid, fetched once."""
    mock_wind(aioclient_mock)
    before = aioclient_mock.call_count
    grid = (await send("wind_grid", spot="spot_river"))["result"]
    assert grid["spots"] == ["spot_bay", "spot_harbor", "spot_river"]
    assert (grid["rows"], grid["cols"]) == (15, 15)
    assert len(grid["speed"][0]) == len(grid["gust"][0]) == 225
    assert grid["times"][0] == "2026-11-02T22:00:00+00:00"
    assert grid["stale"] is False
    shared = (await send("wind_grid", spot="spot_harbor"))["result"]
    assert shared["fetched"] == grid["fetched"]
    assert aioclient_mock.call_count == before + 1
    assert loaded.runtime_data.budget.today >= 225

    response = await send("wind_grid", spot="spot_gone")
    assert response["error"]["code"] == "not_found"


async def test_wind_grid_budget(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    send: Send,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Near the day's limit, a grid that was never fetched can't be shown."""
    mock_wind(aioclient_mock)
    loaded.runtime_data.budget.add(STOP_AT)
    response = await send("wind_grid", spot="spot_river")
    assert response["error"]["code"] == "budget"


async def test_wind_view(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    send: Send,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A view the map's grid covers needs nothing new; a wider one gets a grid."""
    mock_wind(aioclient_mock)
    grid = (await send("wind_grid", spot="spot_river"))["result"]
    inside = {
        "south": grid["south"] + 0.05,
        "west": grid["west"] + 0.05,
        "north": grid["north"] - 0.05,
        "east": grid["east"] - 0.05,
    }
    reply = await send("wind_view", **inside, have=grid["id"])
    assert reply["result"] == {"grid": None, "retry": None}

    before = aioclient_mock.call_count
    wider = {
        "south": grid["south"] - 1,
        "west": grid["west"] - 1,
        "north": grid["north"] + 1,
        "east": grid["east"] + 1,
    }
    reply = (await send("wind_view", **wider, have=grid["id"]))["result"]
    assert reply["retry"] is None
    assert reply["grid"]["id"] != grid["id"]
    assert reply["grid"]["spots"] == ["spot_bay", "spot_harbor", "spot_river"]
    assert reply["grid"]["south"] <= wider["south"]
    assert aioclient_mock.call_count == before + 1

    response = await send("wind_view", south=1, west=1, north=0, east=2)
    assert response["error"]["code"] == "invalid_format"
