"""Data coordinator for Lippert OneControl.

Maintains a live func_id <-> counter mapping that refreshes every poll cycle.
All device state and control is keyed by func_id (stable) with counters
resolved at runtime from 0x08 0x02 registration broadcasts.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, SCAN_INTERVAL
from .onecontrol import OneControlClient

_LOGGER = logging.getLogger(__name__)

# Generator func_id (from decompiled app)
GENERATOR_FUNC_ID = 95


@dataclass
class OneControlData:
    """Data class for OneControl state.  All keyed by func_id (stable)."""

    lights: dict[int, bool] = field(default_factory=dict)       # func_id -> on/off
    tanks: dict[int, int] = field(default_factory=dict)         # func_id -> level %
    water_heaters: dict[int, bool] = field(default_factory=dict) # func_id -> on/off
    water_pumps: dict[int, bool] = field(default_factory=dict)   # func_id -> on/off
    battery_voltage: float | None = None
    generator_hours: float | None = None
    generator_state: int | None = None  # 0=Off, 1=Priming, 2=Starting, 3=Running, 4=Stopping


class OneControlCoordinator(DataUpdateCoordinator[OneControlData]):
    """Coordinator for Lippert OneControl.

    Core concept: func_id is the STABLE device identifier (from firmware).
    Counter is VOLATILE (can change on reboot).  Every poll cycle refreshes
    the func_id -> counter map from live 0x08 0x02 registration broadcasts.
    """

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

        # Live mapping refreshed every poll cycle from 0x08 0x02 broadcasts
        self._func_id_to_counter: dict[int, int] = {}
        self._counter_to_func_id: dict[int, int] = {}

        # Device states keyed by func_id (stable)
        self._light_func_ids: set[int] = set()
        self._light_states: dict[int, bool] = {}
        self._water_heater_func_ids: set[int] = set()
        self._water_heater_states: dict[int, bool] = {}
        self._water_pump_func_ids: set[int] = set()
        self._water_pump_states: dict[int, bool] = {}
        self._has_generator: bool = False
        self._generator_control_counter: int | None = None

    # ---- Initialization (called from platform setup) ----

    def init_light_states(self, func_ids: list[int]) -> None:
        """Register light func_ids for state tracking."""
        for fid in func_ids:
            self._light_func_ids.add(fid)
            if fid not in self._light_states:
                self._light_states[fid] = False

    def init_water_heater_states(self, func_ids: list[int]) -> None:
        """Register water heater func_ids for state tracking."""
        for fid in func_ids:
            self._water_heater_func_ids.add(fid)
            if fid not in self._water_heater_states:
                self._water_heater_states[fid] = False

    def init_water_pump_states(self, func_ids: list[int]) -> None:
        """Register water pump func_ids for state tracking."""
        for fid in func_ids:
            self._water_pump_func_ids.add(fid)
            if fid not in self._water_pump_states:
                self._water_pump_states[fid] = False

    def init_generator(self) -> None:
        """Register that a generator is present."""
        self._has_generator = True

    # ---- Counter resolution ----

    def get_counter(self, func_id: int) -> int | None:
        """Resolve a func_id to its current counter from the live map."""
        return self._func_id_to_counter.get(func_id)

    # ---- Poll cycle ----

    async def _async_update_data(self) -> OneControlData:
        """Fetch data from OneControl.

        Single connection reads all sensor data AND registration broadcasts
        to refresh the func_id <-> counter map every cycle (~3s).
        """
        try:
            sensor_data = await self._client.read_all_sensors(duration=3.0)

            # Update live device map from registration broadcasts
            device_map: dict[int, int] = sensor_data.get("device_map", {})
            if device_map:
                self._func_id_to_counter = dict(device_map)
                self._counter_to_func_id = {v: k for k, v in device_map.items()}
                _LOGGER.debug(
                    "Live device map updated: %d devices",
                    len(self._func_id_to_counter),
                )

            # Generator has multiple sub-counters for the same func_id (hour meter
            # vs genie status).  The control counter is the one broadcasting state
            # + voltage on 05 03 frames, NOT the hour meter (0x80).
            gen_ctrl = sensor_data.get("generator_control_counter")
            if gen_ctrl is not None:
                self._generator_control_counter = gen_ctrl

            # Update relay-based device states using reverse map
            relay_states: dict[int, bool] = sensor_data.get("relay_states", {})
            for counter, is_on in relay_states.items():
                func_id = self._counter_to_func_id.get(counter)
                if func_id is None:
                    continue
                if func_id in self._light_func_ids:
                    self._light_states[func_id] = is_on
                elif func_id in self._water_heater_func_ids:
                    self._water_heater_states[func_id] = is_on
                elif func_id in self._water_pump_func_ids:
                    self._water_pump_states[func_id] = is_on

            # Map tank data from counter-keyed to func_id-keyed
            tanks_by_func_id: dict[int, int] = {}
            for counter, level in sensor_data.get("tanks", {}).items():
                func_id = self._counter_to_func_id.get(counter)
                if func_id is not None:
                    tanks_by_func_id[func_id] = level

            return OneControlData(
                lights=self._light_states.copy(),
                tanks=tanks_by_func_id,
                water_heaters=self._water_heater_states.copy(),
                water_pumps=self._water_pump_states.copy(),
                battery_voltage=sensor_data.get("battery_voltage"),
                generator_hours=sensor_data.get("generator_hours"),
                generator_state=sensor_data.get("generator_state"),
            )

        except asyncio.TimeoutError as err:
            raise UpdateFailed(f"Timeout communicating with OneControl: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Error communicating with OneControl: {err}") from err

    # ---- Light control (by func_id) ----

    async def async_turn_light_on(self, func_id: int) -> bool:
        """Turn on a light, resolving counter at call time."""
        counter = self.get_counter(func_id)
        if counter is None:
            _LOGGER.error("No counter mapped for light func_id %d", func_id)
            return False
        try:
            result = await self._client.light_on(counter)
            if result:
                self._light_states[func_id] = True
            return result
        except Exception as err:
            _LOGGER.error("Failed to turn on light func_id %d: %s", func_id, err)
            return False

    async def async_turn_light_off(self, func_id: int) -> bool:
        """Turn off a light, resolving counter at call time."""
        counter = self.get_counter(func_id)
        if counter is None:
            _LOGGER.error("No counter mapped for light func_id %d", func_id)
            return False
        try:
            result = await self._client.light_off(counter)
            if result:
                self._light_states[func_id] = False
            return result
        except Exception as err:
            _LOGGER.error("Failed to turn off light func_id %d: %s", func_id, err)
            return False

    def get_light_state(self, func_id: int) -> bool | None:
        """Get the tracked state of a light."""
        return self._light_states.get(func_id)

    # ---- Generator control ----

    async def async_generator_on(self) -> bool:
        """Turn on the generator using the dedicated control counter."""
        counter = self._generator_control_counter
        if counter is None:
            counter = self.get_counter(GENERATOR_FUNC_ID)
        if counter is None:
            _LOGGER.error("No counter for generator (func_id %d)", GENERATOR_FUNC_ID)
            return False
        _LOGGER.debug("Generator ON using counter 0x%02x", counter)
        try:
            return await self._client.generator_on(counter)
        except Exception as err:
            _LOGGER.error("Failed to turn on generator: %s", err)
            return False

    async def async_generator_off(self) -> bool:
        """Turn off the generator using the dedicated control counter."""
        counter = self._generator_control_counter
        if counter is None:
            counter = self.get_counter(GENERATOR_FUNC_ID)
        if counter is None:
            _LOGGER.error("No counter for generator (func_id %d)", GENERATOR_FUNC_ID)
            return False
        _LOGGER.debug("Generator OFF using counter 0x%02x", counter)
        try:
            return await self._client.generator_off(counter)
        except Exception as err:
            _LOGGER.error("Failed to turn off generator: %s", err)
            return False

    def get_generator_state(self) -> int | None:
        """Get the current generator state."""
        if self.data is None:
            return None
        return self.data.generator_state

    # ---- Water heater control (by func_id) ----

    async def async_turn_water_heater_on(self, func_id: int) -> bool:
        """Turn on a water heater, resolving counter at call time."""
        counter = self.get_counter(func_id)
        if counter is None:
            _LOGGER.error("No counter mapped for water heater func_id %d", func_id)
            return False
        try:
            result = await self._client.water_heater_on(counter)
            if result:
                self._water_heater_states[func_id] = True
            return result
        except Exception as err:
            _LOGGER.error("Failed to turn on water heater func_id %d: %s", func_id, err)
            return False

    async def async_turn_water_heater_off(self, func_id: int) -> bool:
        """Turn off a water heater, resolving counter at call time."""
        counter = self.get_counter(func_id)
        if counter is None:
            _LOGGER.error("No counter mapped for water heater func_id %d", func_id)
            return False
        try:
            result = await self._client.water_heater_off(counter)
            if result:
                self._water_heater_states[func_id] = False
            return result
        except Exception as err:
            _LOGGER.error("Failed to turn off water heater func_id %d: %s", func_id, err)
            return False

    def get_water_heater_state(self, func_id: int) -> bool | None:
        """Get the tracked state of a water heater."""
        return self._water_heater_states.get(func_id)

    # ---- Water pump control (by func_id) ----

    async def async_turn_water_pump_on(self, func_id: int) -> bool:
        """Turn on a water pump, resolving counter at call time."""
        counter = self.get_counter(func_id)
        if counter is None:
            _LOGGER.error("No counter mapped for water pump func_id %d", func_id)
            return False
        try:
            result = await self._client.water_pump_on(counter)
            if result:
                self._water_pump_states[func_id] = True
            return result
        except Exception as err:
            _LOGGER.error("Failed to turn on water pump func_id %d: %s", func_id, err)
            return False

    async def async_turn_water_pump_off(self, func_id: int) -> bool:
        """Turn off a water pump, resolving counter at call time."""
        counter = self.get_counter(func_id)
        if counter is None:
            _LOGGER.error("No counter mapped for water pump func_id %d", func_id)
            return False
        try:
            result = await self._client.water_pump_off(counter)
            if result:
                self._water_pump_states[func_id] = False
            return result
        except Exception as err:
            _LOGGER.error("Failed to turn off water pump func_id %d: %s", func_id, err)
            return False

    def get_water_pump_state(self, func_id: int) -> bool | None:
        """Get the tracked state of a water pump."""
        return self._water_pump_states.get(func_id)

    # ---- Leveler control (no counter needed - uses fixed leveler_id) ----

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
