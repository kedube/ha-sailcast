"""What SailCast's entities share: the results, and a device per spot and sailor."""

from __future__ import annotations

from collections.abc import Iterable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, NAME
from .coordinator import ResultsCoordinator, SailCastConfigEntry
from .outlook import BoatOutlook, Outlook, SpotConditions
from .profiles import Sailor, Spot


class SailCastEntity(CoordinatorEntity[ResultsCoordinator]):
    """An entity that reads SailCast's results."""

    _attr_has_entity_name = True


class SpotEntity(SailCastEntity):
    """An entity on a spot's device."""

    def __init__(self, coordinator: ResultsCoordinator, spot: Spot, key: str) -> None:
        """Set up the entity for a spot."""
        super().__init__(coordinator)
        self.spot = spot
        self._attr_translation_key = key
        self._attr_unique_id = f"{spot.id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, spot.id)},
            name=spot.name,
            manufacturer=NAME,
            model="Spot",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def conditions(self) -> SpotConditions | None:
        """Return the spot's conditions."""
        return self.coordinator.data.conditions.get(self.spot.id)

    @property
    def available(self) -> bool:
        """Return whether there's a forecast for the spot."""
        return super().available and self.conditions is not None


class SailorEntity(SailCastEntity):
    """An entity on a sailor's device, for one spot or all of them."""

    def __init__(
        self,
        coordinator: ResultsCoordinator,
        sailor: Sailor,
        key: str,
        spot: Spot | None = None,
    ) -> None:
        """Set up the entity for a sailor, at one spot if given."""
        super().__init__(coordinator)
        self.sailor = sailor
        self.spot = spot
        self._attr_translation_key = key
        if spot is None:
            self._attr_unique_id = f"{sailor.id}_{key}"
        else:
            self._attr_unique_id = f"{sailor.id}_{spot.id}_{key}"
            self._attr_translation_placeholders = {"spot": spot.name}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, sailor.id)},
            name=sailor.name,
            manufacturer=NAME,
            model="Sailor",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def available(self) -> bool:
        """Return whether there's a forecast for the spot, or for any spot."""
        if not super().available:
            return False
        if self.spot is not None:
            return self.outlook() is not None
        return any(
            sailor == self.sailor.id for sailor, _ in self.coordinator.data.outlooks
        )

    def outlook(self, spot: Spot | None = None) -> Outlook | None:
        """Return the sailor's outlook at a spot (this entity's by default)."""
        spot = spot or self.spot
        if spot is None:
            return None
        return self.coordinator.data.outlook(self.sailor.id, spot.id)

    def now(self) -> tuple[BoatOutlook, int] | None:
        """Return the usual boat's outlook at this spot and this hour's index."""
        outlook = self.outlook()
        if outlook is None or (boat := outlook.default) is None:
            return None
        conditions = self.coordinator.data.conditions[outlook.spot.id]
        index = conditions.index_at(dt_util.utcnow())
        return None if index is None else (boat, index)


@callback
def async_remove_stale(
    hass: HomeAssistant, entry: SailCastConfigEntry, domain: str, keep: Iterable[str]
) -> None:
    """Remove a platform's entities for spots, sailors or boats that are gone."""
    registry = er.async_get(hass)
    kept = set(keep)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.domain == domain and entity.unique_id not in kept:
            registry.async_remove(entity.entity_id)
