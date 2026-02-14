"""Button platform for Lippert OneControl."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OneControlCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lippert OneControl buttons."""
    coordinator: OneControlCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[ButtonEntity] = [
        OneControlAutoLevelButton(coordinator),
        OneControlRetractButton(coordinator),
        OneControlLevelerCancelButton(coordinator),
    ]

    async_add_entities(entities)


class OneControlAutoLevelButton(CoordinatorEntity[OneControlCoordinator], ButtonEntity):
    """Button to trigger auto-leveling sequence."""

    _attr_has_entity_name = True
    _attr_name = "Auto Level"
    _attr_icon = "mdi:arrow-expand-vertical"

    def __init__(self, coordinator: OneControlCoordinator) -> None:
        """Initialize the auto level button."""
        super().__init__(coordinator)

        self._attr_unique_id = "lippert_onecontrol_leveler_auto_level"

        # Leveler gets its own device
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "leveler")},
            "name": "Leveler",
            "manufacturer": "Lippert",
            "model": "4-Point Hydraulic Leveler",
            "via_device": (DOMAIN, "onecontrol_controller"),
            "suggested_area": "Utility",
        }

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.debug("Auto Level button pressed")
        success = await self.coordinator.async_leveler_auto_level()
        if not success:
            _LOGGER.error("Auto Level failed")


class OneControlRetractButton(CoordinatorEntity[OneControlCoordinator], ButtonEntity):
    """Button to retract all leveler jacks."""

    _attr_has_entity_name = True
    _attr_name = "Retract"
    _attr_icon = "mdi:arrow-collapse-vertical"

    def __init__(self, coordinator: OneControlCoordinator) -> None:
        """Initialize the retract button."""
        super().__init__(coordinator)

        self._attr_unique_id = "lippert_onecontrol_leveler_retract"

        # Share device with auto level
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "leveler")},
            "name": "Leveler",
            "manufacturer": "Lippert",
            "model": "4-Point Hydraulic Leveler",
            "via_device": (DOMAIN, "onecontrol_controller"),
            "suggested_area": "Utility",
        }

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.debug("Retract button pressed")
        success = await self.coordinator.async_leveler_retract()
        if not success:
            _LOGGER.error("Retract failed")


class OneControlLevelerCancelButton(CoordinatorEntity[OneControlCoordinator], ButtonEntity):
    """Button to cancel current leveler operation."""

    _attr_has_entity_name = True
    _attr_name = "Cancel"
    _attr_icon = "mdi:stop-circle-outline"

    def __init__(self, coordinator: OneControlCoordinator) -> None:
        """Initialize the cancel button."""
        super().__init__(coordinator)

        self._attr_unique_id = "lippert_onecontrol_leveler_cancel"

        # Share device with auto level
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "leveler")},
            "name": "Leveler",
            "manufacturer": "Lippert",
            "model": "4-Point Hydraulic Leveler",
            "via_device": (DOMAIN, "onecontrol_controller"),
            "suggested_area": "Utility",
        }

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.debug("Cancel button pressed")
        success = await self.coordinator.async_leveler_cancel()
        if not success:
            _LOGGER.error("Cancel failed")
