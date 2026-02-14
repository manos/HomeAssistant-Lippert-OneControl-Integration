"""Data coordinator for Lippert OneControl."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, SCAN_INTERVAL, DEFAULT_GENERATOR_COUNTER
from .onecontrol import OneControlClient

_LOGGER = logging.getLogger(__name__)


@dataclass
class OneControlData:
    """Data class for OneControl state."""

    lights: dict[int, bool]  # counter -> on/off state
    tanks: dict[int, int]  # counter -> level percentage
    water_heaters: dict[int, bool]  # counter -> on/off state
    water_pumps: dict[int, bool]  # counter -> on/off state
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
        # Initialize water pump states - will be populated by init_water_pump_states()
        self._water_pump_states: dict[int, bool] = {}
        # Generator counters - will be populated by init_generator_counters()
        self._generator_counters: list[int] = []

    def init_light_states(self, counters: list[int]) -> None:
        """Register light counters for state tracking.
        
        Initial state is False (off) until first broadcast is received.
        Actual state is updated from RelayBasicLatchingStatus2 broadcasts during polling.
        """
        for counter in counters:
            if counter not in self._light_states:
                self._light_states[counter] = False

    def init_water_heater_states(self, counters: list[int]) -> None:
        """Register water heater counters for state tracking.
        
        Initial state is False (off) until first broadcast is received.
        Actual state is updated from RelayBasicLatchingStatus2 broadcasts during polling.
        """
        for counter in counters:
            if counter not in self._water_heater_states:
                self._water_heater_states[counter] = False

    def init_water_pump_states(self, counters: list[int]) -> None:
        """Register water pump counters for state tracking.
        
        Initial state is False (off) until first broadcast is received.
        Actual state is updated from RelayBasicLatchingStatus2 broadcasts during polling.
        """
        for counter in counters:
            if counter not in self._water_pump_states:
                self._water_pump_states[counter] = False

    def init_generator_counters(self, counters: list[int]) -> None:
        """Register generator counters discovered from 08 02 broadcasts.
        
        These counters are used for control commands.
        For status reading, we use a flexible hybrid approach that accepts
        generator status from any known counter.
        """
        self._generator_counters = counters
        _LOGGER.debug("Initialized generator counters: %s", [f"0x{c:02x}" for c in counters])

    async def _async_update_data(self) -> OneControlData:
        """Fetch data from OneControl.
        
        Uses a single connection to read ALL sensor data efficiently.
        Previous approach opened 4 separate connections (12+ seconds).
        Now takes ~3 seconds total.
        """
        try:
            # Read ALL sensors in ONE connection (much faster!)
            # Pass discovered generator counters to help identify status frames
            sensor_data = await self._client.read_all_sensors(
                duration=3.0,
                generator_counters=self._generator_counters if self._generator_counters else None
            )

            # Update device states from RelayBasicLatchingStatus2 (0x06 0x03) broadcasts
            # Both lights and water heaters use latching relays that broadcast their state
            relay_states = sensor_data.get("relay_states", {})
            
            # Update light states from broadcasts
            for counter in self._light_states:
                if counter in relay_states:
                    self._light_states[counter] = relay_states[counter]
            
            # Update water heater states from broadcasts
            for counter in self._water_heater_states:
                if counter in relay_states:
                    self._water_heater_states[counter] = relay_states[counter]
            
            # Update water pump states from broadcasts
            for counter in self._water_pump_states:
                if counter in relay_states:
                    self._water_pump_states[counter] = relay_states[counter]
            
            lights = self._light_states.copy()
            water_heaters = self._water_heater_states.copy()
            water_pumps = self._water_pump_states.copy()

            return OneControlData(
                lights=lights,
                tanks=sensor_data.get("tanks", {}),
                water_heaters=water_heaters,
                water_pumps=water_pumps,
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
        """Turn on the generator.
        
        Tries discovered counters first, then falls back to default.
        The control counter may differ from the discovery counter, so we
        try ALL known counters until one succeeds.
        """
        counters_to_try = list(self._generator_counters) if self._generator_counters else []
        # Always include the default as a fallback
        if DEFAULT_GENERATOR_COUNTER not in counters_to_try:
            counters_to_try.append(DEFAULT_GENERATOR_COUNTER)
        
        for counter in counters_to_try:
            try:
                _LOGGER.debug("Trying generator ON with counter 0x%02x", counter)
                result = await self._client.generator_on(counter)
                if result:
                    return True
            except Exception as err:
                _LOGGER.debug("Generator ON failed with counter 0x%02x: %s", counter, err)
        
        _LOGGER.error("Failed to turn on generator (tried counters: %s)", 
                      [f"0x{c:02x}" for c in counters_to_try])
        return False

    async def async_generator_off(self) -> bool:
        """Turn off the generator.
        
        Tries discovered counters first, then falls back to default.
        The control counter may differ from the discovery counter, so we
        try ALL known counters until one succeeds.
        """
        counters_to_try = list(self._generator_counters) if self._generator_counters else []
        # Always include the default as a fallback
        if DEFAULT_GENERATOR_COUNTER not in counters_to_try:
            counters_to_try.append(DEFAULT_GENERATOR_COUNTER)
        
        for counter in counters_to_try:
            try:
                _LOGGER.debug("Trying generator OFF with counter 0x%02x", counter)
                result = await self._client.generator_off(counter)
                if result:
                    return True
            except Exception as err:
                _LOGGER.debug("Generator OFF failed with counter 0x%02x: %s", counter, err)
        
        _LOGGER.error("Failed to turn off generator (tried counters: %s)", 
                      [f"0x{c:02x}" for c in counters_to_try])
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

    async def async_turn_water_pump_on(self, counter: int) -> bool:
        """Turn on a water pump."""
        try:
            result = await self._client.water_pump_on(counter)
            if result:
                self._water_pump_states[counter] = True
            return result
        except Exception as err:
            _LOGGER.error("Failed to turn on water pump %02X: %s", counter, err)
            return False

    async def async_turn_water_pump_off(self, counter: int) -> bool:
        """Turn off a water pump."""
        try:
            result = await self._client.water_pump_off(counter)
            if result:
                self._water_pump_states[counter] = False
            return result
        except Exception as err:
            _LOGGER.error("Failed to turn off water pump %02X: %s", counter, err)
            return False

    def get_water_pump_state(self, counter: int) -> bool | None:
        """Get the tracked state of a water pump."""
        return self._water_pump_states.get(counter)

    # ========== LEVELER CONTROL ==========

    async def async_leveler_auto_level(self) -> bool:
        """Start auto-leveling sequence."""
        try:
            return await self._client.leveler_auto_level()
        except Exception as err:
            _LOGGER.error("Failed to start auto-level: %s", err)
            return False

    async def async_leveler_retract(self) -> bool:
        """Retract all leveler jacks."""
        try:
            return await self._client.leveler_retract()
        except Exception as err:
            _LOGGER.error("Failed to retract leveler: %s", err)
            return False

    async def async_leveler_cancel(self) -> bool:
        """Cancel current leveler operation."""
        try:
            return await self._client.leveler_cancel()
        except Exception as err:
            _LOGGER.error("Failed to cancel leveler: %s", err)
            return False
