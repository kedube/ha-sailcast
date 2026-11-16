"""Tests for planned sails: calendar events added, watched, moved and taken out.

Events go into a real Local Calendar. Two stand-in calendars behave like
Google Calendar (which can't update events) and CalDAV (which can only add
them), and a flaky one fails when asked to.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEntityFeature,
    CalendarEvent,
)
from homeassistant.components.calendar.const import (
    DATA_COMPONENT,
    EVENT_END,
    EVENT_START,
)
from homeassistant.components.persistent_notification import (
    _async_get_or_create_notifications,
    async_create,
)
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant.common import MockConfigEntry, async_capture_events
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from custom_components.sailcast.const import DOMAIN, NAME
from custom_components.sailcast.planner import EVENT_PLANNED_SAIL_CHANGED, Planner
from custom_components.sailcast.scoring import Window
from custom_components.sailcast.storage import DATA_STORE, PlannedSail
from custom_components.sailcast.wording import Wording

from .conftest import BAY, CRUISER, HARBOR, KEELBOAT, RECORDED, RIVER, SAILOR

SATURDAY = datetime(2026, 11, 7, 21, tzinfo=UTC)
SATURDAY_END = datetime(2026, 11, 8, 0, 53, tzinfo=UTC)
SUNDAY = datetime(2026, 11, 8, 21, tzinfo=UTC)
SUNDAY_END = datetime(2026, 11, 9, tzinfo=UTC)
AUTO = {
    "calendar": "calendar.family",
    "days": ["sat", "sun"],
    "min_score": 60,
    "ahead": 6,
    "spots": ["spot_harbor", "spot_bay", "spot_river"],
}
# Saturday's automatic event, in the flaky calendar.
FLAKY = AUTO | {"calendar": "calendar.flaky", "days": ["sat"]}
# Saturday's window an hour later.
LATER = Window(
    start=SATURDAY + timedelta(hours=1), end=SATURDAY_END, average=75, hours=2
)


class StandInCalendar(CalendarEntity):
    """A calendar kept in memory that can do only some things to its events."""

    def __init__(self, name: str, features: CalendarEntityFeature) -> None:
        """Set up the calendar."""
        self._attr_name = name
        self._attr_supported_features = features
        self.events: list[CalendarEvent] = []

    @property
    def event(self) -> CalendarEvent | None:
        """Return no current event."""
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return the events between two times."""
        return [
            event
            for event in self.events
            if event.start_datetime_local < end_date
            and event.end_datetime_local > start_date
        ]

    async def async_create_event(self, **kwargs: Any) -> None:
        """Add an event."""
        self.events.append(
            CalendarEvent(
                start=kwargs["dtstart"],
                end=kwargs["dtend"],
                summary=kwargs["summary"],
                description=kwargs.get("description"),
                location=kwargs.get("location"),
                uid=f"event-{len(self.events)}",
            )
        )

    async def async_delete_event(
        self,
        uid: str,
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        """Delete an event."""
        self.events = [event for event in self.events if event.uid != uid]


class FlakyCalendar(StandInCalendar):
    """A stand-in calendar that can update events, and fails when asked to.

    `failing` has what it fails at: "create", "update", "delete" or "get".
    With a `gate`, adding an event waits for it.
    """

    def __init__(self, name: str, features: CalendarEntityFeature) -> None:
        """Set up the calendar."""
        super().__init__(name, features)
        self.failing: set[str] = set()
        self.gate: asyncio.Event | None = None
        self.adding = False

    def _check(self, action: str) -> None:
        if action in self.failing:
            raise HomeAssistantError(f"Couldn't {action}")

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return the events between two times."""
        self._check("get")
        return await super().async_get_events(hass, start_date, end_date)

    async def async_create_event(self, **kwargs: Any) -> None:
        """Add an event, once the gate opens."""
        self._check("create")
        self.adding = True
        if self.gate is not None:
            await self.gate.wait()
        await super().async_create_event(**kwargs)

    async def async_update_event(
        self,
        uid: str,
        event: dict[str, Any],
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        """Move an event."""
        self._check("update")
        self.events = [
            dataclasses.replace(item, start=event[EVENT_START], end=event[EVENT_END])
            if item.uid == uid
            else item
            for item in self.events
        ]

    async def async_delete_event(
        self,
        uid: str,
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        """Delete an event."""
        self._check("delete")
        await super().async_delete_event(uid, recurrence_id, recurrence_range)


ALL_CHANGES = (
    CalendarEntityFeature.CREATE_EVENT
    | CalendarEntityFeature.UPDATE_EVENT
    | CalendarEntityFeature.DELETE_EVENT
)


async def flaky(
    hass: HomeAssistant,
    features: CalendarEntityFeature = ALL_CHANGES,
    failing: set[str] | None = None,
) -> FlakyCalendar:
    """Add the flaky calendar, as calendar.flaky."""
    calendar = FlakyCalendar("Flaky", features)
    calendar.failing = failing or set()
    await hass.data[DATA_COMPONENT].async_add_entities([calendar])
    return calendar


def alex(**data: Any) -> ConfigSubentryData:
    """Return the weekend sailor with some settings changed."""
    return ConfigSubentryData(**(SAILOR | {"data": SAILOR["data"] | data}))


async def setup(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    sailor: ConfigSubentryData,
) -> MockConfigEntry:
    """Set up SailCast at the recorded time, and let planned sails settle."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=NAME,
        data={},
        subentries_data=[HARBOR, BAY, RIVER, KEELBOAT, CRUISER, sailor],
    )
    entry.add_to_hass(hass)
    freezer.move_to(RECORDED)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return entry


async def events(hass: HomeAssistant, entity_id: str) -> list[dict[str, Any]]:
    """Return a calendar's events over the recorded week."""
    response = await hass.services.async_call(
        "calendar",
        "get_events",
        {
            "start_date_time": RECORDED - timedelta(days=1),
            "end_date_time": RECORDED + timedelta(days=8),
        },
        target={"entity_id": entity_id},
        blocking=True,
        return_response=True,
    )
    return response[entity_id]["events"]  # type: ignore[index, no-any-return]


def planner(entry: MockConfigEntry) -> Planner:
    """Return the entry's planner."""
    return entry.runtime_data.planner  # type: ignore[no-any-return]


async def add(
    hass: HomeAssistant, entry: MockConfigEntry, calendar: str, **values: Any
) -> PlannedSail:
    """Add Saturday's window at the river to a calendar."""
    return await planner(entry).async_add(
        **(
            {
                "sailor": "sailor_alex",
                "boat": "boat_keelboat",
                "spot": "spot_river",
                "calendar": calendar,
                "start": SATURDAY,
                "end": SATURDAY_END,
                "title": "Sailing: River",
                "watch": True,
                "user": None,
            }
            | values
        )
    )


async def test_add_and_take_out(
    hass: HomeAssistant,
    family: str,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A window goes into the calendar with its forecast, and comes out again."""
    entry = await setup(hass, freezer, SAILOR)
    sail = await add(hass, entry, family)

    (event,) = await events(hass, family)
    assert event["summary"] == "Sailing: River"
    assert event["location"] == "River"
    assert datetime.fromisoformat(event["start"]) == SATURDAY
    assert datetime.fromisoformat(event["end"]) == SATURDAY_END
    description = event["description"]
    assert description.startswith(
        "SailCast forecast for Alex in the Keelboat, made Monday, Nov 2 at 2:36 PM."
    )
    assert "Score 80 (great)." in description
    assert "Sunset 4:53 PM." in description
    assert description.endswith(f"\n\nAdded by SailCast ({sail.id})")
    assert sail.uid
    assert sail.score == 80
    assert hass.data[DATA_STORE].get(sail.id) is sail

    assert await planner(entry).async_remove(sail)
    assert await events(hass, family) == []
    assert hass.data[DATA_STORE].get(sail.id) is None


async def test_automatic_adding(
    hass: HomeAssistant,
    family: str,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Each chosen day's best window goes in, and only once."""
    entry = await setup(hass, freezer, alex(auto_calendar=AUTO))
    added = await events(hass, family)
    assert [(event["summary"], event["start"], event["end"]) for event in added] == [
        ("Sailing: River", "2026-11-07T13:00:00-08:00", "2026-11-07T16:53:00-08:00"),
        ("Sailing: River", "2026-11-08T13:00:00-08:00", "2026-11-08T16:00:00-08:00"),
    ]
    store = hass.data[DATA_STORE]
    assert [sail.auto for sail in store.planned] == [True, True]

    # Syncing again changes nothing.
    await planner(entry).async_sync()
    assert len(await events(hass, family)) == 2


async def test_automatic_adding_lowest_score(
    hass: HomeAssistant,
    family: str,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Only great windows go in when the sailor asks for 80 and up."""
    await setup(hass, freezer, alex(auto_calendar=AUTO | {"min_score": 80}))
    assert [event["start"] for event in await events(hass, family)] == [
        "2026-11-07T13:00:00-08:00"
    ]


async def test_automatic_event_moves(
    hass: HomeAssistant,
    family: str,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """An automatic event follows its window, and goes when the window does."""
    entry = await setup(hass, freezer, alex(auto_calendar=AUTO | {"days": ["sat"]}))
    later = Window(
        start=SATURDAY + timedelta(hours=1),
        end=SATURDAY_END,
        average=75,
        hours=2,
    )
    with patch.object(Planner, "_best_window", return_value=("spot_river", later)):
        await planner(entry).async_sync()
    (event,) = await events(hass, family)
    assert event["start"] == "2026-11-07T14:00:00-08:00"
    (sail,) = hass.data[DATA_STORE].planned
    assert sail.start == later.start
    assert sail.score == 75

    # A shift under 30 minutes isn't worth moving for.
    nudged = Window(
        start=later.start + timedelta(minutes=20), end=SATURDAY_END, average=75, hours=2
    )
    with patch.object(Planner, "_best_window", return_value=("spot_river", nudged)):
        await planner(entry).async_sync()
    assert (await events(hass, family))[0]["start"] == "2026-11-07T14:00:00-08:00"

    with patch.object(Planner, "_best_window", return_value=None):
        await planner(entry).async_sync()
    assert await events(hass, family) == []
    assert hass.data[DATA_STORE].planned == []


async def test_automatic_event_stays_from_the_evening_before(
    hass: HomeAssistant,
    family: str,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """From 6 PM the evening before, the event stays put whatever the forecast."""
    entry = await setup(hass, freezer, alex(auto_calendar=AUTO | {"days": ["sat"]}))
    # Friday 6:05 PM in San Diego.
    freezer.move_to(datetime(2026, 11, 7, 2, 5, tzinfo=UTC))
    with patch.object(Planner, "_best_window", return_value=None):
        await planner(entry).async_sync()
    assert len(await events(hass, family)) == 1


async def test_taken_out_in_the_calendar_app(
    hass: HomeAssistant,
    family: str,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A day whose automatic event was deleted elsewhere isn't added again."""
    entry = await setup(hass, freezer, alex(auto_calendar=AUTO | {"days": ["sat"]}))
    (sail,) = hass.data[DATA_STORE].planned
    calendar = hass.data[DATA_COMPONENT].get_entity(family)
    assert calendar is not None
    await calendar.async_delete_event(sail.uid)

    await planner(entry).async_sync()
    assert await events(hass, family) == []
    assert hass.data[DATA_STORE].planned == []
    assert hass.data[DATA_STORE].skipped("sailor_alex") == {SATURDAY.date()}


async def test_taken_out_in_the_panel(
    hass: HomeAssistant,
    family: str,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Taking an automatic event out in the panel keeps that day out."""
    entry = await setup(hass, freezer, alex(auto_calendar=AUTO))
    saturday = hass.data[DATA_STORE].planned[0]
    await planner(entry).async_remove(saturday)
    await planner(entry).async_sync()
    assert [event["start"] for event in await events(hass, family)] == [
        "2026-11-08T13:00:00-08:00"
    ]


async def test_calendars_that_cannot_update(
    hass: HomeAssistant,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Google Calendar moves by deleting and adding; CalDAV only warns."""
    entry = await setup(hass, freezer, SAILOR)
    google = StandInCalendar(
        "Google",
        CalendarEntityFeature.CREATE_EVENT | CalendarEntityFeature.DELETE_EVENT,
    )
    caldav = StandInCalendar("Club", CalendarEntityFeature.CREATE_EVENT)
    await hass.data[DATA_COMPONENT].async_add_entities([google, caldav])
    later = Window(
        start=SATURDAY + timedelta(hours=1), end=SATURDAY_END, average=75, hours=2
    )
    moved = planner(entry)

    for calendar, expected in ((google, later.start), (caldav, SATURDAY)):
        sail = await add(hass, entry, calendar.entity_id or "")
        sail.auto = True
        wording = await Wording.async_load(hass)
        assert await moved._async_move(
            calendar, sail, "spot_river", later, wording
        ) is (calendar is google)
        (event,) = calendar.events
        assert event.start == expected
        # CalDAV can't delete either, so taking it out only stops watching.
        assert await moved.async_remove(sail) is (calendar is google)
        assert hass.data[DATA_STORE].get(sail.id) is None


async def test_watching_a_sail(
    hass: HomeAssistant,
    family: str,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A sail whose forecast gets worse brings a notification and an event.

    Monday 2 PM to 4 PM at the harbor has 1.38 m waves, too much for the
    keelboat. A sail added then starts out worse, so it's set up as if the
    forecast had been good when it was added.
    """
    entry = await setup(hass, freezer, SAILOR)
    changes = async_capture_events(hass, EVENT_PLANNED_SAIL_CHANGED)
    sail = await add(
        hass,
        entry,
        family,
        spot="spot_harbor",
        start=datetime(2026, 11, 2, 22, tzinfo=UTC),
        end=datetime(2026, 11, 3, tzinfo=UTC),
        title="Sailing: Harbor",
    )
    assert sail.worse
    await planner(entry).async_sync()
    assert changes == []
    sail.worse = False

    await planner(entry).async_sync()
    await hass.async_block_till_done()
    assert sail.worse
    (change,) = changes
    notification = _async_get_or_create_notifications(hass)[f"{DOMAIN}_{sail.id}"]
    assert change.data | {"score": None} == {
        "sailor": "Alex",
        "spot": "Harbor",
        "boat": "Keelboat",
        "start": "2026-11-02T22:00:00+00:00",
        "end": "2026-11-03T00:00:00+00:00",
        "calendar": "calendar.family",
        "title": "Sailing: Harbor",
        "rating": "not_recommended",
        "score": None,
        "automatic": False,
        # The notification's text, for the blueprint to send on.
        "message": notification["message"],
    }
    assert notification["title"] == "SailCast: forecast changed"
    assert (
        "Alex's sail at Harbor on Monday, Nov 2, 2 PM to 4 PM"
        in (notification["message"])
    )

    # Once over, the sail is forgotten a day later.
    freezer.move_to(datetime(2026, 11, 4, 1, tzinfo=UTC))
    await planner(entry).async_sync()
    assert hass.data[DATA_STORE].get(sail.id) is None


async def test_unwatched_sail(
    hass: HomeAssistant,
    family: str,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A sail added without warnings turns worse quietly."""
    entry = await setup(hass, freezer, SAILOR)
    changes = async_capture_events(hass, EVENT_PLANNED_SAIL_CHANGED)
    sail = await add(
        hass,
        entry,
        family,
        spot="spot_harbor",
        start=datetime(2026, 11, 2, 22, tzinfo=UTC),
        end=datetime(2026, 11, 3, tzinfo=UTC),
        watch=False,
    )
    sail.worse = False
    await planner(entry).async_sync()
    assert sail.worse
    assert changes == []


async def test_failed_move_tried_again(
    hass: HomeAssistant,
    family: str,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A sail keeps its window when its event couldn't be moved, and moves later."""
    calendar = await flaky(hass)
    entry = await setup(hass, freezer, alex(auto_calendar=FLAKY))
    (sail,) = hass.data[DATA_STORE].planned
    calendar.failing = {"update"}
    with patch.object(Planner, "_best_window", return_value=("spot_river", LATER)):
        await planner(entry).async_sync()
        assert sail.start == SATURDAY
        assert calendar.events[0].start == SATURDAY

        calendar.failing = set()
        await planner(entry).async_sync()
    assert sail.start == LATER.start
    assert calendar.events[0].start == LATER.start


async def test_failed_move_after_delete(
    hass: HomeAssistant,
    family: str,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A sail whose event was deleted but not added again goes in again later.

    Its day isn't skipped, as no one took it out.
    """
    features = CalendarEntityFeature.CREATE_EVENT | CalendarEntityFeature.DELETE_EVENT
    calendar = await flaky(hass, features)
    entry = await setup(hass, freezer, alex(auto_calendar=FLAKY))
    store = hass.data[DATA_STORE]
    (sail,) = store.planned
    async_create(hass, "Worse", notification_id=f"{DOMAIN}_{sail.id}")
    calendar.failing = {"create"}
    with patch.object(Planner, "_best_window", return_value=("spot_river", LATER)):
        await planner(entry).async_sync()
    assert calendar.events == []
    assert store.planned == []
    assert store.skipped("sailor_alex") == set()
    assert f"{DOMAIN}_{sail.id}" not in _async_get_or_create_notifications(hass)

    calendar.failing = set()
    await planner(entry).async_sync()
    assert [event.start for event in calendar.events] == [SATURDAY]
    assert len(store.planned) == 1


async def test_changed_automatic_calendar(
    hass: HomeAssistant,
    family: str,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """An event in the calendar automatic events used to go into stays watched."""
    entry = await setup(hass, freezer, alex(auto_calendar=AUTO | {"days": ["sat"]}))
    calendar = await flaky(hass)
    subentry = entry.subentries["sailor_alex"]
    hass.config_entries.async_update_subentry(
        entry,
        subentry,
        data=dict(subentry.data) | {"auto_calendar": FLAKY},
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    store = hass.data[DATA_STORE]
    (sail,) = store.planned
    assert sail.calendar == family
    assert store.skipped("sailor_alex") == set()
    assert len(await events(hass, family)) == 1
    assert calendar.events == []


async def test_window_gone_but_event_stays(
    hass: HomeAssistant,
    family: str,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A sail whose event couldn't be taken out is kept, so it isn't added twice."""
    calendar = await flaky(hass)
    entry = await setup(hass, freezer, alex(auto_calendar=FLAKY))
    store = hass.data[DATA_STORE]
    calendar.failing = {"delete"}
    with patch.object(Planner, "_best_window", return_value=None):
        await planner(entry).async_sync()
    assert len(calendar.events) == 1
    assert len(store.planned) == 1

    calendar.failing = set()
    await planner(entry).async_sync()
    assert len(calendar.events) == 1
    with patch.object(Planner, "_best_window", return_value=None):
        await planner(entry).async_sync()
    assert calendar.events == []
    assert store.planned == []


async def test_event_id_learned_later(
    hass: HomeAssistant,
    family: str,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """An event that couldn't be found when it was added gets its ID later."""
    calendar = await flaky(hass, failing={"get"})
    entry = await setup(hass, freezer, alex(auto_calendar=FLAKY))
    (sail,) = hass.data[DATA_STORE].planned
    assert sail.uid is None

    calendar.failing = set()
    await planner(entry).async_sync()
    assert sail.uid == calendar.events[0].uid


async def test_cancelled_while_adding(
    hass: HomeAssistant,
    family: str,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """An event added while SailCast unloads is kept, and isn't added again."""
    calendar = await flaky(hass, failing={"create"})
    entry = await setup(hass, freezer, alex(auto_calendar=FLAKY))
    store = hass.data[DATA_STORE]
    assert store.planned == []

    calendar.failing, calendar.gate = set(), asyncio.Event()
    syncing = hass.async_create_task(planner(entry).async_sync())
    for _ in range(100):
        if calendar.adding:
            break
        await asyncio.sleep(0)
    assert calendar.adding
    # Unloading cancels the sync.
    syncing.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await syncing
    calendar.gate.set()
    for _ in range(10):
        await asyncio.sleep(0)
    assert len(calendar.events) == 1
    assert len(store.planned) == 1

    await planner(entry).async_sync()
    assert len(calendar.events) == 1


async def test_planners_take_turns(
    hass: HomeAssistant,
    family: str,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Planners share the store's lock, so a reloading entry's waits its turn."""
    entry = await setup(hass, freezer, SAILOR)
    store = hass.data[DATA_STORE]
    sail = await add(hass, entry, family)
    async with store.lock:
        removing = hass.async_create_task(planner(entry).async_remove(sail))
        for _ in range(20):
            await asyncio.sleep(0)
        assert not removing.done()
        assert store.get(sail.id) is sail
    assert await removing
    assert store.get(sail.id) is None


async def test_removed_boat(
    hass: HomeAssistant,
    family: str,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Automatic events in a boat that's gone are taken out for the next boat's."""
    entry = await setup(hass, freezer, alex(auto_calendar=AUTO))
    hass.config_entries.async_remove_subentry(entry, "boat_keelboat")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert [event["start"] for event in await events(hass, family)] == [
        "2026-11-07T14:00:00-08:00"
    ]
    (sail,) = hass.data[DATA_STORE].planned
    assert sail.boat == "boat_cruiser"


async def test_removed_boat_in_a_calendar_that_cannot_delete(
    hass: HomeAssistant,
    family: str,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """An event that can't be taken out keeps its day, so it isn't added twice."""
    club = StandInCalendar("Club", CalendarEntityFeature.CREATE_EVENT)
    await hass.data[DATA_COMPONENT].async_add_entities([club])
    entry = await setup(
        hass, freezer, alex(auto_calendar=AUTO | {"calendar": "calendar.club"})
    )
    assert len(club.events) == 2
    hass.config_entries.async_remove_subentry(entry, "boat_keelboat")
    await hass.async_block_till_done(wait_background_tasks=True)
    store = hass.data[DATA_STORE]
    assert len(club.events) == 2
    assert store.planned == []
    assert store.skipped("sailor_alex") == {SATURDAY.date(), SUNDAY.date()}
