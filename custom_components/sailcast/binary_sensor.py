"""On/off sensors: official marine warnings, and whether it's good to sail now."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import ResultsCoordinator, SailCastConfigEntry
from .entity import SailorEntity, SpotEntity, async_remove_stale
from .profiles import Sailor, Spot


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SailCastConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a warning sensor per spot and a good-to-sail sensor per sailor and spot."""
    data = entry.runtime_data
    results = data.results
    added: list[str] = []
    for spot in data.profiles.spots.values():
        if spot.marine_zone:
            warning = MarineWarningSensor(results, spot)
            async_add_entities([warning], config_subentry_id=spot.id)
            added.append(f"{spot.id}_marine_warning")
    for sailor in data.profiles.sailors.values():
        entities = [
            GoodToSailSensor(results, sailor, spot)
            for spot in data.profiles.spots.values()
        ]
        async_add_entities(entities, config_subentry_id=sailor.id)
        added += [entity.unique_id for entity in entities if entity.unique_id]
    async_remove_stale(hass, entry, "binary_sensor", added)


class MarineWarningSensor(SpotEntity, BinarySensorEntity):
    """On while an official marine warning is in effect for the spot's zone.

    The attributes list every active warning, including ones that start later.
    """

    _attr_device_class = BinarySensorDeviceClass.SAFETY

    def __init__(self, coordinator: ResultsCoordinator, spot: Spot) -> None:
        """Set up the warning sensor."""
        super().__init__(coordinator, spot, "marine_warning")

    @property
    def is_on(self) -> bool | None:
        """Return whether a warning is in effect now."""
        if (conditions := self.conditions) is None:
            return None
        now = dt_util.utcnow()
        return any(alert.start <= now < alert.end for alert in conditions.alerts)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the zone and each warning's event and times."""
        if (conditions := self.conditions) is None:
            return None
        return {
            "zone": self.spot.marine_zone,
            "warnings": [
                {
                    "event": alert.event,
                    "start": alert.start.isoformat(),
                    "end": alert.end.isoformat(),
                }
                for alert in conditions.alerts
            ],
        }


class GoodToSailSensor(SailorEntity, BinarySensorEntity):
    """On during one of the sailor's windows at the spot, in their usual boat."""

    def __init__(
        self, coordinator: ResultsCoordinator, sailor: Sailor, spot: Spot
    ) -> None:
        """Set up the good-to-sail sensor."""
        super().__init__(coordinator, sailor, "good_to_sail", spot)

    @property
    def is_on(self) -> bool | None:
        """Return whether a sailing window is under way."""
        outlook = self.outlook()
        if outlook is None or (boat := outlook.default) is None:
            return None
        now = dt_util.utcnow()
        return any(
            window.start <= now < window.end
            for day in boat.days
            for window in day.windows
        )
