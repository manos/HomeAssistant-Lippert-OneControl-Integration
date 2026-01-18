"""Switch platform for Lippert OneControl."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
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
    """Set up Lippert OneControl switches."""
    coordinator: OneControlCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SwitchEntity] = []

    # Generator switch
    entities.append(OneControlGeneratorSwitch(coordinator))

    async_add_entities(entities)


class OneControlGeneratorSwitch(CoordinatorEntity[OneControlCoordinator], SwitchEntity):
    """Representation of Lippert OneControl generator switch."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_has_entity_name = True  # Append to device name
    _attr_name = "Power"  # Will show as "Generator Power"
    _attr_icon = "mdi:engine"

    def __init__(self, coordinator: OneControlCoordinator) -> None:
        """Initialize the generator switch."""
        super().__init__(coordinator)

        self._attr_unique_id = "lippert_onecontrol_generator_switch"

        # Generator gets its own device (shared with generator sensors)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "generator")},
            "name": "Generator",
            "manufacturer": "Lippert",
            "model": "Generator Genie",
            "via_device": (DOMAIN, "onecontrol_controller"),
            "suggested_area": "Utility",
        }

    @property
    def is_on(self) -> bool | None:
        """Return True if generator is running (or starting/priming)."""
        if self.coordinator.data is None:
            return None
        state = self.coordinator.data.generator_state
        if state is None:
            return None
        # States: 0=Off, 1=Priming, 2=Starting, 3=Running, 4=Stopping
        # Consider "on" if priming, starting, or running
        return state in (1, 2, 3)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the generator."""
        _LOGGER.info("Turning on generator")
        success = await self.coordinator.async_generator_on()
        if success:
            # Request coordinator refresh to get new state
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to turn on generator")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the generator."""
        _LOGGER.info("Turning off generator")
        success = await self.coordinator.async_generator_off()
        if success:
            # Request coordinator refresh to get new state
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to turn off generator")
