"""Set up SailCast and add its spots, boats and sailors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from typing import Any

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
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
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
from homeassistant.util.unit_conversion import DistanceConverter
import probatio

from . import profiles
from .const import (
    CONF_BOATS,
    CONF_DAYS,
    CONF_DEFAULT_BOAT,
    CONF_END,
    CONF_EXPOSED,
    CONF_LENGTH,
    CONF_OFFSHORE,
    CONF_OTHER_BOATS,
    CONF_SIZE_CLASS,
    CONF_SKILL,
    CONF_START,
    CONF_WATER_TYPE,
    DOMAIN,
    NAME,
    SUBENTRY_BOAT,
    SUBENTRY_SAILOR,
    SUBENTRY_SPOT,
)


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
        return self._async_step_profile("user", user_input, None)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Edit a profile."""
        return self._async_step_profile(
            "reconfigure", user_input, self._get_reconfigure_subentry()
        )

    @callback
    def _async_step_profile(
        self,
        step_id: str,
        user_input: dict[str, Any] | None,
        subentry: ConfigSubentry | None,
    ) -> SubentryFlowResult:
        if reason := self._abort_reason():
            return self.async_abort(reason=reason)
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            data = self._to_data(user_input)
            if error := profiles.check_name(name, self._names_in_use(subentry)):
                errors[CONF_NAME] = error
            errors.update(self._check(data))
            if not errors:
                if subentry is None:
                    return self.async_create_entry(title=name, data=data)
                return self.async_update_and_abort(
                    self._get_entry(), subentry, title=name, data=data
                )
        elif subentry is not None:
            user_input = self._to_form(subentry)
        else:
            user_input = self._defaults()
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(self._schema(), user_input),
            errors=errors,
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
    """Add or edit a spot."""

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
                    profiles.DIRECTIONS, "direction", multiple=True
                ),
                probatio.Optional(CONF_EXPOSED): _select(
                    profiles.DIRECTIONS, "direction", multiple=True
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
            CONF_OFFSHORE: _in_order(
                user_input.get(CONF_OFFSHORE, ()), profiles.DIRECTIONS
            ),
            CONF_EXPOSED: _in_order(
                user_input.get(CONF_EXPOSED, ()), profiles.DIRECTIONS
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
        }

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
    """Add or edit a sailor. Every sailor needs at least one boat."""

    def _boat_options(self) -> list[SelectOptionDict]:
        boats = sorted(
            self._subentries(SUBENTRY_BOAT), key=lambda boat: boat.title.casefold()
        )
        return [
            SelectOptionDict(value=boat.subentry_id, label=boat.title) for boat in boats
        ]

    def _abort_reason(self) -> str | None:
        return None if self._subentries(SUBENTRY_BOAT) else "no_boats"

    def _schema(self) -> probatio.Schema:
        boats = self._boat_options()
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
            }
        )

    def _defaults(self) -> dict[str, Any]:
        defaults: dict[str, Any] = {CONF_DAYS: list(WEEKDAYS)}
        if len(boats := self._boat_options()) == 1:
            defaults[CONF_DEFAULT_BOAT] = boats[0]["value"]
        return defaults

    def _to_data(self, user_input: Mapping[str, Any]) -> dict[str, Any]:
        default = user_input[CONF_DEFAULT_BOAT]
        return {
            CONF_SKILL: user_input[CONF_SKILL],
            CONF_BOATS: list(
                dict.fromkeys([default, *user_input.get(CONF_OTHER_BOATS, ())])
            ),
            CONF_DAYS: _in_order(user_input[CONF_DAYS], WEEKDAYS),
            CONF_START: user_input.get(CONF_START),
            CONF_END: user_input.get(CONF_END),
        }

    def _to_form(self, subentry: ConfigSubentry) -> dict[str, Any]:
        data = subentry.data
        existing = {option["value"] for option in self._boat_options()}
        boats = [boat for boat in data[CONF_BOATS] if boat in existing]
        form: dict[str, Any] = {
            CONF_NAME: subentry.title,
            CONF_SKILL: data[CONF_SKILL],
            CONF_DAYS: list(data[CONF_DAYS]),
        }
        if boats:
            form[CONF_DEFAULT_BOAT] = boats[0]
            form[CONF_OTHER_BOATS] = boats[1:]
        form.update({key: data[key] for key in (CONF_START, CONF_END) if data[key]})
        return form

    def _check(self, data: Mapping[str, Any]) -> dict[str, str]:
        boats = {option["value"] for option in self._boat_options()}
        errors = profiles.check_sailor(data, boats)
        # Boat problems show on the usual boat, the one field that's required.
        if CONF_BOATS in errors:
            errors[CONF_DEFAULT_BOAT] = errors.pop(CONF_BOATS)
        return errors


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


def _in_order(values: Iterable[str], order: Iterable[str]) -> list[str]:
    """Return the chosen values in a fixed order, such as Monday to Sunday."""
    chosen = set(values)
    return [value for value in order if value in chosen]
