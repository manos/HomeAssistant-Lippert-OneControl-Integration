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
    has_generator_legacy = entry.data.get("has_generator", False)  # Backward compat
    if discovered_generators or has_generator_legacy:
        entities.append(OneControlGeneratorSwitch(coordinator))
        _LOGGER.debug("Adding generator switch (discovered: %s, legacy: %s)", 
                     bool(discovered_generators), has_generator_legacy)

    # Water heater switches
    water_heaters = entry.data.get(CONF_DISCOVERED_WATER_HEATERS, {})
    water_heater_counters = []
    for counter_hex, info in water_heaters.items():
        counter = int(counter_hex, 16)
        water_heater_counters.append(counter)
        name = info.get("name", f"Water Heater {counter_hex}")
        func_id = info.get("func_id", 0)
        entities.append(OneControlWaterHeaterSwitch(coordinator, counter, name, func_id))
    
    # Initialize water heater states
    if water_heater_counters:
        coordinator.init_water_heater_states(water_heater_counters)

    # Water pump switches
    water_pumps = entry.data.get(CONF_DISCOVERED_WATER_PUMPS, {})
    water_pump_counters = []
    for counter_hex, info in water_pumps.items():
        counter = int(counter_hex, 16)
        water_pump_counters.append(counter)
        name = info.get("name", f"Water Pump {counter_hex}")
        func_id = info.get("func_id", 0)
        entities.append(OneControlWaterPumpSwitch(coordinator, counter, name, func_id))
    
    # Initialize water pump states
    if water_pump_counters:
        coordinator.init_water_pump_states(water_pump_counters)

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


class OneControlWaterHeaterSwitch(CoordinatorEntity[OneControlCoordinator], SwitchEntity):
    """Representation of Lippert OneControl water heater switch."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_has_entity_name = False  # Use full name directly

    def __init__(
        self,
        coordinator: OneControlCoordinator,
        counter: int,
        name: str,
        func_id: int,
    ) -> None:
        """Initialize the water heater switch."""
        super().__init__(coordinator)

        self._counter = counter
        self._func_id = func_id
        self._attr_name = name
        self._attr_unique_id = f"lippert_onecontrol_water_heater_{counter:02x}"
        
        # Set icon based on type
        if func_id == 3:  # Gas water heater
            self._attr_icon = "mdi:water-boiler"
        else:  # Electric water heater (func_id 4)
            self._attr_icon = "mdi:water-boiler-alert"

        # Each water heater gets its own device
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"water_heater_{counter:02x}")},
            "name": name,
            "manufacturer": "Lippert",
            "model": FUNCTION_NAMES.get(func_id, f"Water Heater (func_id {func_id})"),
            "via_device": (DOMAIN, "onecontrol_controller"),
            "suggested_area": get_suggested_area(name) or "Utility",
        }

    @property
    def is_on(self) -> bool | None:
        """Return True if water heater is on."""
        return self.coordinator.get_water_heater_state(self._counter)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the water heater."""
        _LOGGER.info("Turning on water heater %02X (%s)", self._counter, self._attr_name)
        success = await self.coordinator.async_turn_water_heater_on(self._counter)
        if success:
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on water heater %02X", self._counter)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the water heater."""
        _LOGGER.info("Turning off water heater %02X (%s)", self._counter, self._attr_name)
        success = await self.coordinator.async_turn_water_heater_off(self._counter)
        if success:
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn off water heater %02X", self._counter)


class OneControlWaterPumpSwitch(CoordinatorEntity[OneControlCoordinator], SwitchEntity):
    """Representation of Lippert OneControl water pump switch."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_has_entity_name = False  # Use full name directly
    _attr_icon = "mdi:water-pump"

    def __init__(
        self,
        coordinator: OneControlCoordinator,
        counter: int,
        name: str,
        func_id: int,
    ) -> None:
        """Initialize the water pump switch."""
        super().__init__(coordinator)

        self._counter = counter
        self._func_id = func_id
        self._attr_name = name
        self._attr_unique_id = f"lippert_onecontrol_water_pump_{counter:02x}"

        # Water pump gets its own device
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"water_pump_{counter:02x}")},
            "name": name,
            "manufacturer": "Lippert",
            "model": FUNCTION_NAMES.get(func_id, f"Water Pump (func_id {func_id})"),
            "via_device": (DOMAIN, "onecontrol_controller"),
            "suggested_area": get_suggested_area(name) or "Utility",
        }

    @property
    def is_on(self) -> bool | None:
        """Return True if water pump is on."""
        return self.coordinator.get_water_pump_state(self._counter)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the water pump."""
        _LOGGER.info("Turning on water pump %02X (%s)", self._counter, self._attr_name)
        success = await self.coordinator.async_turn_water_pump_on(self._counter)
        if success:
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on water pump %02X", self._counter)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the water pump."""
        _LOGGER.info("Turning off water pump %02X (%s)", self._counter, self._attr_name)
        success = await self.coordinator.async_turn_water_pump_off(self._counter)
        if success:
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn off water pump %02X", self._counter)
