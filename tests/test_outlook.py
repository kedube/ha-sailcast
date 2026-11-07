"""Tests for sailors' outlooks: which hours count, and boats with lights."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from custom_components.sailcast.outlook import BoatOutlook, SpotConditions, outlook
from custom_components.sailcast.profiles import (
    Boat,
    Hours,
    Sailor,
    SizeClass,
    Skill,
    Spot,
    WaterType,
)
from custom_components.sailcast.timeline import Daylight, Hour
from custom_components.sailcast.week import week

from .conftest import HARBOR_POINT

ZONE = ZoneInfo("America/Los_Angeles")
# A Saturday in San Diego, with sunrise at 6:10 AM and sunset at 4:50 PM.
DAY = Daylight(
    date(2026, 11, 7),
    datetime(2026, 11, 7, 14, 10, tzinfo=UTC),
    datetime(2026, 11, 8, 0, 50, tzinfo=UTC),
    ZONE,
)
SPOT = Spot(
    id="spot_harbor",
    name="Harbor",
    latitude=HARBOR_POINT[0],
    longitude=HARBOR_POINT[1],
    radius=10_000,
    water_type=WaterType.OPEN_COAST,
)
LIT = Boat(
    id="boat_lit", name="Lit", size_class=SizeClass.CRUISER, length=10.4, lights=True
)
UNLIT = Boat(id="boat_unlit", name="Unlit", size_class=SizeClass.CRUISER, length=10.4)
BOATS = {LIT.id: LIT, UNLIT.id: UNLIT}


def at(hour: int, minute: int = 0) -> datetime:
    """Return a local time on the Saturday; 24 is the midnight that ends it."""
    return datetime(2026, 11, 7, tzinfo=ZONE) + timedelta(hours=hour, minutes=minute)


def conditions() -> SpotConditions:
    """Return the Saturday's 24 hours: steady, mild and good for a cruiser."""
    hours = []
    for index in range(24):
        start = at(index).astimezone(UTC)
        hours.append(
            Hour(
                start=start,
                daylight=DAY.covers(start),
                wind=12.0,
                gust=14.0,
                wind_direction=270.0,
                temperature=18.0,
                visibility=20_000.0,
            )
        )
    return SpotConditions(spot=SPOT, hours=tuple(hours), days=(DAY,))


def sailor(start: str | None = None, end: str | None = None) -> Sailor:
    """Return a sailor free on Saturdays, between the times given."""
    return Sailor(
        id="sailor_alex",
        name="Alex",
        skill=Skill.INTERMEDIATE,
        boats=(LIT.id, UNLIT.id),
        week={"sat": Hours(start, end)},
    )


def spans(boat: BoatOutlook) -> list[tuple[datetime, datetime]]:
    """Return when a boat's windows on the Saturday start and end."""
    return [(window.start, window.end) for window in boat.days[0].windows]


def test_lights_count_every_hour() -> None:
    """With navigation lights, hours after dark count, so windows run past sunset."""
    lit, unlit = outlook(sailor(), conditions(), BOATS).boats
    assert all(item.score is not None and item.available for item in lit.hours)
    assert [item.score is not None for item in unlit.hours] == [
        item.hour.daylight for item in unlit.hours
    ]
    assert spans(lit) == [(at(0), at(24))]
    # Without lights, a missing start or end still means sunrise or sunset.
    assert spans(unlit) == [(DAY.sunrise, DAY.sunset)]


def test_sailing_times_still_apply_with_lights() -> None:
    """The sailor's own times limit a lit boat, before sunrise and after sunset."""
    lit, unlit = outlook(sailor("18:00:00", "22:00:00"), conditions(), BOATS).boats
    assert spans(lit) == [(at(18), at(22))]
    assert spans(unlit) == []

    lit, unlit = outlook(sailor("04:00:00", "09:00:00"), conditions(), BOATS).boats
    assert spans(lit) == [(at(4), at(9))]
    assert spans(unlit) == [(DAY.sunrise, at(9))]


def test_week_counts_the_evening_with_lights() -> None:
    """After sunset the panel still has a window for a boat with lights."""
    found = outlook(sailor(), conditions(), BOATS)
    now = at(17).astimezone(UTC)
    lit = week(found, found.boats[0], conditions(), now)
    unlit = week(found, found.boats[1], conditions(), now)

    assert (lit["lights"], unlit["lights"]) == (True, False)
    evening = lit["days"][0]
    assert not evening["over"]
    assert [(item["start"], item["end"]) for item in evening["windows"]] == [
        (now.isoformat(), at(24).astimezone(UTC).isoformat())
    ]
    assert unlit["days"][0]["over"]
    assert unlit["days"][0]["windows"] == []


def test_each_day_has_its_own_hours() -> None:
    """Windows follow the hours of the day of the week they fall on."""
    weekly = Sailor(
        id="sailor_alex",
        name="Alex",
        skill=Skill.INTERMEDIATE,
        boats=(LIT.id, UNLIT.id),
        week={"fri": Hours("17:00:00"), "sat": Hours("09:00:00", "12:00:00")},
    )
    lit, unlit = outlook(weekly, conditions(), BOATS).boats
    assert spans(lit) == spans(unlit) == [(at(9), at(12))]
    assert weekly.days == ("fri", "sat")


def test_hours_set_for_a_date_come_first() -> None:
    """A date's hours beat the weekday's: free all day, not sailing, or set hours."""
    usual = sailor("09:00:00", "12:00:00")
    # Free all day: sunrise to sunset, or every hour in a boat with lights.
    lit, unlit = outlook(usual, conditions(), BOATS, {DAY.date: Hours()}).boats
    assert spans(lit) == [(at(0), at(24))]
    assert spans(unlit) == [(DAY.sunrise, DAY.sunset)]
    # Not sailing.
    lit, unlit = outlook(usual, conditions(), BOATS, {DAY.date: None}).boats
    assert spans(lit) == spans(unlit) == []
    # Hours of their own.
    changed = {DAY.date: Hours("13:00:00", "16:00:00")}
    lit, unlit = outlook(usual, conditions(), BOATS, changed).boats
    assert spans(lit) == spans(unlit) == [(at(13), at(16))]
    # A change for another date leaves this one alone.
    lit, unlit = outlook(usual, conditions(), BOATS, {date(2026, 11, 8): None}).boats
    assert spans(unlit) == [(at(9), at(12))]


def test_a_day_off() -> None:
    """A day they don't usually sail gets windows once they're free that date."""
    sundays = Sailor(
        id="sailor_alex",
        name="Alex",
        skill=Skill.INTERMEDIATE,
        boats=(UNLIT.id,),
        week={"sun": Hours()},
    )
    assert spans(outlook(sundays, conditions(), BOATS).boats[0]) == []
    found = outlook(sundays, conditions(), BOATS, {DAY.date: Hours()})
    assert spans(found.boats[0]) == [(DAY.sunrise, DAY.sunset)]

    page = week(found, found.boats[0], conditions(), at(5).astimezone(UTC))
    assert page["days"][0]["hours"] == {"start": None, "end": None}
    assert page["days"][0]["changed"] is True
    usual = outlook(sundays, conditions(), BOATS)
    page = week(usual, usual.boats[0], conditions(), at(5).astimezone(UTC))
    assert page["days"][0]["hours"] is None
    assert page["days"][0]["changed"] is False
