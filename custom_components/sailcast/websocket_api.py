"""WebSocket commands for the SailCast panel.

The panel reads computed results here rather than entity states, and is told
when they change. Settings use the same checks as the setup dialogs and save
to the same subentries, so Settings → Devices & services always shows the
same data. Only administrators can change them. Calendar events are added and
taken out with the requesting user's permissions, as Home Assistant's own
calendar commands do.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import MappingProxyType
from typing import Any, Final

from homeassistant.auth.models import User
from homeassistant.auth.permissions.const import POLICY_CONTROL
from homeassistant.components import websocket_api
from homeassistant.components.calendar import CalendarEntityFeature
from homeassistant.components.calendar.const import DATA_COMPONENT
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_RADIUS, WEEKDAYS
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, Unauthorized
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.loader import IntegrationNotLoaded, async_get_loaded_integration
from homeassistant.util import dt as dt_util
import probatio

from . import profiles
from .const import (
    CONF_AHEAD,
    CONF_AUTO_CALENDAR,
    CONF_BOATS,
    CONF_CALENDAR,
    CONF_COLDEST,
    CONF_COMFORT,
    CONF_CURRENT_STATION,
    CONF_DAYS,
    CONF_END,
    CONF_EXPOSED,
    CONF_IDEAL_HIGH,
    CONF_IDEAL_LOW,
    CONF_LENGTH,
    CONF_MARINE_ZONE,
    CONF_MIN_SCORE,
    CONF_OFFSHORE,
    CONF_RAIN,
    CONF_SIZE_CLASS,
    CONF_SKILL,
    CONF_SOURCE_NAMES,
    CONF_SPOTS,
    CONF_START,
    CONF_TIDE_STATION,
    CONF_USER,
    CONF_WATER_TYPE,
    DOMAIN,
    SIGNAL_UPDATED,
    SUBENTRY_BOAT,
    SUBENTRY_SAILOR,
    SUBENTRY_SPOT,
)
from .coordinator import SailCastConfigEntry, SailCastData
from .limits import BOAT_LIMITS, SKILL_WIND_LIMITS
from .planner import calendar_entity, supports
from .sources import async_suggest, suggested
from .storage import DATA_STORE, PREFERENCES, PlannedSail
from .week import week

# A sail added from the panel lasts at least an hour, and at most a day.
SHORTEST_SAIL: Final = timedelta(hours=1)
LONGEST_SAIL: Final = timedelta(days=1)
MAX_TITLE: Final = 80


def _time_of_day(value: Any) -> str | None:
    """Accept a time such as "09:00" and keep it as "09:00:00"."""
    if value in (None, ""):
        return None
    parsed = dt_util.parse_time(str(value))
    if parsed is None:
        raise probatio.Invalid("Not a time of day")
    return parsed.strftime("%H:%M:%S")


def _choices(options: Any) -> probatio.In:
    return probatio.In([str(option) for option in options])


SPOT_DATA: Final = probatio.Schema(
    {
        probatio.Required(CONF_LATITUDE): cv.latitude,
        probatio.Required(CONF_LONGITUDE): cv.longitude,
        probatio.Required(CONF_RADIUS): probatio.Coerce(float),
        probatio.Required(CONF_WATER_TYPE): _choices(profiles.WaterType),
        probatio.Optional(CONF_OFFSHORE, default=list): [_choices(profiles.DIRECTIONS)],
        probatio.Optional(CONF_EXPOSED, default=list): [_choices(profiles.DIRECTIONS)],
        probatio.Optional(CONF_TIDE_STATION, default=None): probatio.Maybe(cv.string),
        probatio.Optional(CONF_CURRENT_STATION, default=None): probatio.Maybe(
            cv.string
        ),
        probatio.Optional(CONF_MARINE_ZONE, default=None): probatio.Maybe(cv.string),
        probatio.Optional(CONF_SOURCE_NAMES, default=dict): {cv.string: cv.string},
    }
)
BOAT_DATA: Final = probatio.Schema(
    {
        probatio.Required(CONF_SIZE_CLASS): _choices(profiles.SizeClass),
        probatio.Required(CONF_LENGTH): probatio.Coerce(float),
    }
)
COMFORT_DATA: Final = probatio.Schema(
    {
        probatio.Optional(CONF_IDEAL_LOW, default=None): probatio.Maybe(
            probatio.Coerce(float)
        ),
        probatio.Optional(CONF_IDEAL_HIGH, default=None): probatio.Maybe(
            probatio.Coerce(float)
        ),
        probatio.Optional(CONF_COLDEST, default=None): probatio.Maybe(
            probatio.Coerce(float)
        ),
        probatio.Optional(CONF_RAIN, default=profiles.RainTolerance.SOME.value): (
            _choices(profiles.RainTolerance)
        ),
    }
)
AUTO_CALENDAR_DATA: Final = probatio.Schema(
    {
        probatio.Required(CONF_CALENDAR): cv.entity_id,
        probatio.Required(CONF_DAYS): [_choices(WEEKDAYS)],
        probatio.Required(CONF_MIN_SCORE): probatio.Coerce(int),
        probatio.Required(CONF_AHEAD): probatio.Coerce(int),
        probatio.Required(CONF_SPOTS): [cv.string],
    }
)
SAILOR_DATA: Final = probatio.Schema(
    {
        probatio.Required(CONF_SKILL): _choices(profiles.Skill),
        probatio.Required(CONF_BOATS): [cv.string],
        probatio.Required(CONF_DAYS): [_choices(WEEKDAYS)],
        probatio.Optional(CONF_START, default=None): _time_of_day,
        probatio.Optional(CONF_END, default=None): _time_of_day,
        probatio.Optional(CONF_USER, default=None): probatio.Maybe(cv.string),
        probatio.Optional(CONF_COMFORT, default=dict): COMFORT_DATA,
        probatio.Optional(CONF_AUTO_CALENDAR, default=None): probatio.Maybe(
            AUTO_CALENDAR_DATA
        ),
    }
)
KINDS: Final = {
    SUBENTRY_SPOT: SPOT_DATA,
    SUBENTRY_BOAT: BOAT_DATA,
    SUBENTRY_SAILOR: SAILOR_DATA,
}


@callback
def async_register_commands(hass: HomeAssistant) -> None:
    """Register the panel's commands."""
    for command in (
        ws_config,
        ws_forecast,
        ws_subscribe,
        ws_preferences_get,
        ws_preferences_set,
        ws_settings_save,
        ws_settings_delete,
        ws_settings_sources,
        ws_calendar_add,
        ws_calendar_remove,
        ws_planned_list,
        ws_planned_skipped,
    ):
        websocket_api.async_register_command(hass, command)


def _data(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> SailCastData | None:
    """Return the loaded entry's data, or tell the panel SailCast isn't set up."""
    if entry := _entry(hass):
        return entry.runtime_data
    connection.send_error(
        msg["id"], websocket_api.ERR_NOT_FOUND, "SailCast isn't set up"
    )
    return None


def _entry(hass: HomeAssistant) -> SailCastConfigEntry | None:
    entries: list[SailCastConfigEntry] = hass.config_entries.async_loaded_entries(
        DOMAIN
    )
    return entries[0] if entries else None


@websocket_api.websocket_command({probatio.Required("type"): "sailcast/config"})
@websocket_api.async_response
async def ws_config(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Send the spots, boats, sailors, limits and calendars."""
    if (data := _data(hass, connection, msg)) is None:
        return
    user = connection.user
    result: dict[str, Any] = data.profiles.as_dict() | {
        "limits": {
            size.value: {
                "wind": limits.wind,
                "gust": limits.gust,
                "wave": limits.wave,
                "ideal_wind": limits.ideal_wind,
            }
            for size, limits in BOAT_LIMITS.items()
        },
        "skills": {skill.value: limit for skill, limit in SKILL_WIND_LIMITS.items()},
        "calendars": _calendars(hass, user),
        "users": [],
    }
    if user.is_admin:
        result["users"] = [
            {"id": person.id, "name": person.name}
            for person in await hass.auth.async_get_users()
            if not person.system_generated and person.is_active
        ]
    connection.send_result(msg["id"], result)


def _calendars(hass: HomeAssistant, user: User) -> list[dict[str, Any]]:
    """Return the calendars that accept new events and that the user can change."""
    if (component := hass.data.get(DATA_COMPONENT)) is None:
        return []
    registry = er.async_get(hass)
    calendars = []
    for entity in component.entities:
        if not supports(entity, CalendarEntityFeature.CREATE_EVENT):
            continue
        if not user.permissions.check_entity(entity.entity_id, POLICY_CONTROL):
            continue
        state = hass.states.get(entity.entity_id)
        entry = registry.async_get(entity.entity_id)
        platform = entry.platform if entry else entity.platform.platform_name
        try:
            via = async_get_loaded_integration(hass, platform).name
        except IntegrationNotLoaded:
            via = platform
        calendars.append(
            {
                "entity_id": entity.entity_id,
                "name": state.name if state else entity.entity_id,
                "via": via,
                "update": supports(entity, CalendarEntityFeature.UPDATE_EVENT),
                "delete": supports(entity, CalendarEntityFeature.DELETE_EVENT),
            }
        )
    return sorted(calendars, key=lambda calendar: calendar["name"].casefold())


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "sailcast/forecast",
        probatio.Required("spot"): cv.string,
        probatio.Required("sailor"): cv.string,
        probatio.Optional("boat"): cv.string,
    }
)
@callback
def ws_forecast(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Send a sailor's week at a spot in one of their boats, with planned sails."""
    if (data := _data(hass, connection, msg)) is None:
        return
    results = data.results.data
    outlook = results.outlook(msg["sailor"], msg["spot"])
    conditions = results.conditions.get(msg["spot"])
    if outlook is None or conditions is None or not outlook.boats:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_FOUND, "There's no forecast for that yet"
        )
        return
    boat = next(
        (item for item in outlook.boats if item.boat.id == msg.get("boat")),
        outlook.boats[0],
    )
    now = dt_util.utcnow()
    spot = outlook.spot
    fetched = data.sources.forecast.fetched
    result = week(outlook, boat, conditions, now) | {
        "fetched": fetched.isoformat() if fetched else None,
        "sources": {
            key: {"id": value, "name": spot.source_names.get(key)}
            if (value := getattr(spot, key))
            else None
            for key in (CONF_TIDE_STATION, CONF_CURRENT_STATION, CONF_MARINE_ZONE)
        },
        "planned": [
            _planned(hass, data, sail)
            for sail in data.planner.store.planned
            if sail.sailor == outlook.sailor.id and sail.end > now
        ],
    }
    connection.send_result(msg["id"], result)


def _planned(
    hass: HomeAssistant, data: SailCastData, sail: PlannedSail
) -> dict[str, Any]:
    """Return a planned sail with its forecast now, for the panel."""
    entity = calendar_entity(hass, sail.calendar)
    return sail.as_dict() | {
        "status": data.planner.status(sail).as_dict(),
        "can_delete": bool(
            entity and sail.uid and supports(entity, CalendarEntityFeature.DELETE_EVENT)
        ),
    }


@websocket_api.websocket_command({probatio.Required("type"): "sailcast/subscribe"})
@callback
def ws_subscribe(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Tell the panel whenever results, planned sails or settings change."""

    @callback
    def forward() -> None:
        connection.send_message(
            websocket_api.event_message(
                msg["id"], {"updated": dt_util.utcnow().isoformat()}
            )
        )

    connection.subscriptions[msg["id"]] = async_dispatcher_connect(
        hass, SIGNAL_UPDATED, forward
    )
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {probatio.Required("type"): "sailcast/preferences/get"}
)
@callback
def ws_preferences_get(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Send the user's preferences, starting from their linked sailor."""
    preferences = hass.data[DATA_STORE].preferences(connection.user.id)
    if "sailor" not in preferences and (entry := _entry(hass)):
        sailors = entry.runtime_data.profiles.sailors.values()
        if linked := next(
            (sailor for sailor in sailors if sailor.user == connection.user.id), None
        ):
            preferences["sailor"] = linked.id
    connection.send_result(msg["id"], preferences)


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "sailcast/preferences/set",
        **{probatio.Optional(key): probatio.Maybe(cv.string) for key in PREFERENCES},
    }
)
@callback
def ws_preferences_set(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Change some of the user's preferences."""
    changes: dict[str, str | None] = {
        key: msg[key] for key in PREFERENCES if key in msg
    }
    connection.send_result(
        msg["id"], hass.data[DATA_STORE].set_preferences(connection.user.id, changes)
    )


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "sailcast/settings/save",
        probatio.Required("kind"): probatio.In(list(KINDS)),
        probatio.Optional("profile"): cv.string,
        probatio.Required("name"): cv.string,
        probatio.Required("data"): dict,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_settings_save(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Add or change a spot, boat or sailor.

    Problems a person can fix come back as {"errors": {field: key}}, with the
    same keys as the setup dialogs.
    """
    entry = _entry(hass)
    if entry is None:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_FOUND, "SailCast isn't set up"
        )
        return
    kind, name = msg["kind"], msg["name"].strip()
    subentry = None
    if "profile" in msg:
        subentry = entry.subentries.get(msg["profile"])
        if subentry is None or subentry.subentry_type != kind:
            connection.send_error(
                msg["id"], websocket_api.ERR_NOT_FOUND, f"There's no such {kind}"
            )
            return
    try:
        data = KINDS[kind](msg["data"])
    except probatio.Invalid as err:
        connection.send_error(msg["id"], websocket_api.ERR_INVALID_FORMAT, str(err))
        return
    errors = await _async_check(hass, entry, kind, name, data, editing=subentry)
    if errors:
        connection.send_result(msg["id"], {"errors": errors})
        return
    if subentry is None:
        subentry = ConfigSubentry(
            data=MappingProxyType(data), subentry_type=kind, title=name, unique_id=None
        )
        hass.config_entries.async_add_subentry(entry, subentry)
    else:
        hass.config_entries.async_update_subentry(
            entry, subentry, title=name, data=data
        )
    connection.send_result(msg["id"], {"profile": subentry.subentry_id})


async def _async_check(
    hass: HomeAssistant,
    entry: SailCastConfigEntry,
    kind: str,
    name: str,
    data: dict[str, Any],
    *,
    editing: ConfigSubentry | None,
) -> dict[str, str]:
    """Return what's wrong with a profile, by field, as the setup dialogs do."""
    subentries = entry.subentries.values()
    others = [
        subentry.title
        for subentry in subentries
        if subentry.subentry_type == kind
        and (editing is None or subentry.subentry_id != editing.subentry_id)
    ]
    errors: dict[str, str] = {}
    if error := profiles.check_name(name, others):
        errors["name"] = error
    if kind == SUBENTRY_SPOT:
        errors.update(profiles.check_spot(data))
        for key in (CONF_OFFSHORE, CONF_EXPOSED):
            data[key] = profiles.in_order(data[key], profiles.DIRECTIONS)
        return errors
    if kind == SUBENTRY_BOAT:
        errors.update(profiles.check_boat(data))
        return errors
    boats = {s.subentry_id for s in subentries if s.subentry_type == SUBENTRY_BOAT}
    spots = {s.subentry_id for s in subentries if s.subentry_type == SUBENTRY_SPOT}
    data[CONF_DAYS] = profiles.in_order(data[CONF_DAYS], WEEKDAYS)
    data[CONF_BOATS] = list(dict.fromkeys(data[CONF_BOATS]))
    errors.update(profiles.check_sailor(data, boats, spots))
    if (user := data.get(CONF_USER)) and await hass.auth.async_get_user(user) is None:
        errors[CONF_USER] = "unknown_user"
    if auto := data.get(CONF_AUTO_CALENDAR):
        auto[CONF_DAYS] = profiles.in_order(auto[CONF_DAYS], WEEKDAYS)
        entity = calendar_entity(hass, auto[CONF_CALENDAR])
        if entity is None or not supports(entity, CalendarEntityFeature.CREATE_EVENT):
            errors[CONF_CALENDAR] = "calendar_read_only"
    return errors


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "sailcast/settings/delete",
        probatio.Required("kind"): probatio.In(list(KINDS)),
        probatio.Required("profile"): cv.string,
    }
)
@websocket_api.require_admin
@callback
def ws_settings_delete(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Remove a spot, boat or sailor.

    A boat that's some sailor's only boat stays, so every sailor keeps one.
    A removed sailor's planned sails are no longer watched; their events stay
    in the calendars.
    """
    entry = _entry(hass)
    subentry = entry.subentries.get(msg["profile"]) if entry else None
    if entry is None or subentry is None or subentry.subentry_type != msg["kind"]:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "Not found")
        return
    if msg["kind"] == SUBENTRY_BOAT:
        for sailor in entry.runtime_data.profiles.sailors.values():
            if sailor.boats == (subentry.subentry_id,):
                connection.send_result(
                    msg["id"],
                    {"errors": {"base": "boat_in_use"}, "sailor": sailor.name},
                )
                return
    if msg["kind"] == SUBENTRY_SAILOR:
        hass.data[DATA_STORE].forget_sailor(subentry.subentry_id)
    hass.config_entries.async_remove_subentry(entry, subentry.subentry_id)
    connection.send_result(msg["id"], {"profile": subentry.subentry_id})


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "sailcast/settings/sources",
        probatio.Required(CONF_LATITUDE): cv.latitude,
        probatio.Required(CONF_LONGITUDE): cv.longitude,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_settings_sources(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Send the tide stations, current stations and warning zones near a pin."""
    found = await async_suggest(hass, msg[CONF_LATITUDE], msg[CONF_LONGITUDE])
    choices = {
        CONF_TIDE_STATION: found.tide,
        CONF_CURRENT_STATION: found.current,
        CONF_MARINE_ZONE: found.zones,
    }
    connection.send_result(
        msg["id"],
        {
            key: [
                {"id": choice.id, "name": choice.name, "distance": choice.distance_km}
                for choice in options
            ]
            for key, options in choices.items()
        }
        | {
            "suggested": {
                key: suggested(key, options) for key, options in choices.items()
            },
            "failed": found.failed,
        },
    )


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "sailcast/calendar/add",
        probatio.Required("spot"): cv.string,
        probatio.Required("sailor"): cv.string,
        probatio.Required("boat"): cv.string,
        probatio.Required("calendar"): cv.entity_id,
        probatio.Required("start"): cv.datetime,
        probatio.Required("end"): cv.datetime,
        probatio.Required("title"): cv.string,
        probatio.Optional("watch", default=True): cv.boolean,
    }
)
@websocket_api.async_response
async def ws_calendar_add(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Add a sailing window to one of the user's calendars."""
    if (data := _data(hass, connection, msg)) is None:
        return
    if not connection.user.permissions.check_entity(msg["calendar"], POLICY_CONTROL):
        raise Unauthorized(entity_id=msg["calendar"])
    found = data.profiles
    sailor = found.sailors.get(msg["sailor"])
    if (
        msg["spot"] not in found.spots
        or sailor is None
        or msg["boat"] not in sailor.boats
    ):
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_FOUND, "Unknown spot, sailor or boat"
        )
        return
    start, end = (
        dt_util.as_utc(dt_util.as_local(msg[key])) for key in ("start", "end")
    )
    title = msg["title"].strip()[:MAX_TITLE]
    if not title or not SHORTEST_SAIL <= end - start <= LONGEST_SAIL:
        connection.send_error(
            msg["id"],
            websocket_api.ERR_INVALID_FORMAT,
            "A sail needs a title and lasts from an hour to a day",
        )
        return
    try:
        sail = await data.planner.async_add(
            sailor=sailor.id,
            boat=msg["boat"],
            spot=msg["spot"],
            calendar=msg["calendar"],
            start=start,
            end=end,
            title=title,
            watch=msg["watch"],
            user=connection.user.id,
        )
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "failed", str(err))
        return
    connection.send_result(msg["id"], _planned(hass, data, sail))


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "sailcast/calendar/remove",
        probatio.Required("planned"): cv.string,
    }
)
@websocket_api.async_response
async def ws_calendar_remove(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Take a planned sail out of its calendar, or just stop watching it."""
    if (data := _data(hass, connection, msg)) is None:
        return
    sail = data.planner.store.get(msg["planned"])
    if sail is None:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "Not found")
        return
    if not connection.user.permissions.check_entity(sail.calendar, POLICY_CONTROL):
        raise Unauthorized(entity_id=sail.calendar)
    deleted = await data.planner.async_remove(sail)
    connection.send_result(msg["id"], {"deleted": deleted})


@websocket_api.websocket_command({probatio.Required("type"): "sailcast/planned/list"})
@callback
def ws_planned_list(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Send every planned sail still to come, and the days taken out."""
    if (data := _data(hass, connection, msg)) is None:
        return
    now = dt_util.utcnow()
    store = data.planner.store
    connection.send_result(
        msg["id"],
        {
            "planned": [
                _planned(hass, data, sail) for sail in store.planned if sail.end > now
            ],
            "skipped": {
                sailor: sorted(day.isoformat() for day in store.skipped(sailor))
                for sailor in data.profiles.sailors
            },
        },
    )


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "sailcast/planned/skipped",
        probatio.Required("sailor"): cv.string,
        probatio.Required("days"): [cv.date],
    }
)
@websocket_api.require_admin
@callback
def ws_planned_skipped(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Set the days a sailor took out, so the others can be added again."""
    if (data := _data(hass, connection, msg)) is None:
        return
    days: list[date] = msg["days"]
    data.planner.store.set_skipped(msg["sailor"], days)
    entry = _entry(hass)
    if entry is not None:
        entry.async_create_background_task(
            hass, data.planner.async_sync(), "sailcast planned sails"
        )
    connection.send_result(msg["id"], sorted(day.isoformat() for day in days))
