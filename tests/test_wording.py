"""Tests for SailCast's own sentences: calendar events and notifications."""

from __future__ import annotations

from datetime import UTC, datetime
import re

from homeassistant.core import HomeAssistant
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM
import pytest

from custom_components.sailcast.limits import Level
from custom_components.sailcast.wording import Wording

# Saturday, November 7, 1:00 PM and 4:53 PM in San Diego.
ONE = datetime(2026, 11, 7, 21, tzinfo=UTC)
SUNSET = datetime(2026, 11, 8, 0, 53, tzinfo=UTC)
LANGUAGES = ("de", "fr", "nl", "es", "zh-Hans", "it", "pl", "sv", "ru", "cs", "pt-BR")


@pytest.fixture(autouse=True)
async def san_diego(hass: HomeAssistant) -> None:
    """Use the test spots' time zone."""
    await hass.config.async_set_time_zone("America/Los_Angeles")


async def test_english(hass: HomeAssistant) -> None:
    """English uses the 12-hour clock and a decimal point."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    wording = await Wording.async_load(hass, "en")
    assert wording.clock(ONE) == "1 PM"
    assert wording.clock(SUNSET) == "4:53 PM"
    assert wording.date(ONE) == "Saturday, Nov 7"
    assert wording.range(5.6, 8.9) == "6 to 9"
    assert wording.range(6.2, 5.8) == "6"
    assert wording.heights(0.3, 0.5) == "1.0 to 1.6 ft"
    assert wording.compass(225) == "SW"
    assert wording.band(81) == "great"
    assert wording.level(Level.NOT_RECOMMENDED) == "not recommended"
    assert wording.join(["One.", "Two."]) == "One. Two."


async def test_units_follow_home_assistant(hass: HomeAssistant) -> None:
    """Heights are in meters with the metric system."""
    hass.config.units = METRIC_SYSTEM
    wording = await Wording.async_load(hass, "en")
    assert wording.heights(0.3, 0.5) == "0.3 to 0.5 m"
    assert wording.heights(0.31, 0.34) == "0.3 m"


async def test_other_languages_format(hass: HomeAssistant) -> None:
    """Other languages use the 24-hour clock, and a decimal comma where it's usual."""
    german = Wording("de", {"range": "{low} bis {high}", "meters": "{value} m"})
    assert german.number(1.5, 1) == "1,5"
    assert german.heights(0.3, 0.55) == "0,3 bis 0,6 m"
    assert german.clock(ONE) == "13:00"
    assert Wording("en-GB", {}).clock(SUNSET) == "16:53"
    chinese = Wording("zh-Hans", {})
    assert chinese.number(1.5, 1) == "1.5"
    assert chinese.join(["一。", "二。"]) == "一。二。"


async def test_language_without_a_file(hass: HomeAssistant) -> None:
    """A language SailCast doesn't have gets English."""
    wording = await Wording.async_load(hass, "da")
    assert wording.text("changed_title") == "SailCast: forecast changed"


@pytest.mark.parametrize(
    ("language", "date"),
    [
        ("en", "Sunday, Nov 1"),
        ("de", "Sonntag, 1. Nov."),
        ("fr", "dimanche 1er nov."),
        ("pt-BR", "domingo, 1º de nov."),
    ],
)
async def test_first_of_the_month(
    hass: HomeAssistant, language: str, date: str
) -> None:
    """French and Brazilian Portuguese write the first as an ordinal."""
    wording = await Wording.async_load(hass, language)
    assert wording.date(datetime(2026, 11, 1, 20, tzinfo=UTC)) == date


@pytest.mark.parametrize("language", LANGUAGES)
async def test_every_language(hass: HomeAssistant, language: str) -> None:
    """Each language has its own sentences, with every value filled in."""
    english = await Wording.async_load(hass, "en")
    wording = await Wording.async_load(hass, language)
    message = wording.text(
        "changed",
        sailor="Alex",
        spot="Harbor",
        date=wording.date(ONE),
        start=wording.clock(ONE),
        end=wording.clock(SUNSET),
        level=wording.level(Level.DANGEROUS),
        score=42,
    )
    assert message != english.text(
        "changed",
        sailor="Alex",
        spot="Harbor",
        date=english.date(ONE),
        start=english.clock(ONE),
        end=english.clock(SUNSET),
        level=english.level(Level.DANGEROUS),
        score=42,
    )
    # The sentence itself is translated, not only its clock.
    assert wording.strings["changed"] != english.strings["changed"]
    assert not re.search(r"\{\w+\}", message)
    assert all(part in message for part in ("Alex", "Harbor", "13:00", "16:53", "42"))
    assert wording.text("added_by", id="01ABC").endswith("(01ABC)")
