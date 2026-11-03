"""Set up SailCast and add its spots, boats and sailors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from typing import Any

from homeassistant.components.calendar import CalendarEntityFeature
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentry,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import (
    CONF_LATITUDE,
    CONF_LOCATION,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_RADIUS,
    WEEKDAYS,
    UnitOfLength,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    EntityWithDeviceFilterSelectorConfig,
    LocationSelector,
    LocationSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TimeSelector,
)
from homeassistant.util.unit_conversion import DistanceConverter, TemperatureConverter
import probatio

from . import profiles
from .const import (
    CONF_AHEAD,
    CONF_AIRPORT,
    CONF_AUTO_CALENDAR,
    CONF_AUTO_DAYS,
    CONF_AUTO_SPOTS,
    CONF_BOATS,
    CONF_BUOY,
    CONF_CALENDAR,
    CONF_COLDEST,
    CONF_COMFORT,
    CONF_CURRENT_STATION,
    CONF_DAYS,
    CONF_DEFAULT_BOAT,
    CONF_END,
    CONF_EXPOSED,
    CONF_FETCH,
    CONF_IDEAL_HIGH,
    CONF_IDEAL_LOW,
    CONF_LENGTH,
    CONF_MARINE_ZONE,
    CONF_MIN_SCORE,
    CONF_OFFSHORE,
    CONF_OTHER_BOATS,
    CONF_RAIN,
    CONF_SENSORS,
    CONF_SIZE_CLASS,
    CONF_SKILL,
    CONF_SOURCE_NAMES,
    CONF_SOURCE_POINTS,
    CONF_SPOTS,
    CONF_START,
    CONF_TIDE_STATION,
    CONF_USER,
    CONF_WATER_TYPE,
    DOMAIN,
    NAME,
    SUBENTRY_BOAT,
    SUBENTRY_SAILOR,
    SUBENTRY_SPOT,
)
from .geo import DIRECTIONS
from .planner import calendar_entity, supports
from .sources import Choice, async_suggest, suggested

# The "no source" choice in the sources step.
NONE = "none"
SOURCES = (
    CONF_TIDE_STATION,
    CONF_CURRENT_STATION,
    CONF_MARINE_ZONE,
    CONF_BUOY,
    CONF_AIRPORT,
)
# Sources whose position is kept, for the forecast where they are.
PLACED = (CONF_BUOY, CONF_AIRPORT)
SENSOR_CLASSES = {
    "wind": SensorDeviceClass.WIND_SPEED,
    "gust": SensorDeviceClass.WIND_SPEED,
    "wind_direction": SensorDeviceClass.WIND_DIRECTION,
    "temperature": SensorDeviceClass.TEMPERATURE,
    "water_temperature": SensorDeviceClass.TEMPERATURE,
}


class SailCastConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up SailCast. One entry holds every spot, boat and sailor."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the safety note, then create the entry."""
        if user_input is not None:
            return self.async_create_entry(title=NAME, data={})
        return self.async_show_form(step_id="user")

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return the kinds of profile SailCast holds."""
        return {
            SUBENTRY_SPOT: SpotFlow,
            SUBENTRY_BOAT: BoatFlow,
            SUBENTRY_SAILOR: SailorFlow,
        }


class ProfileFlow(ConfigSubentryFlow, ABC):
    """Add or edit a profile. Each kind of profile defines its own form."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a profile."""
        return await self._async_step_profile("user", user_input, None)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Edit a profile."""
        return await self._async_step_profile(
            "reconfigure", user_input, self._get_reconfigure_subentry()
        )

    async def _async_step_profile(
        self,
        step_id: str,
        user_input: dict[str, Any] | None,
        subentry: ConfigSubentry | None,
    ) -> SubentryFlowResult:
        if reason := self._abort_reason():
            return self.async_abort(reason=reason)
        await self._async_prepare()
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            data = self._to_data(user_input)
            if error := profiles.check_name(name, self._names_in_use(subentry)):
                errors[CONF_NAME] = error
            errors.update(self._check(data))
            if not errors:
                return await self._async_done(name, data, subentry)
        elif subentry is not None:
            user_input = self._to_form(subentry)
        else:
            user_input = self._defaults()
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(self._schema(), user_input),
            errors=errors,
        )

    async def _async_done(
        self, name: str, data: dict[str, Any], subentry: ConfigSubentry | None
    ) -> SubentryFlowResult:
        """Finish once the form is valid. Spots have another step."""
        return self._save(name, data, subentry)

    @callback
    def _save(
        self, name: str, data: dict[str, Any], subentry: ConfigSubentry | None
    ) -> SubentryFlowResult:
        """Add the profile, or save the changes to it."""
        if subentry is None:
            return self.async_create_entry(title=name, data=data)
        return self.async_update_and_abort(
            self._get_entry(), subentry, title=name, data=data
        )

    def _subentries(self, subentry_type: str) -> list[ConfigSubentry]:
        return [
            subentry
            for subentry in self._get_entry().subentries.values()
            if subentry.subentry_type == subentry_type
        ]

    def _names_in_use(self, editing: ConfigSubentry | None) -> list[str]:
        """Return the names of the other profiles of this kind."""
        return [
            subentry.title
            for subentry in self._subentries(self._subentry_type)
            if editing is None or subentry.subentry_id != editing.subentry_id
        ]

    def _abort_reason(self) -> str | None:
        """Return why the form can't be shown, if it can't."""
        return None

    async def _async_prepare(self) -> None:
        """Look up anything the form needs."""

    def _defaults(self) -> dict[str, Any]:
        """Return suggested values for a new profile."""
        return {}

    @abstractmethod
    def _schema(self) -> probatio.Schema:
        """Return the form."""

    @abstractmethod
    def _to_data(self, user_input: Mapping[str, Any]) -> dict[str, Any]:
        """Turn the form's values into the subentry's data."""

    @abstractmethod
    def _to_form(self, subentry: ConfigSubentry) -> dict[str, Any]:
        """Turn a subentry back into the form's values."""

    @abstractmethod
    def _check(self, data: Mapping[str, Any]) -> dict[str, str]:
        """Return errors in the data, by form field."""


class SpotFlow(ProfileFlow):
    """Add or edit a spot, then pick its data sources."""

    _pending: tuple[str, dict[str, Any], ConfigSubentry | None]
    # The names and positions of the sources shown, by source and ID.
    _names: dict[str, dict[str, str]]
    _points: dict[str, dict[str, list[float]]]

    async def _async_done(
        self, name: str, data: dict[str, Any], subentry: ConfigSubentry | None
    ) -> SubentryFlowResult:
        self._pending = (name, data, subentry)
        self._names = {}
        self._points = {}
        return await self.async_step_sources()

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Pick the stations, marine zone, buoy, airport and your own sensors.

        SailCast suggests the nearest of each; None is always a choice.
        """
        name, data, subentry = self._pending
        saved = dict(subentry.data) if subentry else {}
        if user_input is not None:
            sources = {
                key: None if user_input.get(key, NONE) == NONE else user_input[key]
                for key in SOURCES
            }
            return self._save(
                name,
                data
                | sources
                | {
                    CONF_SOURCE_NAMES: self._chosen_names(sources, saved),
                    CONF_SOURCE_POINTS: self._chosen_points(sources, saved),
                    CONF_SENSORS: {
                        key: entity_id
                        for key, entity_id in (
                            user_input.get(CONF_SENSORS) or {}
                        ).items()
                        if entity_id
                    },
                },
                subentry,
            )
        suggestions = await async_suggest(
            self.hass, data[CONF_LATITUDE], data[CONF_LONGITUDE]
        )
        choices = {
            CONF_TIDE_STATION: suggestions.tide,
            CONF_CURRENT_STATION: suggestions.current,
            CONF_MARINE_ZONE: suggestions.zones,
            CONF_BUOY: suggestions.buoys,
            CONF_AIRPORT: suggestions.airports,
        }
        self._names = {
            key: {choice.id: choice.name for choice in found}
            for key, found in choices.items()
        }
        self._points = {
            key: {
                choice.id: [choice.latitude, choice.longitude]
                for choice in choices[key]
                if choice.latitude is not None and choice.longitude is not None
            }
            for key in PLACED
        }
        schema: dict[probatio.Marker, Any] = {}
        values: dict[str, Any] = {}
        for key, found in choices.items():
            options = [SelectOptionDict(value=NONE, label="None")] + [
                SelectOptionDict(value=choice.id, label=self._label(key, choice))
                for choice in found
            ]
            chosen = saved.get(key)
            if chosen and chosen not in {choice.id for choice in found}:
                options.append(SelectOptionDict(value=chosen, label=chosen))
            schema[probatio.Required(key)] = SelectSelector(
                SelectSelectorConfig(
                    options=options,
                    translation_key="source",
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
            if key in saved:
                values[key] = chosen or NONE
            else:
                values[key] = suggested(key, found) or NONE
        schema[probatio.Required(CONF_SENSORS)] = section(
            probatio.Schema(
                {
                    probatio.Optional(key): EntitySelector(
                        EntitySelectorConfig(domain="sensor", device_class=device_class)
                    )
                    for key, device_class in SENSOR_CLASSES.items()
                }
            ),
            {"collapsed": True},
        )
        values[CONF_SENSORS] = dict(saved.get(CONF_SENSORS) or {})
        return self.async_show_form(
            step_id="sources",
            data_schema=self.add_suggested_values_to_schema(
                probatio.Schema(schema), values
            ),
            errors={"base": "suggestions_unavailable"} if suggestions.failed else {},
        )

    def _chosen_names(
        self, sources: dict[str, str | None], saved: dict[str, Any]
    ) -> dict[str, str]:
        """Return each chosen source's name, or the one saved with it."""
        known = dict(saved.get(CONF_SOURCE_NAMES) or {})
        names = {}
        for key, value in sources.items():
            source_name = self._names.get(key, {}).get(value or "")
            if value and value == saved.get(key):
                source_name = source_name or known.get(key)
            if source_name:
                names[key] = source_name
        return names

    def _chosen_points(
        self, sources: dict[str, str | None], saved: dict[str, Any]
    ) -> dict[str, list[float]]:
        """Return the chosen buoy's and airport's positions, or the saved ones."""
        known = dict(saved.get(CONF_SOURCE_POINTS) or {})
        points = {}
        for key in PLACED:
            value = sources[key]
            point = self._points.get(key, {}).get(value or "")
            if value and value == saved.get(key):
                point = point or known.get(key)
            if point:
                points[key] = list(point)
        return points

    @property
    def _distance_unit(self) -> UnitOfLength:
        """Return miles with US units and kilometers otherwise. Data is in km."""
        if self.hass.config.units.length_unit == UnitOfLength.MILES:
            return UnitOfLength.MILES
        return UnitOfLength.KILOMETERS

    def _label(self, key: str, choice: Choice) -> str:
        """Label a source with its name, ID and distance."""
        station = choice.id.partition("_")[0]
        if key == CONF_MARINE_ZONE and choice.distance_km == 0:
            return f"{choice.name} ({station})"
        if self.hass.config.units.length_unit == UnitOfLength.MILES:
            distance = f"{choice.distance_km / 1.609344:.1f} mi"
        else:
            distance = f"{choice.distance_km:.1f} km"
        return f"{choice.name} ({station}), {distance}"

    def _schema(self) -> probatio.Schema:
        return probatio.Schema(
            {
                probatio.Required(CONF_NAME): TextSelector(),
                probatio.Required(CONF_LOCATION): LocationSelector(
                    LocationSelectorConfig(radius=True, icon="mdi:sail-boat")
                ),
                probatio.Required(CONF_WATER_TYPE): _select(
                    profiles.WaterType, CONF_WATER_TYPE
                ),
                probatio.Optional(CONF_OFFSHORE): _select(
                    DIRECTIONS, "direction", multiple=True
                ),
                probatio.Optional(CONF_EXPOSED): _select(
                    DIRECTIONS, "direction", multiple=True
                ),
                probatio.Optional(CONF_FETCH): NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        step=0.1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement=self._distance_unit,
                    )
                ),
            }
        )

    def _defaults(self) -> dict[str, Any]:
        return {
            CONF_LOCATION: {
                CONF_LATITUDE: self.hass.config.latitude,
                CONF_LONGITUDE: self.hass.config.longitude,
                CONF_RADIUS: profiles.DEFAULT_RADIUS,
            }
        }

    def _to_data(self, user_input: Mapping[str, Any]) -> dict[str, Any]:
        location = user_input[CONF_LOCATION]
        return {
            CONF_LATITUDE: location[CONF_LATITUDE],
            CONF_LONGITUDE: location[CONF_LONGITUDE],
            CONF_RADIUS: location.get(CONF_RADIUS, profiles.DEFAULT_RADIUS),
            CONF_WATER_TYPE: user_input[CONF_WATER_TYPE],
            CONF_OFFSHORE: profiles.in_order(
                user_input.get(CONF_OFFSHORE, ()), DIRECTIONS
            ),
            CONF_EXPOSED: profiles.in_order(
                user_input.get(CONF_EXPOSED, ()), DIRECTIONS
            ),
            CONF_FETCH: (
                round(
                    DistanceConverter.convert(
                        fetch, self._distance_unit, UnitOfLength.KILOMETERS
                    ),
                    3,
                )
                if (fetch := user_input.get(CONF_FETCH))
                else None
            ),
        }

    def _to_form(self, subentry: ConfigSubentry) -> dict[str, Any]:
        data = subentry.data
        return {
            CONF_NAME: subentry.title,
            CONF_LOCATION: {
                key: data[key] for key in (CONF_LATITUDE, CONF_LONGITUDE, CONF_RADIUS)
            },
            CONF_WATER_TYPE: data[CONF_WATER_TYPE],
            CONF_OFFSHORE: list(data[CONF_OFFSHORE]),
            CONF_EXPOSED: list(data[CONF_EXPOSED]),
        } | (
            {
                CONF_FETCH: round(
                    DistanceConverter.convert(
                        fetch, UnitOfLength.KILOMETERS, self._distance_unit
                    ),
                    1,
                )
            }
            if (fetch := data.get(CONF_FETCH))
            else {}
        )

    def _check(self, data: Mapping[str, Any]) -> dict[str, str]:
        errors = profiles.check_spot(data)
        # The radius is drawn on the location field's map.
        if CONF_RADIUS in errors:
            errors[CONF_LOCATION] = errors.pop(CONF_RADIUS)
        return errors


class BoatFlow(ProfileFlow):
    """Add or edit a boat."""

    @property
    def _length_unit(self) -> UnitOfLength:
        """Return feet with US units and meters otherwise. Data is in meters."""
        if self.hass.config.units.length_unit == UnitOfLength.MILES:
            return UnitOfLength.FEET
        return UnitOfLength.METERS

    def _schema(self) -> probatio.Schema:
        return probatio.Schema(
            {
                probatio.Required(CONF_NAME): TextSelector(),
                probatio.Required(CONF_SIZE_CLASS): _select(
                    profiles.SizeClass, CONF_SIZE_CLASS
                ),
                probatio.Required(CONF_LENGTH): NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        step=0.1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement=self._length_unit,
                    )
                ),
            }
        )

    def _to_data(self, user_input: Mapping[str, Any]) -> dict[str, Any]:
        length = DistanceConverter.convert(
            user_input[CONF_LENGTH], self._length_unit, UnitOfLength.METERS
        )
        return {
            CONF_SIZE_CLASS: user_input[CONF_SIZE_CLASS],
            CONF_LENGTH: round(length, 3),
        }

    def _to_form(self, subentry: ConfigSubentry) -> dict[str, Any]:
        length = DistanceConverter.convert(
            subentry.data[CONF_LENGTH], UnitOfLength.METERS, self._length_unit
        )
        return {
            CONF_NAME: subentry.title,
            CONF_SIZE_CLASS: subentry.data[CONF_SIZE_CLASS],
            CONF_LENGTH: round(length, 1),
        }

    def _check(self, data: Mapping[str, Any]) -> dict[str, str]:
        return profiles.check_boat(data)


class SailorFlow(ProfileFlow):
    """Add or edit a sailor. Every sailor needs at least one boat.

    Comfort settings and automatic calendar adding are in sections that start
    folded away.
    """

    _users: list[SelectOptionDict]

    async def _async_prepare(self) -> None:
        """Look up the people who can be linked to a sailor."""
        users = await self.hass.auth.async_get_users()
        self._users = [
            SelectOptionDict(value=user.id, label=user.name or user.id)
            for user in sorted(users, key=lambda user: (user.name or "").casefold())
            if not user.system_generated and user.is_active
        ]

    def _boat_options(self) -> list[SelectOptionDict]:
        boats = sorted(
            self._subentries(SUBENTRY_BOAT), key=lambda boat: boat.title.casefold()
        )
        return [
            SelectOptionDict(value=boat.subentry_id, label=boat.title) for boat in boats
        ]

    def _spot_options(self) -> list[SelectOptionDict]:
        spots = sorted(
            self._subentries(SUBENTRY_SPOT), key=lambda spot: spot.title.casefold()
        )
        return [
            SelectOptionDict(value=spot.subentry_id, label=spot.title) for spot in spots
        ]

    @property
    def _temperature_unit(self) -> str:
        return self.hass.config.units.temperature_unit

    def _abort_reason(self) -> str | None:
        return None if self._subentries(SUBENTRY_BOAT) else "no_boats"

    def _schema(self) -> probatio.Schema:
        boats = self._boat_options()
        wind = NumberSelectorConfig(
            min=0,
            max=profiles.MAX_IDEAL_WIND,
            step=1,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement=UnitOfSpeed.KNOTS,
        )
        return probatio.Schema(
            {
                probatio.Required(CONF_NAME): TextSelector(),
                probatio.Required(CONF_SKILL): _select(profiles.Skill, CONF_SKILL),
                probatio.Required(CONF_DEFAULT_BOAT): SelectSelector(
                    SelectSelectorConfig(
                        options=boats, mode=SelectSelectorMode.DROPDOWN
                    )
                ),
                probatio.Optional(CONF_OTHER_BOATS): SelectSelector(
                    SelectSelectorConfig(
                        options=boats, multiple=True, mode=SelectSelectorMode.DROPDOWN
                    )
                ),
                probatio.Required(CONF_DAYS): _select(
                    WEEKDAYS, CONF_DAYS, multiple=True, mode=SelectSelectorMode.LIST
                ),
                probatio.Optional(CONF_START): TimeSelector(),
                probatio.Optional(CONF_END): TimeSelector(),
                probatio.Optional(CONF_USER): SelectSelector(
                    SelectSelectorConfig(
                        options=self._users, mode=SelectSelectorMode.DROPDOWN
                    )
                ),
                probatio.Required(CONF_COMFORT): section(
                    probatio.Schema(
                        {
                            probatio.Optional(CONF_IDEAL_LOW): NumberSelector(wind),
                            probatio.Optional(CONF_IDEAL_HIGH): NumberSelector(wind),
                            probatio.Optional(CONF_COLDEST): NumberSelector(
                                NumberSelectorConfig(
                                    step=1,
                                    mode=NumberSelectorMode.BOX,
                                    unit_of_measurement=self._temperature_unit,
                                )
                            ),
                            probatio.Required(CONF_RAIN): _select(
                                profiles.RainTolerance, CONF_RAIN
                            ),
                        }
                    ),
                    {"collapsed": True},
                ),
                probatio.Required(CONF_AUTO_CALENDAR): section(
                    probatio.Schema(
                        {
                            probatio.Optional(CONF_CALENDAR): EntitySelector(
                                EntitySelectorConfig(
                                    filter=EntityWithDeviceFilterSelectorConfig(
                                        domain="calendar",
                                        supported_features=[
                                            "calendar.CalendarEntityFeature.CREATE_EVENT"
                                        ],
                                    )
                                )
                            ),
                            probatio.Optional(CONF_AUTO_DAYS): _select(
                                WEEKDAYS, CONF_DAYS, multiple=True
                            ),
                            probatio.Optional(CONF_MIN_SCORE): _select(
                                map(str, profiles.MIN_SCORES), CONF_MIN_SCORE
                            ),
                            probatio.Optional(CONF_AHEAD): _select(
                                map(str, profiles.AHEAD_DAYS),
                                CONF_AHEAD,
                                mode=SelectSelectorMode.DROPDOWN,
                            ),
                            probatio.Optional(CONF_AUTO_SPOTS): SelectSelector(
                                SelectSelectorConfig(
                                    options=self._spot_options(),
                                    multiple=True,
                                    mode=SelectSelectorMode.DROPDOWN,
                                )
                            ),
                        }
                    ),
                    {"collapsed": True},
                ),
            }
        )

    def _defaults(self) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            CONF_DAYS: list(WEEKDAYS),
            CONF_COMFORT: {CONF_RAIN: profiles.RainTolerance.SOME.value},
            CONF_AUTO_CALENDAR: _auto_defaults(self._spot_options()),
        }
        if len(boats := self._boat_options()) == 1:
            defaults[CONF_DEFAULT_BOAT] = boats[0]["value"]
        return defaults

    def _to_data(self, user_input: Mapping[str, Any]) -> dict[str, Any]:
        default = user_input[CONF_DEFAULT_BOAT]
        comfort = user_input.get(CONF_COMFORT, {})
        coldest = comfort.get(CONF_COLDEST)
        if coldest is not None:
            coldest = round(
                TemperatureConverter.convert(
                    coldest, self._temperature_unit, UnitOfTemperature.CELSIUS
                ),
                1,
            )
        auto = user_input.get(CONF_AUTO_CALENDAR, {})
        return {
            CONF_SKILL: user_input[CONF_SKILL],
            CONF_BOATS: list(
                dict.fromkeys([default, *user_input.get(CONF_OTHER_BOATS, ())])
            ),
            CONF_DAYS: profiles.in_order(user_input[CONF_DAYS], WEEKDAYS),
            CONF_START: user_input.get(CONF_START),
            CONF_END: user_input.get(CONF_END),
            CONF_USER: user_input.get(CONF_USER) or None,
            CONF_COMFORT: {
                CONF_IDEAL_LOW: comfort.get(CONF_IDEAL_LOW),
                CONF_IDEAL_HIGH: comfort.get(CONF_IDEAL_HIGH),
                CONF_COLDEST: coldest,
                CONF_RAIN: comfort.get(CONF_RAIN, profiles.RainTolerance.SOME.value),
            },
            CONF_AUTO_CALENDAR: {
                CONF_CALENDAR: auto[CONF_CALENDAR],
                CONF_DAYS: profiles.in_order(auto.get(CONF_AUTO_DAYS, ()), WEEKDAYS),
                CONF_MIN_SCORE: int(auto.get(CONF_MIN_SCORE, profiles.MIN_SCORES[0])),
                CONF_AHEAD: int(auto.get(CONF_AHEAD, profiles.AHEAD_DAYS[1])),
                CONF_SPOTS: list(auto.get(CONF_AUTO_SPOTS, ())),
            }
            if auto.get(CONF_CALENDAR)
            else None,
        }

    def _to_form(self, subentry: ConfigSubentry) -> dict[str, Any]:
        data = subentry.data
        existing = {option["value"] for option in self._boat_options()}
        boats = [boat for boat in data[CONF_BOATS] if boat in existing]
        comfort = dict(data.get(CONF_COMFORT) or {})
        if comfort.get(CONF_COLDEST) is not None:
            comfort[CONF_COLDEST] = round(
                TemperatureConverter.convert(
                    comfort[CONF_COLDEST],
                    UnitOfTemperature.CELSIUS,
                    self._temperature_unit,
                )
            )
        auto = data.get(CONF_AUTO_CALENDAR)
        form: dict[str, Any] = {
            CONF_NAME: subentry.title,
            CONF_SKILL: data[CONF_SKILL],
            CONF_DAYS: list(data[CONF_DAYS]),
            CONF_COMFORT: {
                CONF_RAIN: profiles.RainTolerance.SOME.value,
                **{key: value for key, value in comfort.items() if value is not None},
            },
            CONF_AUTO_CALENDAR: {
                CONF_CALENDAR: auto[CONF_CALENDAR],
                CONF_AUTO_DAYS: list(auto[CONF_DAYS]),
                CONF_MIN_SCORE: str(auto[CONF_MIN_SCORE]),
                CONF_AHEAD: str(auto[CONF_AHEAD]),
                CONF_AUTO_SPOTS: list(auto[CONF_SPOTS]),
            }
            if auto
            else _auto_defaults(self._spot_options()),
        }
        if boats:
            form[CONF_DEFAULT_BOAT] = boats[0]
            form[CONF_OTHER_BOATS] = boats[1:]
        form.update(
            {
                key: data[key]
                for key in (CONF_START, CONF_END, CONF_USER)
                if data.get(key)
            }
        )
        return form

    def _check(self, data: Mapping[str, Any]) -> dict[str, str]:
        boats = {option["value"] for option in self._boat_options()}
        spots = {option["value"] for option in self._spot_options()}
        errors = profiles.check_sailor(data, boats, spots)
        # Boat problems show on the usual boat, the one field that's required.
        if CONF_BOATS in errors:
            errors[CONF_DEFAULT_BOAT] = errors.pop(CONF_BOATS)
        if (auto := data[CONF_AUTO_CALENDAR]) and not (
            (entity := calendar_entity(self.hass, auto[CONF_CALENDAR]))
            and supports(entity, CalendarEntityFeature.CREATE_EVENT)
        ):
            errors[CONF_CALENDAR] = "calendar_read_only"
        return errors


def _auto_defaults(spots: list[SelectOptionDict]) -> dict[str, Any]:
    """Return automatic adding's suggestions: weekends, good, three days."""
    return {
        CONF_AUTO_DAYS: ["sat", "sun"],
        CONF_MIN_SCORE: str(profiles.MIN_SCORES[0]),
        CONF_AHEAD: str(profiles.AHEAD_DAYS[1]),
        CONF_AUTO_SPOTS: [spot["value"] for spot in spots],
    }


def _select(
    options: Iterable[str],
    translation_key: str,
    *,
    multiple: bool = False,
    mode: SelectSelectorMode | None = None,
) -> SelectSelector:
    """Return a selector for fixed options, labeled by the translations."""
    if mode is None:
        mode = SelectSelectorMode.DROPDOWN if multiple else SelectSelectorMode.LIST
    return SelectSelector(
        SelectSelectorConfig(
            options=[str(option) for option in options],
            translation_key=translation_key,
            multiple=multiple,
            mode=mode,
        )
    )
