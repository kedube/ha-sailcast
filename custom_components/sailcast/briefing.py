"""The AI briefing: a sailor's coming week, written up by the AI.

With the AI option on, the panel asks for the selected sailor's briefing when
it opens. SailCast sends Home Assistant's AI task the week at every spot in
each of the sailor's boats: conditions, ratings, sailing windows, official
warnings, its own advice and the spots' notes, in the reader's units (see
ai.week_data). The AI answers in a fixed form: a headline, a summary that
compares the days, spots and boats, up to three picks, a note for each day,
and when to check again.

SailCast checks the answer. A pick has to name one of the windows it sent,
so the AI can't make up a window or change its times, and the panel shows a
pick's times and score from SailCast's own data. The instructions say the
text must never contradict or soften a rating, and the panel shows the
ratings beside it. AI never sets a rating.

Briefings are written only when someone opens the panel or asks for one, as
that user, so Home Assistant's permission check for the AI task applies, and
never in the background. Each is kept on disk, per sailor and language, while
the ratings, windows and warnings of the hours to come stay the same; after
that the panel says the forecast has changed and offers a new one.
"""

from __future__ import annotations

import asyncio
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import logging
from typing import Any, Final

from homeassistant.components.ai_task import async_generate_data
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.hass_dict import HassKey
import probatio

from .ai import BadAnswerError, BoatWeek, clean, hours_ahead, language_name
from .const import DOMAIN
from .profiles import Sailor

LOGGER = logging.getLogger(__package__)

TASK_NAME: Final = "SailCast briefing"
STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = f"{DOMAIN}.briefings"
# The day summaries kept before the briefing replaced them.
OLD_STORAGE_KEY: Final = f"{DOMAIN}.summaries"
SAVE_DELAY: Final = 2.0
# How long a provider gets to answer. A briefing is longer than a summary,
# and providers running on the same machine can be slow.
WAIT: Final = 120
# Briefings older than this are dropped when SailCast starts.
KEEP: Final = timedelta(days=2)
PICKS: Final = 3
# The most characters each part may have, in any language.
LONGEST: Final = {
    "headline": 200,
    "summary": 900,
    "why": 300,
    "note": 450,
    "recheck": 300,
}
INSTRUCTIONS: Final = """\
You write the weekly briefing at the top of SailCast, a sailing forecast, for \
{sailor}. Write in {language}, as plain text: no Markdown, lists, headings or \
emoji.

The data is SailCast's forecast for the coming days: for each day and each \
spot, the conditions and any official warnings, and for each of the sailor's \
boats, its score out of 100, its safety ratings hour by hour and its sailing \
windows. "sailing_hours" is when the sailor can go that day: a missing end \
means sunrise or sunset, or any hour in a boat with navigation lights, and \
null means they don't sail that day. Use only this data and the spots' notes, \
and don't make up numbers.

- The safety ratings and windows come from SailCast's rules and are final. \
Never contradict or soften them, never call conditions safer than rated, and \
never suggest sailing in an hour rated caution, not recommended or dangerous.
- If there are official warnings, name them first, with when they apply.
- Compare the days, spots and boats: say which is the best choice and why, \
and what the trade-offs are, such as wind building or dropping, gusts, waves, \
rain or cold. Say where the forecast is uncertain (confidence medium or low).
- Picks must be windows from the data, by their id, best first.
- The spots' notes are local knowledge from the sailors. Use them to explain \
the conditions when they apply, but they never change a rating or a window.
- Don't recommend clothing, wetsuits, drysuits or other gear, and don't give \
navigation advice.
- Use the units given, and write times and days the way {language} speakers \
usually do.

The data, as JSON:
{data}"""

ANSWER: Final = probatio.Schema(
    {
        probatio.Required(
            "headline",
            description="One short sentence: the best choice this week, or that "
            "there's no good window.",
        ): str,
        probatio.Required(
            "summary",
            description="Two to four sentences that compare the days, spots and "
            "boats: the trade-offs, how the wind and waves change, official "
            "warnings, and what to watch for.",
        ): str,
        probatio.Required(
            "picks",
            description=f"Up to {PICKS} of the windows in the data, best first. "
            "Empty if there are none.",
        ): [
            probatio.Schema(
                {
                    probatio.Required(
                        "window", description="The window's id, such as w3."
                    ): str,
                    probatio.Required(
                        "why", description="One sentence on why it's a good choice."
                    ): str,
                }
            )
        ],
        probatio.Required(
            "days",
            description="A note for each day in the data, in the same order.",
        ): [
            probatio.Schema(
                {
                    probatio.Required(
                        "date", description="The day's date, as in the data."
                    ): str,
                    probatio.Required(
                        "note",
                        description="One or two sentences about the day for this "
                        "sailor: the best spot, boat and time, any rating that "
                        "isn't good and why, and official warnings.",
                    ): str,
                }
            )
        ],
        probatio.Required(
            "recheck",
            description="When to check the forecast again and why, if it's "
            "uncertain or a warning could change things. Otherwise empty.",
        ): str,
    }
)

DATA_BRIEFINGS: HassKey[Briefings] = HassKey(f"{DOMAIN}_briefings")

type Key = tuple[str, str]
"""A briefing's sailor and language."""

type Facts = Mapping[str, str]
"""What a briefing says depends on: each hour's rating, window and warnings."""


def facts(weeks: Sequence[BoatWeek], now: datetime) -> dict[str, str]:
    """Return what a briefing depends on, for the hours to come.

    Those are, for each spot and boat, the hours the boat can sail in: each
    one's rating, whether it's in a window, and its warnings. The spots'
    notes count too.
    """
    found: dict[str, str] = {}
    for item in weeks:
        spot, boat = item.outlook.spot, item.boat.boat
        if spot.notes:
            found[f"notes|{spot.id}"] = spot.notes
        windows = [
            (
                datetime.fromisoformat(window["start"]),
                datetime.fromisoformat(window["end"]),
            )
            for day in item.week["days"]
            for window in day["windows"]
        ]
        for day in item.week["days"]:
            for hour in hours_ahead(item, day["date"], now):
                start = datetime.fromisoformat(hour["time"])
                window = any(begin <= start < end for begin, end in windows)
                warnings = ",".join(sorted(hour["warnings"]))
                found[f"{spot.id}|{boat.id}|{hour['time']}"] = (
                    f"{hour['rating']}{'+' if window else ''}|{warnings}"
                )
    return found


def instructions(data: Mapping[str, Any], sailor: Sailor, language: str) -> str:
    """Return what the AI is asked."""
    return INSTRUCTIONS.format(
        sailor=sailor.name,
        language=language_name(language),
        data=json.dumps(data, ensure_ascii=False, separators=(",", ":")),
    )


def read_answer(
    answer: Any, windows: Mapping[str, Mapping[str, Any]], dates: Collection[str]
) -> dict[str, Any]:
    """Return the briefing in the AI's answer, checked, or raise if it isn't one.

    Picks that don't name a window SailCast sent, and notes for days it didn't
    send, are left out.
    """
    if isinstance(answer, str):
        try:
            answer = json.loads(answer)
        except ValueError as err:
            raise BadAnswerError("The answer wasn't a briefing") from err
    if not isinstance(answer, Mapping):
        raise BadAnswerError("The answer wasn't a briefing")
    picks: dict[str, dict[str, Any]] = {}
    for pick in _items(answer.get("picks")):
        number = pick.get("window")
        number = number.strip() if isinstance(number, str) else ""
        if number not in windows:
            LOGGER.debug("Leaving out a pick that isn't one of the windows: %s", pick)
            continue
        picks.setdefault(
            number,
            dict(windows[number])
            | {"why": clean(pick.get("why") or "", LONGEST["why"], required=False)},
        )
    notes: dict[str, str] = {}
    for day in _items(answer.get("days")):
        date = day.get("date")
        note = clean(day.get("note") or "", LONGEST["note"], required=False)
        if isinstance(date, str) and date in dates and date not in notes and note:
            notes[date] = note
    return {
        "headline": clean(answer.get("headline"), LONGEST["headline"]),
        "summary": clean(answer.get("summary"), LONGEST["summary"]),
        "picks": list(picks.values())[:PICKS],
        "days": notes,
        "recheck": clean(
            answer.get("recheck") or "", LONGEST["recheck"], required=False
        ),
    }


def _items(value: Any) -> list[Mapping[str, Any]]:
    """Return the objects in a list from the answer, leaving out anything else."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


@dataclass(frozen=True, slots=True)
class Briefing:
    """A briefing, when it was written, and what it was written from."""

    headline: str
    summary: str
    picks: tuple[Mapping[str, Any], ...]
    days: Mapping[str, str]
    recheck: str
    made: datetime
    facts: Facts = field(repr=False)

    def current(self, now_facts: Facts) -> bool:
        """Return whether the hours still to come look as they did."""
        return all(self.facts.get(key) == value for key, value in now_facts.items())

    def as_dict(self, now_facts: Facts) -> dict[str, Any]:
        """Return the briefing for the panel."""
        return {
            "headline": self.headline,
            "summary": self.summary,
            "picks": [dict(pick) for pick in self.picks],
            "days": dict(self.days),
            "recheck": self.recheck,
            "made": self.made.isoformat(),
            "current": self.current(now_facts),
        }

    def stored(self) -> dict[str, Any]:
        """Return the briefing as it's saved."""
        return {
            "headline": self.headline,
            "summary": self.summary,
            "picks": [dict(pick) for pick in self.picks],
            "days": dict(self.days),
            "recheck": self.recheck,
            "made": self.made.isoformat(),
            # As one string, so the file doesn't get a line for each hour.
            "facts": json.dumps(self.facts, separators=(",", ":")),
        }

    @classmethod
    def from_stored(cls, item: Mapping[str, Any]) -> Briefing:
        """Read a saved briefing."""
        return cls(
            headline=str(item["headline"]),
            summary=str(item["summary"]),
            picks=tuple(dict(pick) for pick in item["picks"]),
            days={str(date): str(note) for date, note in item["days"].items()},
            recheck=str(item["recheck"]),
            made=datetime.fromisoformat(item["made"]),
            facts={
                str(key): str(value) for key, value in json.loads(item["facts"]).items()
            },
        )


class Briefings:
    """The briefings written, one per sailor and language, kept on disk."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Start with none, until the saved ones are read."""
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._kept: dict[Key, Briefing] = {}
        self._locks: dict[Key, asyncio.Lock] = {}
        self._loaded = False

    async def async_load(self) -> None:
        """Read the briefings saved before, leaving out old ones."""
        if self._loaded:
            return
        self._loaded = True
        stored = await self._store.async_load()
        oldest = dt_util.utcnow() - KEEP
        for item in (stored or {}).get("briefings") or []:
            try:
                sailor, language = map(str, item["key"])
                briefing = Briefing.from_stored(item)
            except AttributeError, KeyError, TypeError, ValueError:
                LOGGER.warning("Ignoring an unreadable saved AI briefing")
                continue
            if briefing.made >= oldest:
                self._kept[sailor, language] = briefing

    async def async_remove(self) -> None:
        """Delete the saved briefings, when SailCast is deleted."""
        await self._store.async_remove()

    def get(self, key: Key) -> Briefing | None:
        """Return the briefing kept for a sailor in a language, if there is one."""
        return self._kept.get(key)

    async def async_write(
        self,
        hass: HomeAssistant,
        key: Key,
        found: Facts,
        asked: str,
        *,
        windows: Mapping[str, Mapping[str, Any]],
        dates: Collection[str],
        entity_id: str | None,
        context: Context | None,
    ) -> Briefing:
        """Return a current briefing, asking the AI for one if needed."""
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            if (kept := self._kept.get(key)) and kept.current(found):
                return kept
            async with asyncio.timeout(WAIT):
                result = await async_generate_data(
                    hass,
                    task_name=TASK_NAME,
                    entity_id=entity_id,
                    instructions=asked,
                    structure=ANSWER,
                    context=context,
                )
            answer = read_answer(result.data, windows, dates)
            briefing = Briefing(
                headline=answer["headline"],
                summary=answer["summary"],
                picks=tuple(answer["picks"]),
                days=answer["days"],
                recheck=answer["recheck"],
                made=dt_util.utcnow(),
                facts=dict(found),
            )
            self._kept[key] = briefing
            self._store.async_delay_save(self._data, SAVE_DELAY)
            return briefing

    def _data(self) -> dict[str, Any]:
        return {
            "briefings": [
                {"key": list(key)} | briefing.stored()
                for key, briefing in self._kept.items()
            ]
        }


async def async_remove_old(hass: HomeAssistant) -> None:
    """Delete the day summaries saved before the briefing replaced them."""
    await Store[dict[str, Any]](hass, 1, OLD_STORAGE_KEY).async_remove()
