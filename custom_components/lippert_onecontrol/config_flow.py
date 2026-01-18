"""Config flow for Lippert OneControl integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT

from .const import (
    DOMAIN,
    DEFAULT_HOST,
    DEFAULT_PORT,
    CONF_DISCOVERED_LIGHTS,
    CONF_DISCOVERED_TANKS,
)
from .onecontrol import OneControlClient

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
    }
)


async def validate_connection(host: str, port: int) -> bool:
    """Test if we can connect to the OneControl controller."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=5.0
        )
        writer.close()
        await writer.wait_closed()
        return True
    except (asyncio.TimeoutError, OSError, ConnectionRefusedError):
        return False


class OneControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Lippert OneControl."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._host: str = DEFAULT_HOST
        self._port: int = DEFAULT_PORT
        self._discovered_lights: dict = {}
        self._discovered_tanks: dict = {}
        self._has_generator: bool = False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step - get connection details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._host = user_input[CONF_HOST]
            self._port = user_input.get(CONF_PORT, DEFAULT_PORT)

            # Check if already configured
            await self.async_set_unique_id(f"lippert_onecontrol_{self._host}")
            self._abort_if_unique_id_configured()

            # Test connection
            if await validate_connection(self._host, self._port):
                # Connection successful, run discovery
                return await self.async_step_discover()
            else:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "default_host": DEFAULT_HOST,
            },
        )

    async def async_step_discover(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Discover devices on the controller."""
        _LOGGER.info("Running device discovery on %s:%d", self._host, self._port)
        
        client = OneControlClient(self._host, self._port)
        
        try:
            discovered = await client.discover_devices(duration=5.0)
            self._discovered_lights = discovered.get("lights", {})
            self._discovered_tanks = discovered.get("tanks", {})
            self._has_generator = discovered.get("has_generator", False)
            
            _LOGGER.info(
                "Discovery found: %d lights, %d tanks, generator=%s",
                len(self._discovered_lights),
                len(self._discovered_tanks),
                self._has_generator,
            )
        except Exception as err:
            _LOGGER.error("Discovery failed: %s", err)
            # Continue with empty discovery - user can still add manually

        # Show discovery results and create entry
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the discovered devices and create entry."""
        if user_input is not None:
            # Create entry with discovered devices
            return self.async_create_entry(
                title=f"OneControl ({self._host})",
                data={
                    CONF_HOST: self._host,
                    CONF_PORT: self._port,
                    CONF_DISCOVERED_LIGHTS: self._discovered_lights,
                    CONF_DISCOVERED_TANKS: self._discovered_tanks,
                    "has_generator": self._has_generator,
                },
            )

        # Build description of what was found
        light_names = [info["name"] for info in self._discovered_lights.values()]
        tank_names = [info["name"] for info in self._discovered_tanks.values()]
        
        description = []
        if light_names:
            description.append(f"**Lights:** {', '.join(sorted(light_names))}")
        if tank_names:
            description.append(f"**Tanks:** {', '.join(sorted(tank_names))}")
        if self._has_generator:
            description.append("**Generator:** Yes")
        
        if not description:
            description.append("No devices discovered. Check controller connection.")

        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "discovered_devices": "\n".join(description),
                "light_count": str(len(self._discovered_lights)),
                "tank_count": str(len(self._discovered_tanks)),
            },
        )
