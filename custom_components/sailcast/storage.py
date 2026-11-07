"""What SailCast keeps between restarts for the panel and planned sails.

Preferences are kept for each Home Assistant user, so the panel opens on
their spot, sailor, boat, view and theme on every device. Planned sails are
the calendar events SailCast added, one at a time from the panel or
automatically, so it can watch their forecast and take them out again. Days
someone took an automatic event out of are kept too, so it isn't added again.
So are the hours a sailor set for single dates, such as a day off, until the
date has passed.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, fields
from datetime import date, datetime
from typing import Any, Final

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util.hass_dict import HassKey

from .const import CONF_END, CONF_START, DOMAIN
from .profiles import Hours

STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = f"{DOMAIN}.panel"
SAVE_DELAY: Final = 2.0

# The preferences the panel keeps for each user.
PREFERENCES: Final = ("spot", "sailor", "boat", "view", "theme", "calendar")

DATA_STORE: HassKey[SailCastStore] = HassKey(f"{DOMAIN}_store")


@dataclass(slots=True, kw_only=True)
class PlannedSail:
    """A calendar event SailCast added, and what it last knew of its forecast.

    `uid` and `recurrence_id` identify the event in its calendar, when the
    calendar says. `score` is the forecast's score when it was added, and
    `worse` whether its forecast has got worse since. `user` is who added it;
    automatic events have none.
    """

    id: str
    sailor: str
    boat: str
    spot: str
    calendar: str
    start: datetime
    end: datetime
    title: str
    auto: bool = False
    watch: bool = True
    user: str | None = None
    uid: str | None = None
    recurrence_id: str | None = None
    score: int | None = None
    worse: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Return the sail as JSON-ready data."""
        data = asdict(self)
        data["start"] = self.start.isoformat()
        data["end"] = self.end.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PlannedSail:
        """Read a saved sail, ignoring keys from other versions."""
        known = {field.name for field in fields(cls)}
        values = {key: value for key, value in data.items() if key in known}
        values["start"] = datetime.fromisoformat(data["start"])
        values["end"] = datetime.fromisoformat(data["end"])
        return cls(**values)


class SailCastStore:
    """Preferences, planned sails, skipped days and the hours set for dates.

    Each is saved shortly after a change.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Set up the store; call async_load before using it."""
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._preferences: dict[str, dict[str, str]] = {}
        self._planned: dict[str, PlannedSail] = {}
        self._skipped: dict[str, set[date]] = {}
        self._hours: dict[str, dict[date, Hours | None]] = {}

    async def async_load(self) -> None:
        """Read what was saved."""
        stored = await self._store.async_load() or {}
        self._preferences = {
            user: dict(values) for user, values in stored.get("preferences", {}).items()
        }
        self._planned = {
            data["id"]: PlannedSail.from_dict(data)
            for data in stored.get("planned", [])
        }
        self._skipped = {
            sailor: {date.fromisoformat(day) for day in days}
            for sailor, days in stored.get("skipped", {}).items()
        }
        self._hours = {
            sailor: {
                date.fromisoformat(day): (
                    None if times is None else Hours.from_data(times)
                )
                for day, times in days.items()
            }
            for sailor, days in stored.get("hours", {}).items()
        }

    def preferences(self, user: str) -> dict[str, str]:
        """Return a user's preferences."""
        return dict(self._preferences.get(user, {}))

    @callback
    def set_preferences(
        self, user: str, changes: Mapping[str, str | None]
    ) -> dict[str, str]:
        """Change some of a user's preferences; None removes one."""
        current = self._preferences.setdefault(user, {})
        for key, value in changes.items():
            if key not in PREFERENCES:
                continue
            if value is None:
                current.pop(key, None)
            else:
                current[key] = value
        self.async_changed()
        return dict(current)

    @property
    def planned(self) -> list[PlannedSail]:
        """Return every planned sail, earliest first."""
        return sorted(self._planned.values(), key=lambda sail: sail.start)

    def get(self, sail_id: str) -> PlannedSail | None:
        """Return a planned sail."""
        return self._planned.get(sail_id)

    @callback
    def add(self, sail: PlannedSail) -> None:
        """Keep a new planned sail."""
        self._planned[sail.id] = sail
        self.async_changed()

    @callback
    def remove(self, sail_id: str) -> PlannedSail | None:
        """Forget a planned sail."""
        sail = self._planned.pop(sail_id, None)
        self.async_changed()
        return sail

    def skipped(self, sailor: str) -> set[date]:
        """Return the days a sailor took an automatic event out of."""
        return set(self._skipped.get(sailor, ()))

    @callback
    def skip(self, sailor: str, day: date) -> None:
        """Remember not to add an automatic event on a day again."""
        self._skipped.setdefault(sailor, set()).add(day)
        self.async_changed()

    @callback
    def set_skipped(self, sailor: str, days: Iterable[date]) -> None:
        """Replace the days a sailor took out, so some can be added again."""
        self._skipped[sailor] = set(days)
        self.async_changed()

    def hours(self, sailor: str) -> dict[date, Hours | None]:
        """Return the hours a sailor set for single dates; None is not sailing."""
        return dict(self._hours.get(sailor, {}))

    @callback
    def set_hours(self, sailor: str, day: date, hours: Hours | None) -> None:
        """Set a sailor's hours for one date: None for not sailing."""
        self._hours.setdefault(sailor, {})[day] = hours
        self.async_changed()

    @callback
    def clear_hours(self, sailor: str, day: date) -> None:
        """Go back to a sailor's usual hours on a date."""
        self._hours.get(sailor, {}).pop(day, None)
        self.async_changed()

    @callback
    def forget_before(self, day: date) -> None:
        """Drop skipped days and the hours set for dates that have passed."""
        for sailor, days in self._skipped.items():
            self._skipped[sailor] = {kept for kept in days if kept >= day}
        for sailor, hours in self._hours.items():
            self._hours[sailor] = {
                kept: value for kept, value in hours.items() if kept >= day
            }

    @callback
    def forget_sailor(self, sailor: str) -> list[PlannedSail]:
        """Drop a removed sailor's sails, skipped days and hours; return the sails."""
        gone = [sail for sail in self._planned.values() if sail.sailor == sailor]
        for sail in gone:
            del self._planned[sail.id]
        self._skipped.pop(sailor, None)
        self._hours.pop(sailor, None)
        self.async_changed()
        return gone

    @callback
    def async_changed(self) -> None:
        """Save soon."""
        self._store.async_delay_save(self._data, SAVE_DELAY)

    async def async_remove(self) -> None:
        """Forget everything and delete the file, when SailCast is deleted."""
        self._preferences, self._planned, self._skipped = {}, {}, {}
        self._hours = {}
        await self._store.async_remove()

    def _data(self) -> dict[str, Any]:
        return {
            "preferences": self._preferences,
            "planned": [sail.as_dict() for sail in self.planned],
            "skipped": {
                sailor: sorted(day.isoformat() for day in days)
                for sailor, days in self._skipped.items()
                if days
            },
            "hours": {
                sailor: {
                    day.isoformat(): None
                    if value is None
                    else {CONF_START: value.start, CONF_END: value.end}
                    for day, value in sorted(hours.items())
                }
                for sailor, hours in self._hours.items()
                if hours
            },
        }
