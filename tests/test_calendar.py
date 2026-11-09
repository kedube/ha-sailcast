"""Tests for each sailor's read-only sailing calendar."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry


async def events(hass: HomeAssistant, entity_id: str) -> list[dict[str, str]]:
    """Return a calendar's events for the coming week."""
    response = await hass.services.async_call(
        "calendar",
        "get_events",
        {
            "entity_id": entity_id,
            "start_date_time": datetime(2026, 11, 2, tzinfo=UTC),
            "end_date_time": datetime(2026, 11, 10, tzinfo=UTC),
        },
        blocking=True,
        return_response=True,
    )
    assert isinstance(response, dict)
    return response[entity_id]["events"]


async def test_window_under_way(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    """The calendar is on during a window, showing that window."""
    state = hass.states.get("calendar.sam_sailing")
    assert state.state == "on"
    assert state.attributes["message"] == "River: Keelboat"
    assert state.attributes["location"] == "River"


async def test_weekend_sailor(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    """A weekend sailor's windows fall on the weekend, in each of their boats."""
    week = await events(hass, "calendar.alex_sailing")
    assert hass.states.get("calendar.alex_sailing").state == "off"
    assert week
    days = {datetime.fromisoformat(event["start"]).strftime("%a") for event in week}
    assert days <= {"Sat", "Sun"}
    assert {event["summary"] for event in week} >= {"River: Keelboat"}
    saturday = next(event for event in week if event["start"].startswith("2026-11-07"))
    assert saturday["description"] == (
        "1 PM to 4:53 PM, score 80 (great). NW 5 to 6 kt, gusts to 15 kt.\n\n"
        "SailCast is advisory: check the latest forecast and official warnings "
        "before you go."
    )
    # Windows end at sunset.
    assert saturday["end"] == "2026-11-07T16:53:00-08:00"
