"""Data coordinator for Lippert OneControl."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    SCAN_INTERVAL,
    KNOWN_LIGHTS,
    KNOWN_TANKS,
    GENERATOR_COUNTER,
)
from .onecontrol import OneControlClient

_LOGGER = logging.getLogger(__name__)


@dataclass
class OneControlData:
    """Data class for OneControl state."""

    lights: dict[int, bool]  # counter -> on/off state
    tanks: dict[int, int]  # counter -> level percentage
    battery_voltage: float | None
    generator_hours: float | None


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

        # Initialize known devices
        self._light_counters = list(KNOWN_LIGHTS.keys())
        self._tank_counters = list(KNOWN_TANKS.keys())

    async def _async_update_data(self) -> OneControlData:
        """Fetch data from OneControl."""
        try:
            # Read tank levels
            tanks = await self._client.read_tank_levels()

            # Read battery voltage
            voltage = await self._client.read_battery_voltage()

            # Read generator hours
            hours = await self._client.read_generator_hours()

            # For lights, we don't poll state - we track it locally
            # (OneControl doesn't provide reliable state feedback)
            lights = getattr(self, "_light_states", {})

            return OneControlData(
                lights=lights,
                tanks=tanks,
                battery_voltage=voltage,
                generator_hours=hours,
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
                # Update local state tracking
                if not hasattr(self, "_light_states"):
                    self._light_states = {}
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
                # Update local state tracking
                if not hasattr(self, "_light_states"):
                    self._light_states = {}
                self._light_states[counter] = False
            return result
        except Exception as err:
            _LOGGER.error("Failed to turn off light %02X: %s", counter, err)
            return False

    def get_light_state(self, counter: int) -> bool | None:
        """Get the tracked state of a light."""
        if not hasattr(self, "_light_states"):
            return None
        return self._light_states.get(counter)

    @property
    def available_lights(self) -> dict[int, dict[str, Any]]:
        """Return available lights."""
        return KNOWN_LIGHTS

    @property
    def available_tanks(self) -> dict[int, dict[str, Any]]:
        """Return available tanks."""
        return KNOWN_TANKS
