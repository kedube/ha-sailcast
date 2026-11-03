"""SailCast's own sentences, for calendar events and notifications.

Home Assistant translates what it shows itself, but the text of calendar
events and notifications is written by SailCast. Its words come from the
`common` group of the translation files, in Home Assistant's language or, for
an event someone adds from the panel, in theirs; a language without a file
gets English. Times use the 12-hour clock in English and the 24-hour clock in
other languages, and numbers a decimal comma where the language has one.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Final

from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import DistanceConverter

from .const import DOMAIN
from .geo import compass_point
from .limits import Level
from .scoring import band

# SailCast's languages that write 1.5 as 1,5. Languages without a translation
# get English, with a decimal point.
_DECIMAL_COMMA: Final = frozenset(
    {"cs", "de", "es", "fr", "it", "nl", "pl", "pt", "ru", "sv"}
)
# Languages that don't put spaces between sentences.
_NO_SPACES: Final = frozenset({"zh"})
_WEEKDAYS: Final = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_PLACEHOLDER: Final = re.compile(r"\{(\w+)\}")


@dataclass(frozen=True, slots=True)
class Wording:
    """SailCast's sentences in one language, with Home Assistant's units."""

    language: str
    strings: Mapping[str, str]
    feet: bool = False

    @classmethod
    async def async_load(
        cls, hass: HomeAssistant, language: str | None = None
    ) -> Wording:
        """Return the wording in a language, or in Home Assistant's own."""
        language = language or hass.config.language
        found = await async_get_translations(hass, language, "common", {DOMAIN})
        prefix = f"component.{DOMAIN}.common."
        return cls(
            language,
            {key.removeprefix(prefix): text for key, text in found.items()},
            hass.config.units.length_unit == UnitOfLength.MILES,
        )

    @property
    def _base(self) -> str:
        return self.language.split("-")[0]

    def text(self, key: str, **values: object) -> str:
        """Return a sentence with its {placeholders} filled in."""
        return _PLACEHOLDER.sub(
            lambda match: str(values.get(match.group(1), match.group(0))),
            self.strings.get(key, key),
        )

    def join(self, sentences: list[str]) -> str:
        """Return sentences as one paragraph."""
        return ("" if self._base in _NO_SPACES else " ").join(sentences)

    def number(self, value: float, digits: int = 0) -> str:
        """Return a number such as "1.5", or "1,5" where that's the custom."""
        text = f"{value:.{digits}f}"
        return text.replace(".", ",") if self._base in _DECIMAL_COMMA else text

    def range(self, low: float, high: float, digits: int = 0) -> str:
        """Return a range such as "6 to 9", or one number when both round alike."""
        low_text, high_text = self.number(low, digits), self.number(high, digits)
        if low_text == high_text:
            return low_text
        return self.text("range", low=low_text, high=high_text)

    def heights(self, low: float, high: float) -> str:
        """Return a range of heights in meters as "0.3 to 0.5 m", or in feet."""
        unit = UnitOfLength.FEET if self.feet else UnitOfLength.METERS
        low, high = (
            DistanceConverter.convert(value, UnitOfLength.METERS, unit)
            for value in (low, high)
        )
        return self.text(
            "feet" if self.feet else "meters", value=self.range(low, high, 1)
        )

    def clock(self, when: datetime) -> str:
        """Return a local time such as "4:30 PM", or "16:30"."""
        when = dt_util.as_local(when)
        if self.language != "en":
            return f"{when:%H:%M}"
        hour = when.hour % 12 or 12
        suffix = "AM" if when.hour < 12 else "PM"
        return (
            f"{hour} {suffix}"
            if when.minute == 0
            else f"{hour}:{when.minute:02d} {suffix}"
        )

    def date(self, when: datetime) -> str:
        """Return a local date such as "Saturday, Nov 7"."""
        when = dt_util.as_local(when)
        return self.text(
            "date",
            weekday=self.text(f"weekday_{_WEEKDAYS[when.weekday()]}"),
            month=self.text(f"month_{when.month}"),
            day=when.day,
        )

    def compass(self, degrees: float) -> str:
        """Return a compass point such as "SW"."""
        return self.text(f"compass_{compass_point(degrees)}")

    def band(self, score: int) -> str:
        """Return a score's band, such as "great"."""
        return self.text(f"band_{band(score)}")

    def level(self, level: Level) -> str:
        """Return a safety rating inside a sentence, such as "not recommended"."""
        return self.text(f"level_{level.key}")
