"""Planned sails: sailing windows in your own calendar.

Windows go into a calendar that accepts new events, such as Local Calendar,
Google Calendar or CalDAV, one at a time from the panel or automatically.
Automatic adding puts each chosen day's best window in, at most one a day for
each sailor, and keeps it in step with the forecast: it moves the event when
the window shifts by 30 minutes or more and takes it out when the window goes
away. From 6 PM the evening before, it leaves the event alone and warns
instead. A day someone takes an automatic event out of isn't added again.

Every planned sail is watched. When its forecast gets worse (any hour below
good, or the score under 60), SailCast posts a notification and fires a
sailcast_planned_sail_changed event.

Events and notifications are written in Home Assistant's language, except an
event someone adds from the panel, which is in theirs.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import logging
import statistics
from typing import TYPE_CHECKING, Any, Final

from homeassistant.components import persistent_notification
from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEntityFeature,
    CalendarEvent,
)
from homeassistant.components.calendar.const import (
    DATA_COMPONENT,
    EVENT_DESCRIPTION,
    EVENT_END,
    EVENT_LOCATION,
    EVENT_START,
    EVENT_SUMMARY,
)
from homeassistant.const import WEEKDAYS
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util
from homeassistant.util.ulid import ulid_now

from .const import DOMAIN, SIGNAL_UPDATED
from .limits import Level
from .outlook import BoatOutlook, Results
from .profiles import AutoCalendar, Profiles, Sailor
from .rating import Reason
from .scoring import WINDOW_SCORE, Window, round_half_up
from .storage import PlannedSail, SailCastStore
from .summary import hours_between, summarize
from .timeline import HOUR
from .wording import Wording

if TYPE_CHECKING:
    from .coordinator import ResultsCoordinator

_LOGGER = logging.getLogger(__name__)

# Automatic events stay put from this time the evening before.
FREEZE_AT: Final = time(18)
# An automatic event moves when its window shifts by this much or more.
MOVE_AFTER: Final = timedelta(minutes=30)
# Planned sails are kept this long after they end.
KEEP_PAST: Final = timedelta(days=1)
# How far around a sail to look for its event in the calendar.
LOOK_AROUND: Final = timedelta(hours=12)

EVENT_PLANNED_SAIL_CHANGED: Final = "sailcast_planned_sail_changed"


@dataclass(frozen=True, slots=True)
class SailStatus:
    """How a planned sail's forecast looks now, for its hours still to come.

    `level` is the worst rating and `score` the average. Both are None when
    there's no forecast for those hours.
    """

    level: Level | None
    score: int | None
    reasons: tuple[Reason, ...] = ()

    @property
    def worse(self) -> bool:
        """Return whether the sail no longer looks good."""
        if self.level is None:
            return False
        return self.level > Level.GOOD or (
            self.score is not None and self.score < WINDOW_SCORE
        )

    def as_dict(self) -> dict[str, Any]:
        """Return the status for the panel."""
        return {
            "rating": None if self.level is None else self.level.key,
            "score": self.score,
            "worse": self.worse,
            "reasons": [reason.as_dict() for reason in self.reasons],
        }


def sail_status(sail: PlannedSail, results: Results, now: datetime) -> SailStatus:
    """Return a planned sail's status from the latest results."""
    outlook = results.outlook(sail.sailor, sail.spot)
    boat = (
        next((item for item in outlook.boats if item.boat.id == sail.boat), None)
        if outlook
        else None
    )
    if boat is None:
        return SailStatus(None, None)
    items = [
        item
        for item in boat.hours
        if item.score is not None
        and item.hour.start < sail.end
        and item.hour.start + HOUR > max(sail.start, now)
    ]
    if not items:
        return SailStatus(None, None)
    worst = max(items, key=lambda item: item.rating.level)
    score = round_half_up(statistics.fmean(item.score or 0 for item in items))
    return SailStatus(worst.rating.level, score, worst.rating.reasons)


def calendar_entity(hass: HomeAssistant, entity_id: str) -> CalendarEntity | None:
    """Return a calendar entity, if it's loaded."""
    if (component := hass.data.get(DATA_COMPONENT)) is None:
        return None
    return component.get_entity(entity_id)


def supports(entity: CalendarEntity, feature: CalendarEntityFeature) -> bool:
    """Return whether a calendar can do something to its events."""
    return bool((entity.supported_features or 0) & feature)


class Planner:
    """Adds, watches and takes out the planned sails of one SailCast entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        store: SailCastStore,
        profiles: Profiles,
        results: ResultsCoordinator,
    ) -> None:
        """Set up the planner."""
        self.hass = hass
        self.store = store
        self.profiles = profiles
        self.results = results
        self._lock = asyncio.Lock()

    def status(self, sail: PlannedSail) -> SailStatus:
        """Return a planned sail's status now."""
        return sail_status(sail, self.results.data, dt_util.utcnow())

    def writable(self, entity_id: str) -> CalendarEntity:
        """Return a calendar that accepts new events, or raise."""
        entity = calendar_entity(self.hass, entity_id)
        if entity is None or not supports(entity, CalendarEntityFeature.CREATE_EVENT):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="calendar_read_only",
                translation_placeholders={"calendar": entity_id},
            )
        return entity

    async def async_add(
        self,
        *,
        sailor: str,
        boat: str,
        spot: str,
        calendar: str,
        start: datetime,
        end: datetime,
        title: str,
        watch: bool,
        user: str | None,
        language: str | None = None,
    ) -> PlannedSail:
        """Add an event to a calendar and start watching its forecast.

        Its description is in `language`, or Home Assistant's.
        """
        entity = self.writable(calendar)
        wording = await Wording.async_load(self.hass, language)
        sail = PlannedSail(
            id=ulid_now(),
            sailor=sailor,
            boat=boat,
            spot=spot,
            calendar=calendar,
            start=dt_util.as_utc(start),
            end=dt_util.as_utc(end),
            title=title,
            watch=watch,
            user=user,
        )
        # Warnings are about changes from here on.
        status = self.status(sail)
        sail.score, sail.worse = status.score, status.worse
        async with self._lock:
            await self._async_create_event(entity, sail, wording)
            self.store.add(sail)
        self._async_signal()
        return sail

    async def async_remove(self, sail: PlannedSail) -> bool:
        """Take an event out of its calendar and stop watching it.

        Returns whether the event was deleted. Calendars that can't delete
        events, such as CalDAV, keep it; SailCast only stops watching. An
        automatic event's day isn't added again.
        """
        async with self._lock:
            deleted = await self._async_delete_event(sail)
            if sail.auto:
                self.store.skip(sail.sailor, self._local_date(sail.start))
            self.store.remove(sail.id)
        self._async_dismiss(sail)
        self._async_signal()
        return deleted

    async def async_sync(self) -> None:
        """Keep automatic events in step and check every sail's forecast."""
        wording = await Wording.async_load(self.hass)
        async with self._lock:
            now = dt_util.utcnow()
            changed = self._forget_stale(now)
            for sailor in self.profiles.sailors.values():
                if sailor.auto_calendar and sailor.boats:
                    try:
                        changed |= await self._async_sync_auto(
                            sailor, sailor.auto_calendar, now, wording
                        )
                    except HomeAssistantError as err:
                        _LOGGER.warning(
                            "Couldn't update %s's automatic calendar: %s",
                            sailor.name,
                            err,
                        )
            changed |= self._watch(now, wording)
        if changed:
            self._async_signal()

    def _forget_stale(self, now: datetime) -> bool:
        """Drop sails long past, or whose sailor, boat or spot is gone."""
        profiles = self.profiles
        gone = [
            sail
            for sail in self.store.planned
            if sail.end < now - KEEP_PAST
            or sail.sailor not in profiles.sailors
            or sail.boat not in profiles.boats
            or sail.spot not in profiles.spots
        ]
        for sail in gone:
            self.store.remove(sail.id)
            self._async_dismiss(sail)
        self.store.forget_before(self._local_date(now))
        return bool(gone)

    async def _async_sync_auto(
        self, sailor: Sailor, auto: AutoCalendar, now: datetime, wording: Wording
    ) -> bool:
        """Add, move or take out a sailor's automatic events."""
        entity = calendar_entity(self.hass, auto.calendar)
        if entity is None or not supports(entity, CalendarEntityFeature.CREATE_EVENT):
            return False
        zone = dt_util.get_default_time_zone()
        today = now.astimezone(zone).date()
        changed = False
        for offset in range(auto.ahead + 1):
            day = today + timedelta(days=offset)
            if WEEKDAYS[day.weekday()] not in auto.days or day in self.store.skipped(
                sailor.id
            ):
                continue
            best = self._best_window(sailor, auto, day, now)
            existing = next(
                (
                    sail
                    for sail in self.store.planned
                    if sail.auto
                    and sail.sailor == sailor.id
                    and self._local_date(sail.start) == day
                ),
                None,
            )
            if existing is None:
                if best is not None:
                    spot, window = best
                    sail = PlannedSail(
                        id=ulid_now(),
                        sailor=sailor.id,
                        boat=sailor.boats[0],
                        spot=spot,
                        calendar=auto.calendar,
                        start=window.start,
                        end=window.end,
                        title=self._title(spot, wording),
                        auto=True,
                        score=window.score,
                    )
                    await self._async_create_event(entity, sail, wording)
                    self.store.add(sail)
                    changed = True
                continue
            if not await self._async_still_there(entity, existing):
                # Taken out in the calendar app, so it stays out.
                self.store.skip(sailor.id, day)
                self.store.remove(existing.id)
                self._async_dismiss(existing)
                changed = True
                continue
            frozen = now >= datetime.combine(day - timedelta(days=1), FREEZE_AT, zone)
            if frozen or existing.start <= now or existing.calendar != auto.calendar:
                # Leave it alone; watching warns if its forecast gets worse.
                continue
            if best is None:
                if supports(entity, CalendarEntityFeature.DELETE_EVENT):
                    await self._async_delete_event(existing)
                    self.store.remove(existing.id)
                    self._async_dismiss(existing)
                    changed = True
                continue
            spot, window = best
            if (
                spot != existing.spot
                or abs(window.start - existing.start) >= MOVE_AFTER
                or abs(window.end - existing.end) >= MOVE_AFTER
            ):
                changed |= await self._async_move(
                    entity, existing, spot, window, wording
                )
        return changed

    def _best_window(
        self, sailor: Sailor, auto: AutoCalendar, day: date, now: datetime
    ) -> tuple[str, Window] | None:
        """Return the day's best window that's still to come, across the spots."""
        best: tuple[str, Window] | None = None
        for spot in auto.spots:
            outlook = self.results.data.outlook(sailor.id, spot)
            boat: BoatOutlook | None = outlook.default if outlook else None
            if boat is None:
                continue
            for day_outlook in boat.days:
                if day_outlook.daylight.date != day:
                    continue
                for window in day_outlook.windows:
                    if (
                        window.score >= auto.min_score
                        and window.start > now
                        and (best is None or window.average > best[1].average)
                    ):
                        best = (spot, window)
        return best

    async def _async_move(
        self,
        entity: CalendarEntity,
        sail: PlannedSail,
        spot: str,
        window: Window,
        wording: Wording,
    ) -> bool:
        """Move an automatic event to a new window, if the calendar allows."""
        old = (sail.start, sail.end, sail.spot, sail.title)
        sail.start, sail.end, sail.spot = window.start, window.end, spot
        sail.title = self._title(spot, wording)
        sail.score, sail.worse = window.score, False
        if sail.uid and supports(entity, CalendarEntityFeature.UPDATE_EVENT):
            await entity.async_update_event(
                sail.uid, self._event(sail, wording), recurrence_id=sail.recurrence_id
            )
        elif sail.uid and supports(entity, CalendarEntityFeature.DELETE_EVENT):
            await entity.async_delete_event(sail.uid, recurrence_id=sail.recurrence_id)
            await self._async_create_event(entity, sail, wording)
        else:
            sail.start, sail.end, sail.spot, sail.title = old
            return False
        self._async_dismiss(sail)
        self.store.async_changed()
        return True

    def _watch(self, now: datetime, wording: Wording) -> bool:
        """Notice planned sails whose forecast got worse, or better again."""
        changed = False
        for sail in self.store.planned:
            if sail.end <= now:
                continue
            status = sail_status(sail, self.results.data, now)
            if status.level is None or status.worse == sail.worse:
                continue
            sail.worse = status.worse
            changed = True
            if not sail.watch:
                continue
            if status.worse:
                self._async_notify(sail, status, wording)
            else:
                self._async_dismiss(sail)
        if changed:
            self.store.async_changed()
        return changed

    async def _async_create_event(
        self, entity: CalendarEntity, sail: PlannedSail, wording: Wording
    ) -> None:
        """Add a sail's event, then find it again to learn its ID."""
        await entity.async_create_event(**self._event(sail, wording))
        try:
            events = await _async_events(self.hass, entity, sail, timedelta(minutes=1))
        except HomeAssistantError:
            return
        if found := _find(events, sail):
            sail.uid, sail.recurrence_id = found.uid, found.recurrence_id

    async def _async_delete_event(self, sail: PlannedSail) -> bool:
        """Delete a sail's event if its calendar allows, and say if it did."""
        entity = calendar_entity(self.hass, sail.calendar)
        if (
            entity is None
            or not sail.uid
            or not supports(entity, CalendarEntityFeature.DELETE_EVENT)
        ):
            return False
        try:
            await entity.async_delete_event(sail.uid, recurrence_id=sail.recurrence_id)
        except (HomeAssistantError, ValueError) as err:
            # Most likely deleted in the calendar app already.
            _LOGGER.debug("Couldn't delete %s from %s: %s", sail.id, sail.calendar, err)
            return False
        return True

    async def _async_still_there(
        self, entity: CalendarEntity, sail: PlannedSail
    ) -> bool:
        """Return whether a sail's event is still in its calendar."""
        try:
            events = await _async_events(self.hass, entity, sail, LOOK_AROUND)
        except HomeAssistantError:
            return True
        return _find(events, sail) is not None

    def _event(self, sail: PlannedSail, wording: Wording) -> dict[str, Any]:
        """Return a sail's event, as the calendar's create and update take it."""
        return {
            EVENT_START: dt_util.as_local(sail.start),
            EVENT_END: dt_util.as_local(sail.end),
            EVENT_SUMMARY: sail.title,
            EVENT_DESCRIPTION: self._describe(sail, wording),
            EVENT_LOCATION: self.profiles.spots[sail.spot].name,
        }

    def _title(self, spot: str, wording: Wording) -> str:
        return wording.text("event_title", spot=self.profiles.spots[spot].name)

    def _describe(self, sail: PlannedSail, wording: Wording) -> str:
        """Describe a sail's forecast as it is now, and how to find it again."""
        profiles = self.profiles
        sailor, boat = profiles.sailors[sail.sailor], profiles.boats[sail.boat]
        made = dt_util.utcnow()
        lines = [
            wording.text(
                "forecast_for",
                sailor=sailor.name,
                boat=boat.name,
                date=wording.date(made),
                time=wording.clock(made),
            )
        ]
        conditions = self.results.data.conditions.get(sail.spot)
        hours = (
            hours_between(conditions.hours, sail.start, sail.end) if conditions else []
        )
        if (summary := summarize(hours)) is not None:
            status = self.status(sail)
            if status.score is not None:
                lines.append(
                    wording.text(
                        "score", score=status.score, band=wording.band(status.score)
                    )
                )
            lines.append(
                wording.text(
                    "wind",
                    direction=wording.compass(summary.direction),
                    wind=wording.range(summary.wind_low, summary.wind_high),
                    gust=wording.number(summary.gust),
                )
            )
            if summary.waves is not None:
                lines.append(
                    wording.text("waves", waves=wording.heights(*summary.waves))
                )
        if conditions is not None:
            lines.extend(
                wording.text(
                    "high_tide" if event.high else "low_tide",
                    time=wording.clock(event.time),
                )
                for event in conditions.tide_events
                if sail.start <= event.time <= sail.end
            )
            if day := next(
                (
                    day
                    for day in conditions.days
                    if day.date == self._local_date(sail.start)
                ),
                None,
            ):
                lines.append(wording.text("sunset", time=wording.clock(day.sunset)))
        lines.append(wording.text("check_again"))
        return wording.join(lines) + "\n\n" + wording.text("added_by", id=sail.id)

    @callback
    def _async_notify(
        self, sail: PlannedSail, status: SailStatus, wording: Wording
    ) -> None:
        """Tell everyone a planned sail's forecast got worse."""
        profiles = self.profiles
        sailor, spot = profiles.sailors[sail.sailor], profiles.spots[sail.spot]
        message = wording.text(
            "changed",
            sailor=sailor.name,
            spot=spot.name,
            date=wording.date(sail.start),
            start=wording.clock(sail.start),
            end=wording.clock(sail.end),
            level=wording.level(status.level or Level.CAUTION),
            score=status.score,
        )
        persistent_notification.async_create(
            self.hass,
            message,
            title=wording.text("changed_title"),
            notification_id=f"{DOMAIN}_{sail.id}",
        )
        self.hass.bus.async_fire(
            EVENT_PLANNED_SAIL_CHANGED,
            {
                "sailor": sailor.name,
                "spot": spot.name,
                "boat": profiles.boats[sail.boat].name,
                "start": sail.start.isoformat(),
                "end": sail.end.isoformat(),
                "calendar": sail.calendar,
                "title": sail.title,
                "rating": status.level.key if status.level is not None else None,
                "score": status.score,
                "automatic": sail.auto,
                "message": message,
            },
        )

    @callback
    def _async_dismiss(self, sail: PlannedSail) -> None:
        persistent_notification.async_dismiss(self.hass, f"{DOMAIN}_{sail.id}")

    @callback
    def _async_signal(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)

    @staticmethod
    def _local_date(when: datetime) -> date:
        return dt_util.as_local(when).date()


async def _async_events(
    hass: HomeAssistant, entity: CalendarEntity, sail: PlannedSail, around: timedelta
) -> list[CalendarEvent]:
    """Return a calendar's events around a sail.

    Calendars are asked in local time, as Home Assistant's calendar does;
    Local Calendar finds nothing when asked in UTC.
    """
    return await entity.async_get_events(
        hass,
        dt_util.as_local(sail.start - around),
        dt_util.as_local(sail.end + around),
    )


def _find(events: Sequence[CalendarEvent], sail: PlannedSail) -> CalendarEvent | None:
    """Return a sail's event: the one with its ID, or with SailCast's in its text.

    The description's last line names the sail's ID in any language.
    """
    for event in events:
        if (sail.uid and event.uid == sail.uid) or sail.id in (event.description or ""):
            return event
    return None
