"""Switch platform for Lippert OneControl."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_DISCOVERED_GENERATORS,
    CONF_DISCOVERED_WATER_HEATERS,
    CONF_DISCOVERED_WATER_PUMPS,
    DOMAIN,
    FUNCTION_NAMES,
    get_suggested_area,
)
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

    # Generator switch - only if generators were discovered
    discovered_generators = entry.data.get(CONF_DISCOVERED_GENERATORS, {})
    if discovered_generators:
        coordinator.init_generator()
        entities.append(OneControlGeneratorSwitch(coordinator))
        _LOGGER.debug("Adding generator switch")

    # Water heater switches -- config keyed by func_id string
    water_heaters = entry.data.get(CONF_DISCOVERED_WATER_HEATERS, {})
    wh_func_ids = []
    for fid_str, info in water_heaters.items():
        func_id = int(fid_str)
        wh_func_ids.append(func_id)
        name = info.get("name", f"Water Heater {fid_str}")
        entities.append(OneControlWaterHeaterSwitch(coordinator, func_id, name))
    
    if wh_func_ids:
        coordinator.init_water_heater_states(wh_func_ids)

    # Water pump switches -- config keyed by func_id string
    water_pumps = entry.data.get(CONF_DISCOVERED_WATER_PUMPS, {})
    wp_func_ids = []
    for fid_str, info in water_pumps.items():
        func_id = int(fid_str)
        wp_func_ids.append(func_id)
        name = info.get("name", f"Water Pump {fid_str}")
        entities.append(OneControlWaterPumpSwitch(coordinator, func_id, name))
    
    if wp_func_ids:
        coordinator.init_water_pump_states(wp_func_ids)

    async_add_entities(entities)


class OneControlGeneratorSwitch(CoordinatorEntity[OneControlCoordinator], SwitchEntity):
    """Representation of Lippert OneControl generator switch."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_has_entity_name = True
    _attr_name = "Power"
    _attr_icon = "mdi:engine"

    def __init__(self, coordinator: OneControlCoordinator) -> None:
        """Initialize the generator switch."""
        super().__init__(coordinator)

        self._attr_unique_id = "lippert_onecontrol_generator_switch"

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
        return state in (1, 2, 3)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the generator."""
        _LOGGER.debug("Turning on generator")
        success = await self.coordinator.async_generator_on()
        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to turn on generator")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the generator."""
        _LOGGER.debug("Turning off generator")
        success = await self.coordinator.async_generator_off()
        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to turn off generator")


class OneControlWaterHeaterSwitch(CoordinatorEntity[OneControlCoordinator], SwitchEntity):
    """Representation of Lippert OneControl water heater switch."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: OneControlCoordinator,
        func_id: int,
        name: str,
    ) -> None:
        """Initialize the water heater switch."""
        super().__init__(coordinator)

        self._func_id = func_id
        self._attr_name = name
        self._attr_unique_id = f"lippert_onecontrol_water_heater_fid{func_id}"
        
        # Icon by func_id
        if func_id == 3:  # Gas water heater
            self._attr_icon = "mdi:water-boiler"
        else:  # Electric water heater (func_id 4)
            self._attr_icon = "mdi:water-boiler-alert"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"water_heater_fid{func_id}")},
            "name": name,
            "manufacturer": "Lippert",
            "model": FUNCTION_NAMES.get(func_id, f"Water Heater (func_id {func_id})"),
            "via_device": (DOMAIN, "onecontrol_controller"),
            "suggested_area": get_suggested_area(name) or "Utility",
        }

    @property
    def is_on(self) -> bool | None:
        """Return True if water heater is on."""
        return self.coordinator.get_water_heater_state(self._func_id)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the water heater."""
        _LOGGER.debug("Turning on water heater func_id=%d (%s)", self._func_id, self._attr_name)
        success = await self.coordinator.async_turn_water_heater_on(self._func_id)
        if success:
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on water heater func_id=%d", self._func_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the water heater."""
        _LOGGER.debug("Turning off water heater func_id=%d (%s)", self._func_id, self._attr_name)
        success = await self.coordinator.async_turn_water_heater_off(self._func_id)
        if success:
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn off water heater func_id=%d", self._func_id)


class OneControlWaterPumpSwitch(CoordinatorEntity[OneControlCoordinator], SwitchEntity):
    """Representation of Lippert OneControl water pump switch."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_has_entity_name = False
    _attr_icon = "mdi:water-pump"

    def __init__(
        self,
        coordinator: OneControlCoordinator,
        func_id: int,
        name: str,
    ) -> None:
        """Initialize the water pump switch."""
        super().__init__(coordinator)

        self._func_id = func_id
        self._attr_name = name
        self._attr_unique_id = f"lippert_onecontrol_water_pump_fid{func_id}"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"water_pump_fid{func_id}")},
            "name": name,
            "manufacturer": "Lippert",
            "model": FUNCTION_NAMES.get(func_id, f"Water Pump (func_id {func_id})"),
            "via_device": (DOMAIN, "onecontrol_controller"),
            "suggested_area": get_suggested_area(name) or "Utility",
        }

    @property
    def is_on(self) -> bool | None:
        """Return True if water pump is on."""
        return self.coordinator.get_water_pump_state(self._func_id)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the water pump."""
        _LOGGER.debug("Turning on water pump func_id=%d (%s)", self._func_id, self._attr_name)
        success = await self.coordinator.async_turn_water_pump_on(self._func_id)
        if success:
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on water pump func_id=%d", self._func_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the water pump."""
        _LOGGER.debug("Turning off water pump func_id=%d (%s)", self._func_id, self._attr_name)
        success = await self.coordinator.async_turn_water_pump_off(self._func_id)
        if success:
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn off water pump func_id=%d", self._func_id)
