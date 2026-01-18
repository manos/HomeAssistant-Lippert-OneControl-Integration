"""Light platform for Lippert OneControl."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import LightEntity, ColorMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_DISCOVERED_LIGHTS, get_suggested_area
from .coordinator import OneControlCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lippert OneControl lights."""
    coordinator: OneControlCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Get discovered lights from config entry data
    discovered_lights = entry.data.get(CONF_DISCOVERED_LIGHTS, {})
    
    entities = []
    for counter_str, info in discovered_lights.items():
        counter = int(counter_str, 16) if isinstance(counter_str, str) else counter_str
        entities.append(
            OneControlLight(
                coordinator=coordinator,
                counter=counter,
                name=info["name"],
                func_id=info.get("func_id"),
            )
        )

    async_add_entities(entities)


class OneControlLight(CoordinatorEntity[OneControlCoordinator], LightEntity):
    """Representation of a Lippert OneControl light."""

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}
    # Don't use entity name - we want full control over the name
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: OneControlCoordinator,
        counter: int,
        name: str,
        func_id: int | None = None,
    ) -> None:
        """Initialize the light."""
        super().__init__(coordinator)
        self._counter = counter
        self._func_id = func_id
        
        # Use just the device name (e.g., "Kitchen Ceiling Light")
        self._attr_name = name
        
        # Unique ID based on counter
        self._attr_unique_id = f"lippert_onecontrol_light_{counter:02x}"
        
        # Each light gets its own device for better organization
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"light_{counter:02x}")},
            "name": name,
            "manufacturer": "Lippert",
            "model": "OneControl Light",
            "via_device": (DOMAIN, "onecontrol_controller"),
            "suggested_area": get_suggested_area(name),
        }

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        return self.coordinator.get_light_state(self._counter)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        _LOGGER.debug("Turning on %s (counter=%02X)", self._attr_name, self._counter)
        success = await self.coordinator.async_turn_light_on(self._counter)
        if success:
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on %s", self._attr_name)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        _LOGGER.debug("Turning off %s (counter=%02X)", self._attr_name, self._counter)
        success = await self.coordinator.async_turn_light_off(self._counter)
        if success:
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn off %s", self._attr_name)
