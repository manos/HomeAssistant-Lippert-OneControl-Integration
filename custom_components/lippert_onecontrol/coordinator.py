"""Data coordinator for Lippert OneControl."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, SCAN_INTERVAL
from .onecontrol import OneControlClient

_LOGGER = logging.getLogger(__name__)


@dataclass
class OneControlData:
    """Data class for OneControl state."""

    lights: dict[int, bool]  # counter -> on/off state
    tanks: dict[int, int]  # counter -> level percentage
    water_heaters: dict[int, bool]  # counter -> on/off state
    battery_voltage: float | None
    generator_hours: float | None
    generator_state: int | None  # 0=Off, 1=Priming, 2=Starting, 3=Running, 4=Stopping


class OneControlCoordinator(DataUpdateCoordinator[OneControlData]):
    """Coordinator for Lippert OneControl."""

    def __init__(self, hass: HomeAssistant, host: str, port: int) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.host = host
        self.port = port
        self._client = OneControlClient(host, port)
        # Initialize light states - will be populated by init_light_states()
        self._light_states: dict[int, bool] = {}
        # Initialize water heater states - will be populated by init_water_heater_states()
        self._water_heater_states: dict[int, bool] = {}

    def init_light_states(self, counters: list[int]) -> None:
        """Initialize light states to False (off) for all discovered lights.
        
        This prevents lights from showing as 'Unknown' before first interaction.
        """
        for counter in counters:
            if counter not in self._light_states:
                self._light_states[counter] = False  # Assume off initially

    def init_water_heater_states(self, counters: list[int]) -> None:
        """Initialize water heater states to False (off) for all discovered water heaters.
        
        This prevents water heaters from showing as 'Unknown' before first interaction.
        """
        for counter in counters:
            if counter not in self._water_heater_states:
                self._water_heater_states[counter] = False  # Assume off initially

    async def _async_update_data(self) -> OneControlData:
        """Fetch data from OneControl.
        
        Uses a single connection to read ALL sensor data efficiently.
        Previous approach opened 4 separate connections (12+ seconds).
        Now takes ~3 seconds total.
        """
        try:
            # Read ALL sensors in ONE connection (much faster!)
            sensor_data = await self._client.read_all_sensors(duration=3.0)

            # For lights, we track state locally (no reliable broadcast)
            lights = self._light_states.copy()
            
            # For water heaters, update from relay broadcasts if available
            relay_states = sensor_data.get("relay_states", {})
            for counter in self._water_heater_states:
                if counter in relay_states:
                    self._water_heater_states[counter] = relay_states[counter]
            
            water_heaters = self._water_heater_states.copy()

            return OneControlData(
                lights=lights,
                tanks=sensor_data.get("tanks", {}),
                water_heaters=water_heaters,
                battery_voltage=sensor_data.get("battery_voltage"),
                generator_hours=sensor_data.get("generator_hours"),
                generator_state=sensor_data.get("generator_state"),
            )

        except asyncio.TimeoutError as err:
            raise UpdateFailed(f"Timeout communicating with OneControl: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Error communicating with OneControl: {err}") from err

    async def async_turn_light_on(self, counter: int) -> bool:
        """Turn on a light."""
        try:
            result = await self._client.light_on(counter)
            if result:
                self._light_states[counter] = True
            return result
        except Exception as err:
            _LOGGER.error("Failed to turn on light %02X: %s", counter, err)
            return False

    async def async_turn_light_off(self, counter: int) -> bool:
        """Turn off a light."""
        try:
            result = await self._client.light_off(counter)
            if result:
                self._light_states[counter] = False
            return result
        except Exception as err:
            _LOGGER.error("Failed to turn off light %02X: %s", counter, err)
            return False

    def get_light_state(self, counter: int) -> bool | None:
        """Get the tracked state of a light."""
        return self._light_states.get(counter)

    async def async_generator_on(self) -> bool:
        """Turn on the generator."""
        try:
            return await self._client.generator_on()
        except Exception as err:
            _LOGGER.error("Failed to turn on generator: %s", err)
            return False

    async def async_generator_off(self) -> bool:
        """Turn off the generator."""
        try:
            return await self._client.generator_off()
        except Exception as err:
            _LOGGER.error("Failed to turn off generator: %s", err)
            return False

    def get_generator_state(self) -> int | None:
        """Get the current generator state."""
        if self.data is None:
            return None
        return self.data.generator_state

    async def async_turn_water_heater_on(self, counter: int) -> bool:
        """Turn on a water heater."""
        try:
            result = await self._client.water_heater_on(counter)
            if result:
                self._water_heater_states[counter] = True
            return result
        except Exception as err:
            _LOGGER.error("Failed to turn on water heater %02X: %s", counter, err)
            return False

    async def async_turn_water_heater_off(self, counter: int) -> bool:
        """Turn off a water heater."""
        try:
            result = await self._client.water_heater_off(counter)
            if result:
                self._water_heater_states[counter] = False
            return result
        except Exception as err:
            _LOGGER.error("Failed to turn off water heater %02X: %s", counter, err)
            return False

    def get_water_heater_state(self, counter: int) -> bool | None:
        """Get the tracked state of a water heater."""
        return self._water_heater_states.get(counter)
