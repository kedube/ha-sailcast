"""Tests for reading and checking profiles."""

from __future__ import annotations

from types import MappingProxyType

from homeassistant.config_entries import ConfigSubentry
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
    assert alex.start == "09:00:00"
    assert alex.end is None


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
        "days": ("sat", "sun"),
        "start": "09:00:00",
        "end": None,
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
    """A sailor needs known boats, a day, and a finish after the start."""
    good = {
        "boats": ["a"],
        "days": ["sat"],
        "start": "08:00:00",
        "end": "12:00:00",
    }
    assert profiles.check_sailor(good, {"a"}) == {}
    assert profiles.check_sailor(good | {"boats": []}, {"a"}) == {
        "boats": "unknown_boat"
    }
    assert profiles.check_sailor(good | {"end": "08:00:00"}, {"a"}) == {
        "end": "end_before_start"
    }
    assert profiles.check_sailor(good | {"start": None}, {"a"}) == {}


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
