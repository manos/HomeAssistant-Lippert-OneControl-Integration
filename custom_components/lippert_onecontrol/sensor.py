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

from .const import DOMAIN, KNOWN_TANKS
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

    # Tank sensors
    for counter, info in KNOWN_TANKS.items():
        entities.append(
            OneControlTankSensor(
                coordinator=coordinator,
                counter=counter,
                name=info["name"],
                func_id=info.get("func_id"),
            )
        )

    # Battery voltage sensor
    entities.append(OneControlBatteryVoltageSensor(coordinator))

    # Generator hours sensor
    entities.append(OneControlGeneratorHoursSensor(coordinator))

    # Generator state sensor
    entities.append(OneControlGeneratorStateSensor(coordinator))

    async_add_entities(entities)


class OneControlTankSensor(CoordinatorEntity[OneControlCoordinator], SensorEntity):
    """Representation of a Lippert OneControl tank sensor."""

    # Note: No device_class - tanks are not a standard HA device class
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = True

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
        self._attr_name = name
        self._func_id = func_id

        # Unique ID based on counter
        self._attr_unique_id = f"lippert_onecontrol_tank_{counter:02x}"

        # Device info for grouping in HA
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "onecontrol_controller")},
            "name": "Lippert OneControl",
            "manufacturer": "Lippert",
            "model": "OneControl",
        }

        # Custom icon based on tank type
        if "fresh" in name.lower():
            self._attr_icon = "mdi:water"
        elif "grey" in name.lower():
            self._attr_icon = "mdi:water-opacity"
        elif "black" in name.lower():
            self._attr_icon = "mdi:water-off"
        elif "lp" in name.lower():
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
    _attr_has_entity_name = True
    _attr_name = "Battery Voltage"
    _attr_icon = "mdi:car-battery"

    def __init__(self, coordinator: OneControlCoordinator) -> None:
        """Initialize the battery voltage sensor."""
        super().__init__(coordinator)

        self._attr_unique_id = "lippert_onecontrol_battery_voltage"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, "onecontrol_controller")},
            "name": "Lippert OneControl",
            "manufacturer": "Lippert",
            "model": "OneControl",
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
    _attr_has_entity_name = True
    _attr_name = "Generator Hours"
    _attr_icon = "mdi:engine"

    def __init__(self, coordinator: OneControlCoordinator) -> None:
        """Initialize the generator hours sensor."""
        super().__init__(coordinator)

        self._attr_unique_id = "lippert_onecontrol_generator_hours"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, "onecontrol_controller")},
            "name": "Lippert OneControl",
            "manufacturer": "Lippert",
            "model": "OneControl",
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
    _attr_has_entity_name = True
    _attr_name = "Generator State"
    _attr_icon = "mdi:engine"
    _attr_options = ["Off", "Priming", "Starting", "Running", "Stopping", "Unknown"]

    def __init__(self, coordinator: OneControlCoordinator) -> None:
        """Initialize the generator state sensor."""
        super().__init__(coordinator)

        self._attr_unique_id = "lippert_onecontrol_generator_state"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, "onecontrol_controller")},
            "name": "Lippert OneControl",
            "manufacturer": "Lippert",
            "model": "OneControl",
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
