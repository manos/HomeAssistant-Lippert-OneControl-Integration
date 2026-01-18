"""Sensor platform for Lippert OneControl."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfElectricPotential, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_DISCOVERED_TANKS, get_suggested_area
from .coordinator import OneControlCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lippert OneControl sensors."""
    coordinator: OneControlCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []

    # Tank sensors from discovered devices
    discovered_tanks = entry.data.get(CONF_DISCOVERED_TANKS, {})
    for counter_str, info in discovered_tanks.items():
        counter = int(counter_str, 16) if isinstance(counter_str, str) else counter_str
        entities.append(
            OneControlTankSensor(
                coordinator=coordinator,
                counter=counter,
                name=info["name"],
                func_id=info.get("func_id"),
            )
        )

    # Battery voltage sensor (controller-level)
    entities.append(OneControlBatteryVoltageSensor(coordinator))

    # Generator sensors (grouped under Generator device)
    entities.append(OneControlGeneratorHoursSensor(coordinator))
    entities.append(OneControlGeneratorStateSensor(coordinator))

    async_add_entities(entities)


class OneControlTankSensor(CoordinatorEntity[OneControlCoordinator], SensorEntity):
    """Representation of a Lippert OneControl tank sensor."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = False  # Use full name directly

    def __init__(
        self,
        coordinator: OneControlCoordinator,
        counter: int,
        name: str,
        func_id: int | None = None,
    ) -> None:
        """Initialize the tank sensor."""
        super().__init__(coordinator)
        self._counter = counter
        self._func_id = func_id

        # Use the tank name directly (e.g., "Fresh Tank")
        self._attr_name = name

        # Unique ID based on counter
        self._attr_unique_id = f"lippert_onecontrol_tank_{counter:02x}"

        # Each tank gets its own device
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"tank_{counter:02x}")},
            "name": name,
            "manufacturer": "Lippert",
            "model": "OneControl Tank Sensor",
            "via_device": (DOMAIN, "onecontrol_controller"),
            "suggested_area": get_suggested_area(name),
        }

        # Custom icon based on tank type
        if "fresh" in name.lower():
            self._attr_icon = "mdi:water"
        elif "grey" in name.lower() or "gray" in name.lower():
            self._attr_icon = "mdi:water-opacity"
        elif "black" in name.lower():
            self._attr_icon = "mdi:water-off"
        elif "lp" in name.lower() or "propane" in name.lower():
            self._attr_icon = "mdi:propane-tank"

    @property
    def native_value(self) -> int | None:
        """Return the tank level percentage."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.tanks.get(self._counter)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success


class OneControlBatteryVoltageSensor(CoordinatorEntity[OneControlCoordinator], SensorEntity):
    """Representation of Lippert OneControl battery voltage sensor."""

    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = True  # Append to device name
    _attr_name = "Battery Voltage"
    _attr_icon = "mdi:car-battery"

    def __init__(self, coordinator: OneControlCoordinator) -> None:
        """Initialize the battery voltage sensor."""
        super().__init__(coordinator)

        self._attr_unique_id = "lippert_onecontrol_battery_voltage"

        # This stays under the main controller device
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "onecontrol_controller")},
            "name": "OneControl",
            "manufacturer": "Lippert",
            "model": "OneControl Controller",
            "suggested_area": "Utility",
        }

    @property
    def native_value(self) -> float | None:
        """Return the battery voltage."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.battery_voltage

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success


class OneControlGeneratorHoursSensor(CoordinatorEntity[OneControlCoordinator], SensorEntity):
    """Representation of Lippert OneControl generator hours sensor."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_has_entity_name = True  # Append to device name
    _attr_name = "Hours"
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator: OneControlCoordinator) -> None:
        """Initialize the generator hours sensor."""
        super().__init__(coordinator)

        self._attr_unique_id = "lippert_onecontrol_generator_hours"

        # Generator gets its own device
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "generator")},
            "name": "Generator",
            "manufacturer": "Lippert",
            "model": "Generator Genie",
            "via_device": (DOMAIN, "onecontrol_controller"),
            "suggested_area": "Utility",
        }

    @property
    def native_value(self) -> float | None:
        """Return the generator hours."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.generator_hours

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success


class OneControlGeneratorStateSensor(CoordinatorEntity[OneControlCoordinator], SensorEntity):
    """Representation of Lippert OneControl generator state sensor."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_has_entity_name = True  # Append to device name
    _attr_name = "State"
    _attr_icon = "mdi:engine"
    _attr_options = ["Off", "Priming", "Starting", "Running", "Stopping", "Unknown"]

    def __init__(self, coordinator: OneControlCoordinator) -> None:
        """Initialize the generator state sensor."""
        super().__init__(coordinator)

        self._attr_unique_id = "lippert_onecontrol_generator_state"

        # Generator gets its own device (same as hours sensor)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "generator")},
            "name": "Generator",
            "manufacturer": "Lippert",
            "model": "Generator Genie",
            "via_device": (DOMAIN, "onecontrol_controller"),
            "suggested_area": "Utility",
        }

    @property
    def native_value(self) -> str | None:
        """Return the generator state as a string."""
        if self.coordinator.data is None:
            return None
        state = self.coordinator.data.generator_state
        if state is None:
            return None
        state_names = {
            0: "Off",
            1: "Priming",
            2: "Starting",
            3: "Running",
            4: "Stopping",
        }
        return state_names.get(state, "Unknown")

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success
