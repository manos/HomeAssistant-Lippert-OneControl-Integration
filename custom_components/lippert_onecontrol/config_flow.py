"""Config flow for Lippert OneControl integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback

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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return OneControlOptionsFlowHandler(config_entry)

    async def async_step_integration_discovery(
        self, discovery_info: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle auto-discovery of OneControl controller."""
        self._host = discovery_info.get(CONF_HOST, DEFAULT_HOST)
        self._port = discovery_info.get(CONF_PORT, DEFAULT_PORT)

        # Check if already configured
        await self.async_set_unique_id(f"lippert_onecontrol_{self._host}")
        self._abort_if_unique_id_configured()

        # Set the title for the discovery notification
        self.context["title_placeholders"] = {"host": self._host}

        # Go directly to device discovery
        return await self.async_step_discover()

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


class OneControlOptionsFlowHandler(OptionsFlow):
    """Handle options flow for Lippert OneControl."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self._new_lights: dict = {}
        self._new_tanks: dict = {}
        self._has_new_generator: bool = False

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options - show menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["rediscover", "current_devices"],
        )

    async def async_step_current_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show current configured devices."""
        current_lights = self.config_entry.data.get(CONF_DISCOVERED_LIGHTS, {})
        current_tanks = self.config_entry.data.get(CONF_DISCOVERED_TANKS, {})
        has_generator = self.config_entry.data.get("has_generator", False)

        light_names = [info["name"] for info in current_lights.values()]
        tank_names = [info["name"] for info in current_tanks.values()]

        description = []
        description.append(f"**Lights ({len(light_names)}):** {', '.join(sorted(light_names)) or 'None'}")
        description.append(f"**Tanks ({len(tank_names)}):** {', '.join(sorted(tank_names)) or 'None'}")
        description.append(f"**Generator:** {'Yes' if has_generator else 'No'}")

        return self.async_show_form(
            step_id="current_devices",
            description_placeholders={
                "device_list": "\n".join(description),
            },
            last_step=True,
        )

    async def async_step_rediscover(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Run device rediscovery."""
        host = self.config_entry.data.get(CONF_HOST, DEFAULT_HOST)
        port = self.config_entry.data.get(CONF_PORT, DEFAULT_PORT)

        _LOGGER.info("Running rediscovery on %s:%d", host, port)

        # Get current devices
        current_lights = self.config_entry.data.get(CONF_DISCOVERED_LIGHTS, {})
        current_tanks = self.config_entry.data.get(CONF_DISCOVERED_TANKS, {})
        current_has_generator = self.config_entry.data.get("has_generator", False)

        # Run discovery
        client = OneControlClient(host, port)
        try:
            discovered = await client.discover_devices(duration=5.0)
            discovered_lights = discovered.get("lights", {})
            discovered_tanks = discovered.get("tanks", {})
            discovered_has_generator = discovered.get("has_generator", False)
        except Exception as err:
            _LOGGER.error("Rediscovery failed: %s", err)
            return self.async_abort(reason="discovery_failed")

        # Find NEW devices (not already in current config)
        self._new_lights = {
            k: v for k, v in discovered_lights.items()
            if k not in current_lights
        }
        self._new_tanks = {
            k: v for k, v in discovered_tanks.items()
            if k not in current_tanks
        }
        self._has_new_generator = discovered_has_generator and not current_has_generator

        # Check if we found anything new
        if not self._new_lights and not self._new_tanks and not self._has_new_generator:
            return self.async_abort(reason="no_new_devices")

        # Show what we found
        return await self.async_step_confirm_new()

    async def async_step_confirm_new(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm adding new devices."""
        if user_input is not None:
            # Merge new devices with existing
            current_lights = dict(self.config_entry.data.get(CONF_DISCOVERED_LIGHTS, {}))
            current_tanks = dict(self.config_entry.data.get(CONF_DISCOVERED_TANKS, {}))
            current_has_generator = self.config_entry.data.get("has_generator", False)

            # Add new devices
            current_lights.update(self._new_lights)
            current_tanks.update(self._new_tanks)
            new_has_generator = current_has_generator or self._has_new_generator

            # Update the config entry data
            new_data = {
                **self.config_entry.data,
                CONF_DISCOVERED_LIGHTS: current_lights,
                CONF_DISCOVERED_TANKS: current_tanks,
                "has_generator": new_has_generator,
            }

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data,
            )

            _LOGGER.info(
                "Added %d new lights, %d new tanks, generator=%s",
                len(self._new_lights),
                len(self._new_tanks),
                self._has_new_generator,
            )

            # Return empty options dict - we updated data directly
            return self.async_create_entry(title="", data={})

        # Build description of new devices
        new_light_names = [info["name"] for info in self._new_lights.values()]
        new_tank_names = [info["name"] for info in self._new_tanks.values()]

        description = []
        if new_light_names:
            description.append(f"**New Lights:** {', '.join(sorted(new_light_names))}")
        if new_tank_names:
            description.append(f"**New Tanks:** {', '.join(sorted(new_tank_names))}")
        if self._has_new_generator:
            description.append("**New:** Generator")

        return self.async_show_form(
            step_id="confirm_new",
            description_placeholders={
                "new_devices": "\n".join(description),
                "new_light_count": str(len(self._new_lights)),
                "new_tank_count": str(len(self._new_tanks)),
            },
        )
