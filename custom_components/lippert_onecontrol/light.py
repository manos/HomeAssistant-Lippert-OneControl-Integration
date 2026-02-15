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


def get_light_icon(name: str) -> str:
    """Get appropriate icon based on light name."""
    name_lower = name.lower()
    if "ceiling" in name_lower:
        return "mdi:ceiling-light"
    elif "porch" in name_lower:
        return "mdi:coach-lamp"
    elif "awning" in name_lower:
        return "mdi:awning-outline"
    elif "scare" in name_lower:
        return "mdi:alarm-light"
    elif "outdoor" in name_lower or "outside" in name_lower:
        return "mdi:outdoor-lamp"
    elif "sconce" in name_lower:
        return "mdi:wall-sconce"
    elif "cabinet" in name_lower:
        return "mdi:light-recessed"
    else:
        return "mdi:lightbulb"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lippert OneControl lights."""
    coordinator: OneControlCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Config is now keyed by func_id string: {"57": {"name": "Bedroom Light"}}
    discovered_lights = entry.data.get(CONF_DISCOVERED_LIGHTS, {})
    
    func_ids = []
    entities = []
    for fid_str, info in discovered_lights.items():
        func_id = int(fid_str)
        func_ids.append(func_id)
        entities.append(
            OneControlLight(
                coordinator=coordinator,
                func_id=func_id,
                name=info["name"],
            )
        )

    # Initialize all light states to False (off) - prevents "Unknown" state
    coordinator.init_light_states(func_ids)

    async_add_entities(entities)


class OneControlLight(CoordinatorEntity[OneControlCoordinator], LightEntity):
    """Representation of a Lippert OneControl light."""

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: OneControlCoordinator,
        func_id: int,
        name: str,
    ) -> None:
        """Initialize the light."""
        super().__init__(coordinator)
        self._func_id = func_id
        
        self._attr_name = name
        self._attr_icon = get_light_icon(name)
        
        # Unique ID based on func_id (stable across reboots)
        self._attr_unique_id = f"lippert_onecontrol_light_fid{func_id}"
        
        # Each light gets its own device
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"light_fid{func_id}")},
            "name": name,
            "manufacturer": "Lippert",
            "model": "OneControl Light",
            "via_device": (DOMAIN, "onecontrol_controller"),
            "suggested_area": get_suggested_area(name),
        }

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        return self.coordinator.get_light_state(self._func_id)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        _LOGGER.debug("Turning on %s (func_id=%d)", self._attr_name, self._func_id)
        success = await self.coordinator.async_turn_light_on(self._func_id)
        if success:
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on %s", self._attr_name)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        _LOGGER.debug("Turning off %s (func_id=%d)", self._attr_name, self._func_id)
        success = await self.coordinator.async_turn_light_off(self._func_id)
        if success:
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn off %s", self._attr_name)
