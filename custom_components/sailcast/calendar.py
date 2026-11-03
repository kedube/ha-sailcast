"""Each sailor's sailing windows as a read-only calendar.

There's one event per window, spot and boat, always following the latest
forecast, so calendar triggers can say "an hour before". Each description
starts with a line on the window, in Home Assistant's language, which the
evening-before blueprint sends on.
"""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import ResultsCoordinator, SailCastConfigEntry
from .entity import SailorEntity, async_remove_stale
from .outlook import BoatOutlook
from .profiles import Sailor, Spot
from .scoring import Window
from .summary import hours_between, summarize
from .wording import Wording


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SailCastConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a calendar for each sailor."""
    data = entry.runtime_data
    added = []
    for sailor in data.profiles.sailors.values():
        async_add_entities(
            [SailingCalendar(data.results, sailor)], config_subentry_id=sailor.id
        )
        added.append(f"{sailor.id}_sailing")
    async_remove_stale(hass, entry, "calendar", added)


class SailingCalendar(SailorEntity, CalendarEntity):
    """A sailor's sailing windows, at every spot and in each of their boats."""

    def __init__(self, coordinator: ResultsCoordinator, sailor: Sailor) -> None:
        """Set up the calendar."""
        super().__init__(coordinator, sailor, "sailing")

    def _events(self) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        if (wording := self.coordinator.wording) is None:
            return events
        for outlook in self.coordinator.data.outlooks.values():
            if outlook.sailor.id != self.sailor.id:
                continue
            for boat in outlook.boats:
                events.extend(
                    _event(outlook.spot, boat, window, wording)
                    for day in boat.days
                    for window in day.windows
                )
        return sorted(events, key=lambda event: (event.start, event.summary))

    @property
    def event(self) -> CalendarEvent | None:
        """Return the window under way, or the next one."""
        now = dt_util.utcnow()
        return next((event for event in self._events() if event.end > now), None)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return the windows between two times."""
        return [
            event
            for event in self._events()
            if event.start < end_date and event.end > start_date
        ]


def _event(
    spot: Spot, boat: BoatOutlook, window: Window, wording: Wording
) -> CalendarEvent:
    summary = summarize(
        hours_between([item.hour for item in boat.hours], window.start, window.end)
    )
    lines = [
        wording.text(
            "window",
            start=wording.clock(window.start),
            end=wording.clock(window.end),
            score=window.score,
            band=wording.band(window.score),
        )
    ]
    if summary is not None:
        lines.append(
            wording.text(
                "wind",
                direction=wording.compass(summary.direction),
                wind=wording.range(summary.wind_low, summary.wind_high),
                gust=wording.number(summary.gust),
            )
        )
    return CalendarEvent(
        start=dt_util.as_local(window.start),
        end=dt_util.as_local(window.end),
        summary=f"{spot.name}: {boat.boat.name}",
        description=wording.join(lines) + "\n\n" + wording.text("advisory"),
        location=spot.name,
        uid=f"sailcast-{spot.id}-{boat.boat.id}-{window.start.isoformat()}",
    )
