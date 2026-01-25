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
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    SelectOptionDict,
)

from .const import (
    DOMAIN,
    DEFAULT_HOST,
    DEFAULT_PORT,
    CONF_DISCOVERED_LIGHTS,
    CONF_DISCOVERED_TANKS,
    CONF_DISCOVERED_WATER_HEATERS,
    CONF_DISCOVERED_WATER_PUMPS,
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
        self._discovered_water_heaters: dict = {}
        self._discovered_water_pumps: dict = {}
        self._has_generator: bool = False

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return OneControlOptionsFlowHandler()

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
            self._discovered_water_heaters = discovered.get("water_heaters", {})
            self._discovered_water_pumps = discovered.get("water_pumps", {})
            self._has_generator = discovered.get("has_generator", False)
            
            _LOGGER.info(
                "Discovery found: %d lights, %d tanks, %d water heaters, %d water pumps, generator=%s",
                len(self._discovered_lights),
                len(self._discovered_tanks),
                len(self._discovered_water_heaters),
                len(self._discovered_water_pumps),
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
        """Confirm the discovered devices with multi-select lists."""
        if user_input is not None:
            # Get selected device counters from multi-select
            selected_light_keys = user_input.get("lights", [])
            selected_tank_keys = user_input.get("tanks", [])
            selected_water_heater_keys = user_input.get("water_heaters", [])
            selected_water_pump_keys = user_input.get("water_pumps", [])
            include_generator = user_input.get("generator", self._has_generator)
            
            # Filter devices based on selection
            selected_lights = {
                k: v for k, v in self._discovered_lights.items()
                if k in selected_light_keys
            }
            selected_tanks = {
                k: v for k, v in self._discovered_tanks.items()
                if k in selected_tank_keys
            }
            selected_water_heaters = {
                k: v for k, v in self._discovered_water_heaters.items()
                if k in selected_water_heater_keys
            }
            selected_water_pumps = {
                k: v for k, v in self._discovered_water_pumps.items()
                if k in selected_water_pump_keys
            }
            
            # Create entry with selected devices only
            return self.async_create_entry(
                title=f"OneControl ({self._host})",
                data={
                    CONF_HOST: self._host,
                    CONF_PORT: self._port,
                    CONF_DISCOVERED_LIGHTS: selected_lights,
                    CONF_DISCOVERED_TANKS: selected_tanks,
                    CONF_DISCOVERED_WATER_HEATERS: selected_water_heaters,
                    CONF_DISCOVERED_WATER_PUMPS: selected_water_pumps,
                    "has_generator": include_generator and self._has_generator,
                },
            )

        # Build schema with multi-select for each device type
        schema_dict = {}
        
        # Build options for lights
        if self._discovered_lights:
            light_options = [
                SelectOptionDict(value=counter_hex, label=f"💡 {info['name']}")
                for counter_hex, info in sorted(
                    self._discovered_lights.items(), 
                    key=lambda x: x[1]["name"]
                )
            ]
            # Default: all selected
            default_lights = list(self._discovered_lights.keys())
            schema_dict[vol.Optional("lights", default=default_lights)] = SelectSelector(
                SelectSelectorConfig(
                    options=light_options,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            )
        
        # Build options for tanks
        if self._discovered_tanks:
            tank_options = [
                SelectOptionDict(value=counter_hex, label=f"🛢️ {info['name']}")
                for counter_hex, info in sorted(
                    self._discovered_tanks.items(),
                    key=lambda x: x[1]["name"]
                )
            ]
            default_tanks = list(self._discovered_tanks.keys())
            schema_dict[vol.Optional("tanks", default=default_tanks)] = SelectSelector(
                SelectSelectorConfig(
                    options=tank_options,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            )
        
        # Build options for water heaters
        if self._discovered_water_heaters:
            water_heater_options = [
                SelectOptionDict(value=counter_hex, label=f"🔥 {info['name']}")
                for counter_hex, info in sorted(
                    self._discovered_water_heaters.items(),
                    key=lambda x: x[1]["name"]
                )
            ]
            default_water_heaters = list(self._discovered_water_heaters.keys())
            schema_dict[vol.Optional("water_heaters", default=default_water_heaters)] = SelectSelector(
                SelectSelectorConfig(
                    options=water_heater_options,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            )
        
        # Build options for water pumps
        if self._discovered_water_pumps:
            water_pump_options = [
                SelectOptionDict(value=counter_hex, label=f"💧 {info['name']}")
                for counter_hex, info in sorted(
                    self._discovered_water_pumps.items(),
                    key=lambda x: x[1]["name"]
                )
            ]
            default_water_pumps = list(self._discovered_water_pumps.keys())
            schema_dict[vol.Optional("water_pumps", default=default_water_pumps)] = SelectSelector(
                SelectSelectorConfig(
                    options=water_pump_options,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            )
        
        # Add generator checkbox
        if self._has_generator:
            schema_dict[vol.Optional("generator", default=True)] = bool
        
        # Build description of what was found
        total_devices = (
            len(self._discovered_lights) + 
            len(self._discovered_tanks) + 
            len(self._discovered_water_heaters) +
            len(self._discovered_water_pumps) +
            (1 if self._has_generator else 0)
        )
        
        if total_devices == 0:
            # No devices found - show message and empty schema
            return self.async_show_form(
                step_id="confirm",
                data_schema=vol.Schema({}),
                description_placeholders={
                    "device_summary": "No devices discovered. Check controller connection.",
                },
            )

        # Build summary text
        summary_parts = []
        if self._discovered_lights:
            summary_parts.append(f"{len(self._discovered_lights)} lights")
        if self._discovered_tanks:
            summary_parts.append(f"{len(self._discovered_tanks)} tanks")
        if self._discovered_water_heaters:
            summary_parts.append(f"{len(self._discovered_water_heaters)} water heaters")
        if self._discovered_water_pumps:
            summary_parts.append(f"{len(self._discovered_water_pumps)} water pumps")
        if self._has_generator:
            summary_parts.append("1 generator")
        
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "device_summary": f"Found {', '.join(summary_parts)}. Deselect any devices you don't want to add.",
            },
        )


class OneControlOptionsFlowHandler(OptionsFlow):
    """Handle options flow for Lippert OneControl."""

    def __init__(self) -> None:
        """Initialize options flow."""
        self._new_lights: dict = {}
        self._new_tanks: dict = {}
        self._new_water_heaters: dict = {}
        self._new_water_pumps: dict = {}
        self._has_new_generator: bool = False

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options - show action selection."""
        if user_input is not None:
            action = user_input.get("action")
            if action == "rediscover":
                return await self.async_step_rediscover()
            elif action == "current_devices":
                return await self.async_step_current_devices()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("action"): vol.In({
                    "rediscover": "🔄 Rediscover Devices",
                    "current_devices": "📋 View Current Devices",
                })
            }),
        )

    async def async_step_current_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show current configured devices."""
        if user_input is not None:
            # User clicked submit, just return to close
            return self.async_create_entry(title="", data={})

        current_lights = self.config_entry.data.get(CONF_DISCOVERED_LIGHTS, {})
        current_tanks = self.config_entry.data.get(CONF_DISCOVERED_TANKS, {})
        current_water_heaters = self.config_entry.data.get(CONF_DISCOVERED_WATER_HEATERS, {})
        current_water_pumps = self.config_entry.data.get(CONF_DISCOVERED_WATER_PUMPS, {})
        has_generator = self.config_entry.data.get("has_generator", False)

        light_names = sorted([info["name"] for info in current_lights.values()])
        tank_names = sorted([info["name"] for info in current_tanks.values()])
        water_heater_names = sorted([info["name"] for info in current_water_heaters.values()])
        water_pump_names = sorted([info["name"] for info in current_water_pumps.values()])

        # Build device list text
        lights_text = ", ".join(light_names) if light_names else "None"
        tanks_text = ", ".join(tank_names) if tank_names else "None"
        water_heaters_text = ", ".join(water_heater_names) if water_heater_names else "None"
        water_pumps_text = ", ".join(water_pump_names) if water_pump_names else "None"
        generator_text = "Yes" if has_generator else "No"

        return self.async_show_form(
            step_id="current_devices",
            data_schema=vol.Schema({}),  # Empty schema but still shows description
            description_placeholders={
                "light_count": str(len(light_names)),
                "lights": lights_text,
                "tank_count": str(len(tank_names)),
                "tanks": tanks_text,
                "water_heater_count": str(len(water_heater_names)),
                "water_heaters": water_heaters_text,
                "water_pump_count": str(len(water_pump_names)),
                "water_pumps": water_pumps_text,
                "generator": generator_text,
            },
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
        current_water_heaters = self.config_entry.data.get(CONF_DISCOVERED_WATER_HEATERS, {})
        current_water_pumps = self.config_entry.data.get(CONF_DISCOVERED_WATER_PUMPS, {})
        current_has_generator = self.config_entry.data.get("has_generator", False)

        # Run discovery
        client = OneControlClient(host, port)
        try:
            discovered = await client.discover_devices(duration=5.0)
            discovered_lights = discovered.get("lights", {})
            discovered_tanks = discovered.get("tanks", {})
            discovered_water_heaters = discovered.get("water_heaters", {})
            discovered_water_pumps = discovered.get("water_pumps", {})
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
        self._new_water_heaters = {
            k: v for k, v in discovered_water_heaters.items()
            if k not in current_water_heaters
        }
        self._new_water_pumps = {
            k: v for k, v in discovered_water_pumps.items()
            if k not in current_water_pumps
        }
        self._has_new_generator = discovered_has_generator and not current_has_generator

        # Check if we found anything new
        if not self._new_lights and not self._new_tanks and not self._new_water_heaters and not self._new_water_pumps and not self._has_new_generator:
            return self.async_abort(reason="no_new_devices")

        # Show what we found
        return await self.async_step_confirm_new()

    async def async_step_confirm_new(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm adding new devices with multi-select lists."""
        if user_input is not None:
            # Get selected device counters from multi-select
            selected_light_keys = user_input.get("lights", [])
            selected_tank_keys = user_input.get("tanks", [])
            selected_water_heater_keys = user_input.get("water_heaters", [])
            selected_water_pump_keys = user_input.get("water_pumps", [])
            include_new_generator = user_input.get("generator", self._has_new_generator)
            
            # Filter new devices based on selection
            selected_new_lights = {
                k: v for k, v in self._new_lights.items()
                if k in selected_light_keys
            }
            selected_new_tanks = {
                k: v for k, v in self._new_tanks.items()
                if k in selected_tank_keys
            }
            selected_new_water_heaters = {
                k: v for k, v in self._new_water_heaters.items()
                if k in selected_water_heater_keys
            }
            selected_new_water_pumps = {
                k: v for k, v in self._new_water_pumps.items()
                if k in selected_water_pump_keys
            }
            
            # Merge selected new devices with existing
            current_lights = dict(self.config_entry.data.get(CONF_DISCOVERED_LIGHTS, {}))
            current_tanks = dict(self.config_entry.data.get(CONF_DISCOVERED_TANKS, {}))
            current_water_heaters = dict(self.config_entry.data.get(CONF_DISCOVERED_WATER_HEATERS, {}))
            current_water_pumps = dict(self.config_entry.data.get(CONF_DISCOVERED_WATER_PUMPS, {}))
            current_has_generator = self.config_entry.data.get("has_generator", False)

            # Add selected new devices
            current_lights.update(selected_new_lights)
            current_tanks.update(selected_new_tanks)
            current_water_heaters.update(selected_new_water_heaters)
            current_water_pumps.update(selected_new_water_pumps)
            new_has_generator = current_has_generator or (include_new_generator and self._has_new_generator)

            # Update the config entry data
            new_data = {
                **self.config_entry.data,
                CONF_DISCOVERED_LIGHTS: current_lights,
                CONF_DISCOVERED_TANKS: current_tanks,
                CONF_DISCOVERED_WATER_HEATERS: current_water_heaters,
                CONF_DISCOVERED_WATER_PUMPS: current_water_pumps,
                "has_generator": new_has_generator,
            }

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data,
            )

            _LOGGER.info(
                "Added %d new lights, %d new tanks, %d new water heaters, %d new water pumps, generator=%s",
                len(selected_new_lights),
                len(selected_new_tanks),
                len(selected_new_water_heaters),
                len(selected_new_water_pumps),
                include_new_generator and self._has_new_generator,
            )

            # Return empty options dict - we updated data directly
            return self.async_create_entry(title="", data={})

        # Build schema with multi-select for each device type
        schema_dict = {}
        
        # Build options for new lights
        if self._new_lights:
            light_options = [
                SelectOptionDict(value=counter_hex, label=f"💡 {info['name']}")
                for counter_hex, info in sorted(
                    self._new_lights.items(),
                    key=lambda x: x[1]["name"]
                )
            ]
            default_lights = list(self._new_lights.keys())
            schema_dict[vol.Optional("lights", default=default_lights)] = SelectSelector(
                SelectSelectorConfig(
                    options=light_options,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            )
        
        # Build options for new tanks
        if self._new_tanks:
            tank_options = [
                SelectOptionDict(value=counter_hex, label=f"🛢️ {info['name']}")
                for counter_hex, info in sorted(
                    self._new_tanks.items(),
                    key=lambda x: x[1]["name"]
                )
            ]
            default_tanks = list(self._new_tanks.keys())
            schema_dict[vol.Optional("tanks", default=default_tanks)] = SelectSelector(
                SelectSelectorConfig(
                    options=tank_options,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            )
        
        # Build options for new water heaters
        if self._new_water_heaters:
            water_heater_options = [
                SelectOptionDict(value=counter_hex, label=f"🔥 {info['name']}")
                for counter_hex, info in sorted(
                    self._new_water_heaters.items(),
                    key=lambda x: x[1]["name"]
                )
            ]
            default_water_heaters = list(self._new_water_heaters.keys())
            schema_dict[vol.Optional("water_heaters", default=default_water_heaters)] = SelectSelector(
                SelectSelectorConfig(
                    options=water_heater_options,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            )
        
        # Build options for new water pumps
        if self._new_water_pumps:
            water_pump_options = [
                SelectOptionDict(value=counter_hex, label=f"💧 {info['name']}")
                for counter_hex, info in sorted(
                    self._new_water_pumps.items(),
                    key=lambda x: x[1]["name"]
                )
            ]
            default_water_pumps = list(self._new_water_pumps.keys())
            schema_dict[vol.Optional("water_pumps", default=default_water_pumps)] = SelectSelector(
                SelectSelectorConfig(
                    options=water_pump_options,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            )
        
        # Add generator checkbox
        if self._has_new_generator:
            schema_dict[vol.Optional("generator", default=True)] = bool

        # Build summary text
        summary_parts = []
        if self._new_lights:
            summary_parts.append(f"{len(self._new_lights)} lights")
        if self._new_tanks:
            summary_parts.append(f"{len(self._new_tanks)} tanks")
        if self._new_water_heaters:
            summary_parts.append(f"{len(self._new_water_heaters)} water heaters")
        if self._new_water_pumps:
            summary_parts.append(f"{len(self._new_water_pumps)} water pumps")
        if self._has_new_generator:
            summary_parts.append("1 generator")

        return self.async_show_form(
            step_id="confirm_new",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "device_summary": f"Found {', '.join(summary_parts)}. Deselect any you don't want to add.",
            },
        )
