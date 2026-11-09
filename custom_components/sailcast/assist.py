"""Ask SailCast: the forecast as tools for Assist.

SailCast offers Home Assistant an LLM API named "SailCast". Choosing it in a
conversation agent's settings, beside Assist, lets the AI read SailCast's
forecast to answer questions such as "Can I take the boat out on Saturday
afternoon?". The tools only read. The ratings and windows they give come from
SailCast's rules, and the prompt says never to contradict or soften them.

The forecast is for the person asking: the sailor linked to their Home
Assistant user, or the one they picked in the panel. Questions about another
sailor name them.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Final, Protocol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.util import dt as dt_util
from homeassistant.util.json import JsonObjectType
import probatio

from .ai import Units, boat_weeks, day_hours, week_data
from .const import DOMAIN
from .profiles import Profiles, Sailor
from .storage import DATA_STORE

if TYPE_CHECKING:
    from .coordinator import SailCastData

NAME: Final = "SailCast"
PROMPT: Final = """\
SailCast rates sailing conditions for this household's sailors, boats and \
spots. Use its tools for questions about when and where to go sailing, and \
answer from what they return.
- SailCast's safety ratings (good, caution, not recommended, dangerous) and \
its sailing windows come from its rules and are final. Never contradict or \
soften them, never call conditions safer than rated, and never suggest \
sailing in an hour that isn't rated good.
- Name any official warnings first.
- SailCast is advisory: official forecasts and warnings come first, and the \
skipper decides. Don't give navigation advice, and don't recommend clothing \
or other gear.
- A spot's notes are the sailors' local knowledge. They never change a rating.
Wind is in knots, heights in {height}, temperatures in {temperature}, and \
times are local, on a 24-hour clock.
It's {now}. The coming days: {days}.
Sailors: {sailors}.{asking}
Spots: {spots}."""
NOT_SET_UP: Final = "SailCast isn't set up, so it has no forecast to give."
READ_ONLY: Final = llm.ToolAnnotations(
    read_only=True, destructive=False, idempotent=True, open_world=False
)


class SailCastAPI(llm.API):
    """SailCast's forecast, for conversation agents."""

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        """Return the prompt and tools, for the person asking."""
        data = _loaded(self.hass)
        if data is None or not data.profiles.sailors or not data.profiles.spots:
            return llm.APIInstance(
                api=self, api_prompt=NOT_SET_UP, llm_context=llm_context, tools=[]
            )
        profiles = data.profiles
        asking = _asking(self.hass, profiles, llm_context)
        units = Units(self.hass)
        now = dt_util.now()
        sailors = "; ".join(
            f"{sailor.name} ({sailor.skill.value}; boats: "
            f"{', '.join(_names(profiles, sailor))})"
            for sailor in profiles.sailors.values()
        )
        prompt = PROMPT.format(
            height=units.names["height"],
            temperature=units.names["temperature"],
            now=f"{now:%A %Y-%m-%d %H:%M}",
            days=", ".join(
                f"{day:%A} {day:%Y-%m-%d}"
                for day in (now.date() + timedelta(days=i) for i in range(7))
            ),
            sailors=sailors,
            asking=f" The person asking is {asking.name}." if asking else "",
            spots=", ".join(spot.name for spot in profiles.spots.values()),
        )
        return llm.APIInstance(
            api=self,
            api_prompt=prompt,
            llm_context=llm_context,
            tools=[WeekTool(profiles, asking), DayTool(profiles, asking)],
        )


class _ForecastTool(llm.Tool):
    """Shared by the tools: who and what a question is about."""

    annotations = READ_ONLY
    integration = DOMAIN

    def __init__(self, profiles: Profiles, asking: Sailor | None) -> None:
        self.asking = asking
        sailors = [sailor.name for sailor in profiles.sailors.values()]
        spots = [spot.name for spot in profiles.spots.values()]
        boats = [boat.name for boat in profiles.boats.values()]
        self.parameters = probatio.Schema(
            self.extra_parameters()
            | {
                probatio.Optional(
                    "sailor",
                    description="Whose forecast, if not the person asking's.",
                ): probatio.In(sailors),
                probatio.Optional(
                    "spot", description="Only this spot. Leave out for every spot."
                ): probatio.In(spots),
                probatio.Optional(
                    "boat",
                    description="Only this boat. Leave out for all the sailor's boats.",
                ): probatio.In(boats),
            }
        )

    def extra_parameters(self) -> dict[probatio.Marker, Any]:
        """Return the parameters only this tool has."""
        return {}

    def chosen(
        self, data: SailCastData, args: dict[str, Any]
    ) -> tuple[Sailor, set[str] | None, set[str] | None] | str:
        """Return the sailor, spots and boats asked about, or what's wrong."""
        profiles = data.profiles
        sailor = self.asking
        if name := args.get("sailor"):
            sailor = _find(profiles.sailors.values(), name)
            if sailor is None:
                return f"There's no sailor called {name}."
        elif sailor is None:
            if len(profiles.sailors) != 1:
                return "Ask which sailor this is for: " + ", ".join(
                    item.name for item in profiles.sailors.values()
                )
            sailor = next(iter(profiles.sailors.values()))
        spots = None
        if name := args.get("spot"):
            spot = _find(profiles.spots.values(), name)
            if spot is None:
                return f"There's no spot called {name}."
            spots = {spot.id}
        boats = None
        if name := args.get("boat"):
            boat = _find(
                (profiles.boats[id_] for id_ in sailor.boats if id_ in profiles.boats),
                name,
            )
            if boat is None:
                return f"{sailor.name} has no boat called {name}."
            boats = {boat.id}
        return sailor, spots, boats


class WeekTool(_ForecastTool):
    """The coming week, day by day."""

    name = "sailcast_week"
    title = "SailCast week"
    description = (
        "Get SailCast's sailing forecast for the coming week: for each day and "
        "spot, the wind, gusts, waves and official warnings, and for each boat "
        "its score out of 100, its safety ratings through the day and its "
        "sailing windows. Use it to find when and where to sail, or to compare "
        "days, spots and boats."
    )

    def extra_parameters(self) -> dict[probatio.Marker, Any]:
        """Return the day, for only one day."""
        return {
            probatio.Optional("date", description="Only this day, as YYYY-MM-DD."): str,
        }

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Return the week for the sailor, spots and boats asked about."""
        if (data := _loaded(hass)) is None:
            return _error(NOT_SET_UP)
        args = tool_input.tool_args
        if isinstance(found := self.chosen(data, args), str):
            return _error(found)
        sailor, spots, boats = found
        now = dt_util.utcnow()
        weeks = boat_weeks(data.results.data, sailor, now, spots=spots, boats=boats)
        dates = {args["date"]} if args.get("date") else None
        forecast, _ = week_data(hass, weeks, sailor, now, dates=dates, detail=False)
        if not forecast["days"]:
            return _error("SailCast has no forecast for that.")
        return llm.ToolResult(data={"forecast": forecast})


class DayTool(_ForecastTool):
    """One day at one spot, hour by hour."""

    name = "sailcast_day"
    title = "SailCast day"
    description = (
        "Get SailCast's hour-by-hour forecast for one day at one spot: each "
        "hour's wind, gusts, waves, air temperature and rain chance, and each "
        "boat's safety rating and score, with the reasons for any rating that "
        "isn't good, plus the sailing windows, tides, sunrise and sunset. Use "
        "it for questions about a particular time."
    )

    def extra_parameters(self) -> dict[probatio.Marker, Any]:
        """Return the day, which is needed."""
        return {
            probatio.Required("date", description="The day, as YYYY-MM-DD."): str,
        }

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Return a day at a spot: the one asked about, or the sailor's usual one."""
        if (data := _loaded(hass)) is None:
            return _error(NOT_SET_UP)
        args = tool_input.tool_args
        if not isinstance(date := args.get("date"), str):
            return _error("Say which day, as YYYY-MM-DD.")
        if isinstance(found := self.chosen(data, args), str):
            return _error(found)
        sailor, spots, boats = found
        if spots is None:
            spots = {_usual_spot(hass, data, llm_context, sailor)}
        now = dt_util.utcnow()
        weeks = boat_weeks(data.results.data, sailor, now, spots=spots, boats=boats)
        if (day := day_hours(hass, weeks, date, now)) is None:
            return _error("SailCast has no forecast for that day.")
        return llm.ToolResult(data={"forecast": day})


def _loaded(hass: HomeAssistant) -> SailCastData | None:
    """Return the loaded SailCast entry's data, if there is one."""
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    return entries[0].runtime_data if entries else None


def _asking(
    hass: HomeAssistant, profiles: Profiles, llm_context: llm.LLMContext
) -> Sailor | None:
    """Return the sailor asking: picked in the panel, or linked to their user."""
    user = llm_context.context.user_id if llm_context.context else None
    if user is None:
        return None
    if (store := hass.data.get(DATA_STORE)) and (
        sailor := profiles.sailors.get(store.preferences(user).get("sailor", ""))
    ):
        return sailor
    return next(
        (sailor for sailor in profiles.sailors.values() if sailor.user == user), None
    )


def _usual_spot(
    hass: HomeAssistant,
    data: SailCastData,
    llm_context: llm.LLMContext,
    sailor: Sailor,
) -> str:
    """Return the spot the person asking picked in the panel, or the first one."""
    user = llm_context.context.user_id if llm_context.context else None
    if user and (store := hass.data.get(DATA_STORE)):
        spot = store.preferences(user).get("spot")
        if spot in data.profiles.spots:
            return spot
    return next(iter(data.profiles.spots))


def _names(profiles: Profiles, sailor: Sailor) -> list[str]:
    return [profiles.boats[id_].name for id_ in sailor.boats if id_ in profiles.boats]


class _Named(Protocol):
    @property
    def name(self) -> str: ...


def _find[T: _Named](items: Iterable[T], name: str) -> T | None:
    """Return the item with this name, whatever its case."""
    wanted = name.strip().casefold()
    return next((item for item in items if item.name.casefold() == wanted), None)


def _error(message: str) -> llm.ToolResult:
    data: JsonObjectType = {"error": message}
    return llm.ToolResult(data=data, error=True)
