"""Tests for reading and checking profiles."""

from __future__ import annotations

from datetime import date
from types import MappingProxyType

from homeassistant.config_entries import ConfigSubentry
import pytest
from pytest_homeassistant.common import MockConfigEntry

from custom_components.sailcast import profiles
from custom_components.sailcast.profiles import Profiles, SizeClass, Skill, WaterType


def test_profiles_from_entry(full_entry: MockConfigEntry) -> None:
    """Profiles are read from the subentries, with typed values."""
    read = Profiles.from_entry(full_entry)

    spot = read.spots["spot_harbor"]
    assert spot.name == "Harbor"
    assert spot.water_type is WaterType.OPEN_COAST
    assert spot.open_water
    assert spot.exposed == ("sw", "w", "nw")
    assert (spot.tide_station, spot.current_station, spot.marine_zone) == (
        "9410170",
        None,
        "PZZ740",
    )
    assert read.boats["boat_cruiser"].size_class is SizeClass.CRUISER

    alex = read.sailors["sailor_alex"]
    assert alex.skill is Skill.INTERMEDIATE
    assert alex.boats == ("boat_keelboat", "boat_cruiser")
    assert alex.days == ("sat", "sun")
    assert alex.week["sat"] == (profiles.Hours("09:00:00", None),)


def test_hours_from_before_each_day_had_its_own() -> None:
    """A sailor saved with one start and end gets them on every day they sail."""
    old = {"days": ["sun", "sat"], "start": "09:00:00", "end": "15:00:00"}
    assert profiles.week_hours(old) == {
        "sat": (profiles.Hours("09:00:00", "15:00:00"),),
        "sun": (profiles.Hours("09:00:00", "15:00:00"),),
    }
    # Then each day had one start and end of its own.
    one = {
        "days": ["fri", "sat"],
        "hours": {"fri": {"start": "17:00:00", "end": None}, "mon": {}},
    }
    # A sailing day without hours of its own runs sunrise to sunset.
    assert profiles.week_hours(one) == {
        "fri": (profiles.Hours("17:00:00", None),),
        "sat": profiles.ALL_DAY,
    }


def test_several_stretches_a_day() -> None:
    """A day can have several stretches, read earliest first; none is all day."""
    data = {
        "days": ["sat", "sun"],
        "hours": {
            "sat": [
                {"start": "15:00:00", "end": "19:00:00"},
                {"start": "09:00:00", "end": "11:00:00"},
                {"start": None, "end": "07:00:00"},
            ],
            "sun": [],
        },
    }
    assert profiles.week_hours(data) == {
        "sat": (
            profiles.Hours(None, "07:00:00"),
            profiles.Hours("09:00:00", "11:00:00"),
            profiles.Hours("15:00:00", "19:00:00"),
        ),
        "sun": profiles.ALL_DAY,
    }
    assert profiles.hours_data(profiles.week_hours(data)["sat"][1:]) == [
        {"start": "09:00:00", "end": "11:00:00"},
        {"start": "15:00:00", "end": "19:00:00"},
    ]


def test_hours_on_a_date() -> None:
    """A change made for a date comes before the weekday's hours."""
    sailor = profiles.Sailor(
        id="alex",
        name="Alex",
        skill=Skill.INTERMEDIATE,
        boats=("boat",),
        week={"sat": (profiles.Hours("09:00:00"),)},
    )
    saturday, sunday = date(2026, 11, 7), date(2026, 11, 8)
    assert sailor.hours_on(saturday) == (profiles.Hours("09:00:00"),)
    assert sailor.hours_on(sunday) is None
    changes = {saturday: None, sunday: profiles.ALL_DAY}
    assert sailor.hours_on(saturday, changes) is None
    assert sailor.hours_on(sunday, changes) == profiles.ALL_DAY


def test_boat_lights() -> None:
    """Boats saved before navigation lights existed have none."""

    def boat(**data: object) -> profiles.Boat:
        return profiles.Boat.from_subentry(
            ConfigSubentry(
                data=MappingProxyType(
                    {"size_class": "cruiser", "length": 10.4, **data}
                ),
                subentry_type="boat",
                title="Cruiser",
                unique_id=None,
            )
        )

    assert boat().lights is False
    assert boat(lights=True).lights is True


def test_removed_boats_are_left_out(full_entry: MockConfigEntry) -> None:
    """A sailor's removed boat is dropped, and the next one becomes usual."""
    data = full_entry.subentries["sailor_alex"].data
    sailor = profiles.Sailor.from_subentry(
        full_entry.subentries["sailor_alex"], boats={"boat_cruiser"}
    )
    assert data["boats"] == ["boat_keelboat", "boat_cruiser"]
    assert sailor.boats == ("boat_cruiser",)


def test_as_dict_is_sorted_by_name(full_entry: MockConfigEntry) -> None:
    """The panel gets each kind of profile sorted by name."""
    result = Profiles.from_entry(full_entry).as_dict()
    assert [boat["name"] for boat in result["boats"]] == ["Cruiser", "Keelboat"]
    assert result["sailors"][0] == {
        "id": "sailor_alex",
        "name": "Alex",
        "skill": "intermediate",
        "boats": ("boat_keelboat", "boat_cruiser"),
        "week": {
            "sat": ({"start": "09:00:00", "end": None},),
            "sun": ({"start": "09:00:00", "end": None},),
        },
        "user": None,
        "comfort": {
            "ideal_low": None,
            "ideal_high": None,
            "coldest": None,
            "rain": "some",
        },
        "auto_calendar": None,
    }


def test_check_name() -> None:
    """Names must be present, short enough, and unique ignoring case."""
    assert profiles.check_name("Harbor", ["Bay"]) is None
    assert profiles.check_name(" ", []) == "name_required"
    assert profiles.check_name("x" * 41, []) == "name_too_long"
    assert profiles.check_name(" HARBOR ", ["Bay", "harbor"]) == "name_taken"


def test_check_sailor() -> None:
    """A sailor needs known boats, a day, and each day's hours in order."""
    good = {
        "boats": ["a"],
        "days": ["fri", "sat"],
        "hours": {
            "fri": [{"start": "17:00:00", "end": None}],
            "sat": [
                {"start": "08:00:00", "end": "12:00:00"},
                {"start": "15:00:00", "end": "19:00:00"},
            ],
        },
    }
    assert profiles.check_sailor(good, {"a"}) == {}
    assert profiles.check_sailor(good | {"boats": []}, {"a"}) == {
        "boats": "unknown_boat"
    }
    assert profiles.check_sailor(good | {"days": []}, {"a"}) == {"days": "no_days"}
    # Errors are by day.
    late = {"sat": [{"start": "08:00:00", "end": "08:00:00"}]}
    assert profiles.check_sailor(good | {"hours": late}, {"a"}) == {
        "sat": "end_before_start"
    }
    # A day saved with one start and end is checked too.
    assert profiles.check_hours({"sat": {"start": "08:00:00", "end": "07:00:00"}}) == {
        "sat": "end_before_start"
    }


def _day(*stretches: tuple[str | None, str | None]) -> list[profiles.Hours]:
    return [profiles.Hours(start, end) for start, end in stretches]


@pytest.mark.parametrize(
    ("stretches", "error"),
    [
        ([(None, None)], None),
        ([("09:00:00", "11:00:00"), ("15:00:00", "19:00:00")], None),
        # In any order, and one can start where another ends.
        ([("15:00:00", "19:00:00"), ("09:00:00", "15:00:00")], None),
        # Sunrise to 7 AM, and 5 PM to sunset.
        ([(None, "07:00:00"), ("17:00:00", None)], None),
        ([("09:00:00", "12:00:00"), ("11:00:00", "14:00:00")], "hours_overlap"),
        ([("08:00:00", "18:00:00"), ("09:00:00", "11:00:00")], "hours_overlap"),
        # Only the first can start at sunrise, and only the last end at sunset.
        ([(None, "11:00:00"), (None, "13:00:00")], "hours_overlap"),
        ([("17:00:00", None), ("19:00:00", "21:00:00")], "hours_overlap"),
        ([(None, None), ("09:00:00", "11:00:00")], "hours_overlap"),
        ([("09:00:00", "11:00:00"), ("13:00:00", "13:00:00")], "end_before_start"),
        (
            [(f"{hour:02}:00:00", f"{hour:02}:30:00") for hour in range(8, 13)],
            "too_many_hours",
        ),
    ],
)
def test_check_day(
    stretches: list[tuple[str | None, str | None]], error: str | None
) -> None:
    """Stretches end after they start and don't overlap, up to four a day."""
    assert profiles.check_day(_day(*stretches)) == error


def test_clock() -> None:
    """Times from the setup dialog are kept as hours, minutes and seconds."""
    assert profiles.clock("9:00") == "09:00:00"
    assert profiles.clock("17:30:00") == "17:30:00"
    assert profiles.clock("") is None
    assert profiles.clock(None) is None


def test_spots_from_before_sources(entry: MockConfigEntry) -> None:
    """Spots saved before data sources existed still load, without sources."""
    subentry = ConfigSubentry(
        data=MappingProxyType(
            {
                "latitude": 32.7,
                "longitude": -117.2,
                "radius": 10_000.0,
                "water_type": "lake",
                "offshore": [],
                "exposed": [],
            }
        ),
        subentry_type="spot",
        title="Lake",
        unique_id=None,
    )
    spot = profiles.Spot.from_subentry(subentry)
    assert (spot.tide_station, spot.current_station, spot.marine_zone) == (
        None,
        None,
        None,
    )
    assert not spot.open_water
    assert spot.source_names == {}
    assert (spot.buoy, spot.airport, spot.fetch) == (None, None, None)
    assert spot.sensors == {}
    assert spot.source_points == {}


def test_spot_readings_and_fetch() -> None:
    """A spot's buoy, airport, sensors and fetch are read typed."""
    subentry = ConfigSubentry(
        data=MappingProxyType(
            {
                "latitude": 32.7,
                "longitude": -117.2,
                "radius": 10_000.0,
                "water_type": "lake",
                "offshore": [],
                "exposed": [],
                "buoy": "46258",
                "airport": "KSAN",
                "sensors": {"wind": "sensor.dock_wind"},
                "fetch": 3.5,
                "source_points": {"buoy": [32.749, -117.502]},
            }
        ),
        subentry_type="spot",
        title="Lake",
        unique_id=None,
    )
    spot = profiles.Spot.from_subentry(subentry)
    assert (spot.buoy, spot.airport, spot.fetch) == ("46258", "KSAN", 3.5)
    assert spot.sensors == {"wind": "sensor.dock_wind"}
    assert spot.source_points == {"buoy": (32.749, -117.502)}


def test_check_spot_fetch_and_sensors() -> None:
    """Fetch set by hand must be sensible, and sensors must be sensors."""
    spot = {"radius": 10_000.0}
    assert profiles.check_spot(spot | {"fetch": 2.0}) == {}
    assert profiles.check_spot(spot | {"fetch": 0.01}) == {
        "fetch": "fetch_out_of_range"
    }
    assert profiles.check_spot(spot | {"fetch": 500.0}) == {
        "fetch": "fetch_out_of_range"
    }
    assert profiles.check_spot(spot | {"sensors": {"wind": "sensor.a"}}) == {}
    assert profiles.check_spot(spot | {"sensors": {"wind": "light.a"}}) == {
        "sensors": "invalid_sensor"
    }
    assert profiles.check_spot(spot | {"sensors": {"waves": "sensor.a"}}) == {
        "sensors": "invalid_sensor"
    }


def test_comfort_and_automatic_adding(full_entry: MockConfigEntry) -> None:
    """A sailor's comfort settings and automatic adding are read typed.

    Spots that have been removed drop out of automatic adding.
    """
    data = dict(full_entry.subentries["sailor_alex"].data) | {
        "user": "user_alex",
        "comfort": {"ideal_low": 8, "ideal_high": 14, "coldest": 12, "rain": "avoid"},
        "auto_calendar": {
            "calendar": "calendar.family",
            "days": ["sat", "sun"],
            "min_score": 80,
            "ahead": 2,
            "spots": ["spot_harbor", "spot_gone"],
        },
    }
    subentry = ConfigSubentry(
        data=MappingProxyType(data),
        subentry_type="sailor",
        title="Alex",
        unique_id=None,
    )
    sailor = profiles.Sailor.from_subentry(
        subentry, boats={"boat_keelboat"}, spots={"spot_harbor"}
    )
    assert sailor.user == "user_alex"
    assert sailor.comfort == profiles.Comfort(
        ideal_low=8, ideal_high=14, coldest=12, rain=profiles.RainTolerance.AVOID
    )
    assert sailor.auto_calendar == profiles.AutoCalendar(
        calendar="calendar.family",
        days=("sat", "sun"),
        min_score=80,
        ahead=2,
        spots=("spot_harbor",),
    )
    # Without a calendar, automatic adding is off.
    off = profiles.AutoCalendar.from_data({"calendar": None, "days": []}, set())
    assert off is None


@pytest.mark.parametrize(
    ("comfort", "errors"),
    [
        ({}, {}),
        ({"ideal_low": 6, "ideal_high": 14, "coldest": -5}, {}),
        ({"ideal_low": 14, "ideal_high": 6}, {"ideal_high": "ideal_high_below_low"}),
        ({"ideal_low": -1}, {"ideal_low": "ideal_out_of_range"}),
        ({"ideal_high": 41}, {"ideal_high": "ideal_out_of_range"}),
        ({"coldest": 40}, {"coldest": "coldest_out_of_range"}),
    ],
)
def test_check_comfort(comfort: dict[str, float], errors: dict[str, str]) -> None:
    """The ideal wind runs low to high within 0-40 kt, and cold within reason."""
    assert profiles.check_comfort(comfort) == errors


def test_check_auto_calendar() -> None:
    """Automatic adding needs days, known spots, and one of the choices."""
    auto = {
        "calendar": "calendar.family",
        "days": ["sat"],
        "min_score": 60,
        "ahead": 2,
        "spots": ["harbor"],
    }
    assert profiles.check_auto_calendar(auto, {"harbor"}) == {}
    assert profiles.check_auto_calendar(None, set()) == {}
    assert profiles.check_auto_calendar(auto | {"calendar": None}, set()) == {}
    assert profiles.check_auto_calendar(
        auto | {"days": [], "spots": ["gone"], "min_score": 70, "ahead": 3},
        {"harbor"},
    ) == {
        "auto_days": "no_days",
        "auto_spots": "no_spots",
        "min_score": "invalid_min_score",
        "ahead": "invalid_ahead",
    }


def test_in_order() -> None:
    """Chosen values come back in their fixed order, once each."""
    assert profiles.in_order(["sun", "mon", "sun"], ("mon", "sat", "sun")) == [
        "mon",
        "sun",
    ]
