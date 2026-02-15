"""Config flow for Lippert OneControl integration.

Device discovery stores results keyed by func_id (stable firmware identifier).
Counters are volatile and resolved at runtime -- never stored in config.
"""
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
    CONF_DISCOVERED_GENERATORS,
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

    VERSION = 2  # Bumped for func_id-based config format

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._host: str = DEFAULT_HOST
        self._port: int = DEFAULT_PORT
        self._discovered_lights: dict = {}
        self._discovered_tanks: dict = {}
        self._discovered_water_heaters: dict = {}
        self._discovered_water_pumps: dict = {}
        self._discovered_generators: dict = {}

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

        await self.async_set_unique_id(f"lippert_onecontrol_{self._host}")
        self._abort_if_unique_id_configured()

        self.context["title_placeholders"] = {"host": self._host}
        return await self.async_step_discover()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step - get connection details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._host = user_input[CONF_HOST]
            self._port = user_input.get(CONF_PORT, DEFAULT_PORT)

            await self.async_set_unique_id(f"lippert_onecontrol_{self._host}")
            self._abort_if_unique_id_configured()

            if await validate_connection(self._host, self._port):
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
            self._discovered_generators = discovered.get("generators", {})
            
            _LOGGER.info(
                "Discovery found: %d lights, %d tanks, %d water heaters, %d water pumps, %d generators",
                len(self._discovered_lights),
                len(self._discovered_tanks),
                len(self._discovered_water_heaters),
                len(self._discovered_water_pumps),
                len(self._discovered_generators),
            )
        except Exception as err:
            _LOGGER.error("Discovery failed: %s", err)

        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the discovered devices with multi-select lists."""
        if user_input is not None:
            # Filter devices based on selection (keys are func_id strings)
            selected_lights = {
                k: v for k, v in self._discovered_lights.items()
                if k in user_input.get("lights", [])
            }
            selected_tanks = {
                k: v for k, v in self._discovered_tanks.items()
                if k in user_input.get("tanks", [])
            }
            selected_water_heaters = {
                k: v for k, v in self._discovered_water_heaters.items()
                if k in user_input.get("water_heaters", [])
            }
            selected_water_pumps = {
                k: v for k, v in self._discovered_water_pumps.items()
                if k in user_input.get("water_pumps", [])
            }
            selected_generators = {
                k: v for k, v in self._discovered_generators.items()
                if k in user_input.get("generators", [])
            }
            
            return self.async_create_entry(
                title=f"OneControl ({self._host})",
                data={
                    CONF_HOST: self._host,
                    CONF_PORT: self._port,
                    CONF_DISCOVERED_LIGHTS: selected_lights,
                    CONF_DISCOVERED_TANKS: selected_tanks,
                    CONF_DISCOVERED_WATER_HEATERS: selected_water_heaters,
                    CONF_DISCOVERED_WATER_PUMPS: selected_water_pumps,
                    CONF_DISCOVERED_GENERATORS: selected_generators,
                },
            )

        # Build schema with multi-select for each device type
        schema_dict = {}
        
        if self._discovered_lights:
            light_options = [
                SelectOptionDict(value=fid_str, label=f"💡 {info['name']}")
                for fid_str, info in sorted(
                    self._discovered_lights.items(), 
                    key=lambda x: x[1]["name"]
                )
            ]
            default_lights = list(self._discovered_lights.keys())
            schema_dict[vol.Optional("lights", default=default_lights)] = SelectSelector(
                SelectSelectorConfig(
                    options=light_options,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            )
        
        if self._discovered_tanks:
            tank_options = [
                SelectOptionDict(value=fid_str, label=f"🛢️ {info['name']}")
                for fid_str, info in sorted(
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
        
        if self._discovered_water_heaters:
            water_heater_options = [
                SelectOptionDict(value=fid_str, label=f"🔥 {info['name']}")
                for fid_str, info in sorted(
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
        
        if self._discovered_water_pumps:
            water_pump_options = [
                SelectOptionDict(value=fid_str, label=f"💧 {info['name']}")
                for fid_str, info in sorted(
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
        
        if self._discovered_generators:
            generator_options = [
                SelectOptionDict(value=fid_str, label=f"⚡ {info['name']}")
                for fid_str, info in sorted(
                    self._discovered_generators.items(),
                    key=lambda x: x[1]["name"]
                )
            ]
            default_generators = list(self._discovered_generators.keys())
            schema_dict[vol.Optional("generators", default=default_generators)] = SelectSelector(
                SelectSelectorConfig(
                    options=generator_options,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            )
        
        total_devices = (
            len(self._discovered_lights) + 
            len(self._discovered_tanks) + 
            len(self._discovered_water_heaters) +
            len(self._discovered_water_pumps) +
            len(self._discovered_generators)
        )
        
        if total_devices == 0:
            return self.async_show_form(
                step_id="confirm",
                data_schema=vol.Schema({}),
                description_placeholders={
                    "device_summary": "No devices discovered. Check controller connection.",
                },
            )

        summary_parts = []
        if self._discovered_lights:
            summary_parts.append(f"{len(self._discovered_lights)} lights")
        if self._discovered_tanks:
            summary_parts.append(f"{len(self._discovered_tanks)} tanks")
        if self._discovered_water_heaters:
            summary_parts.append(f"{len(self._discovered_water_heaters)} water heaters")
        if self._discovered_water_pumps:
            summary_parts.append(f"{len(self._discovered_water_pumps)} water pumps")
        if self._discovered_generators:
            summary_parts.append(f"{len(self._discovered_generators)} generators")
        
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
        self._new_generators: dict = {}

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
            return self.async_create_entry(title="", data={})

        current_lights = self.config_entry.data.get(CONF_DISCOVERED_LIGHTS, {})
        current_tanks = self.config_entry.data.get(CONF_DISCOVERED_TANKS, {})
        current_water_heaters = self.config_entry.data.get(CONF_DISCOVERED_WATER_HEATERS, {})
        current_water_pumps = self.config_entry.data.get(CONF_DISCOVERED_WATER_PUMPS, {})
        current_generators = self.config_entry.data.get(CONF_DISCOVERED_GENERATORS, {})

        light_names = sorted([info["name"] for info in current_lights.values()])
        tank_names = sorted([info["name"] for info in current_tanks.values()])
        water_heater_names = sorted([info["name"] for info in current_water_heaters.values()])
        water_pump_names = sorted([info["name"] for info in current_water_pumps.values()])
        generator_names = sorted([info["name"] for info in current_generators.values()])

        return self.async_show_form(
            step_id="current_devices",
            data_schema=vol.Schema({}),
            description_placeholders={
                "light_count": str(len(light_names)),
                "lights": ", ".join(light_names) if light_names else "None",
                "tank_count": str(len(tank_names)),
                "tanks": ", ".join(tank_names) if tank_names else "None",
                "water_heater_count": str(len(water_heater_names)),
                "water_heaters": ", ".join(water_heater_names) if water_heater_names else "None",
                "water_pump_count": str(len(water_pump_names)),
                "water_pumps": ", ".join(water_pump_names) if water_pump_names else "None",
                "generator_count": str(len(generator_names)),
                "generators": ", ".join(generator_names) if generator_names else "None",
            },
        )

    async def async_step_rediscover(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Run device rediscovery."""
        host = self.config_entry.data.get(CONF_HOST, DEFAULT_HOST)
        port = self.config_entry.data.get(CONF_PORT, DEFAULT_PORT)

        _LOGGER.info("Running rediscovery on %s:%d", host, port)

        # Get current devices (keyed by func_id string)
        current_lights = self.config_entry.data.get(CONF_DISCOVERED_LIGHTS, {})
        current_tanks = self.config_entry.data.get(CONF_DISCOVERED_TANKS, {})
        current_water_heaters = self.config_entry.data.get(CONF_DISCOVERED_WATER_HEATERS, {})
        current_water_pumps = self.config_entry.data.get(CONF_DISCOVERED_WATER_PUMPS, {})
        current_generators = self.config_entry.data.get(CONF_DISCOVERED_GENERATORS, {})

        # Run discovery (returns func_id-keyed dicts)
        client = OneControlClient(host, port)
        try:
            discovered = await client.discover_devices(duration=5.0)
            discovered_lights = discovered.get("lights", {})
            discovered_tanks = discovered.get("tanks", {})
            discovered_water_heaters = discovered.get("water_heaters", {})
            discovered_water_pumps = discovered.get("water_pumps", {})
            discovered_generators = discovered.get("generators", {})
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
        self._new_generators = {
            k: v for k, v in discovered_generators.items()
            if k not in current_generators
        }

        if not any([self._new_lights, self._new_tanks, self._new_water_heaters,
                     self._new_water_pumps, self._new_generators]):
            return self.async_abort(reason="no_new_devices")

        return await self.async_step_confirm_new()

    async def async_step_confirm_new(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm adding new devices with multi-select lists."""
        if user_input is not None:
            # Filter new devices based on selection
            selected_new_lights = {
                k: v for k, v in self._new_lights.items()
                if k in user_input.get("lights", [])
            }
            selected_new_tanks = {
                k: v for k, v in self._new_tanks.items()
                if k in user_input.get("tanks", [])
            }
            selected_new_water_heaters = {
                k: v for k, v in self._new_water_heaters.items()
                if k in user_input.get("water_heaters", [])
            }
            selected_new_water_pumps = {
                k: v for k, v in self._new_water_pumps.items()
                if k in user_input.get("water_pumps", [])
            }
            selected_new_generators = {
                k: v for k, v in self._new_generators.items()
                if k in user_input.get("generators", [])
            }
            
            # Merge with existing
            current_lights = dict(self.config_entry.data.get(CONF_DISCOVERED_LIGHTS, {}))
            current_tanks = dict(self.config_entry.data.get(CONF_DISCOVERED_TANKS, {}))
            current_water_heaters = dict(self.config_entry.data.get(CONF_DISCOVERED_WATER_HEATERS, {}))
            current_water_pumps = dict(self.config_entry.data.get(CONF_DISCOVERED_WATER_PUMPS, {}))
            current_generators = dict(self.config_entry.data.get(CONF_DISCOVERED_GENERATORS, {}))

            current_lights.update(selected_new_lights)
            current_tanks.update(selected_new_tanks)
            current_water_heaters.update(selected_new_water_heaters)
            current_water_pumps.update(selected_new_water_pumps)
            current_generators.update(selected_new_generators)

            new_data = {
                **self.config_entry.data,
                CONF_DISCOVERED_LIGHTS: current_lights,
                CONF_DISCOVERED_TANKS: current_tanks,
                CONF_DISCOVERED_WATER_HEATERS: current_water_heaters,
                CONF_DISCOVERED_WATER_PUMPS: current_water_pumps,
                CONF_DISCOVERED_GENERATORS: current_generators,
            }
            # Remove legacy keys
            new_data.pop("has_generator", None)

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data,
            )

            _LOGGER.info(
                "Added %d new lights, %d new tanks, %d new water heaters, %d new water pumps, %d generators",
                len(selected_new_lights),
                len(selected_new_tanks),
                len(selected_new_water_heaters),
                len(selected_new_water_pumps),
                len(selected_new_generators),
            )

            return self.async_create_entry(title="", data={})

        # Build schema with multi-select for each device type
        schema_dict = {}
        
        if self._new_lights:
            light_options = [
                SelectOptionDict(value=fid_str, label=f"💡 {info['name']}")
                for fid_str, info in sorted(
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
        
        if self._new_tanks:
            tank_options = [
                SelectOptionDict(value=fid_str, label=f"🛢️ {info['name']}")
                for fid_str, info in sorted(
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
        
        if self._new_water_heaters:
            water_heater_options = [
                SelectOptionDict(value=fid_str, label=f"🔥 {info['name']}")
                for fid_str, info in sorted(
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
        
        if self._new_water_pumps:
            water_pump_options = [
                SelectOptionDict(value=fid_str, label=f"💧 {info['name']}")
                for fid_str, info in sorted(
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
        
        if self._new_generators:
            generator_options = [
                SelectOptionDict(value=fid_str, label=f"⚡ {info['name']}")
                for fid_str, info in sorted(
                    self._new_generators.items(),
                    key=lambda x: x[1]["name"]
                )
            ]
            default_generators = list(self._new_generators.keys())
            schema_dict[vol.Optional("generators", default=default_generators)] = SelectSelector(
                SelectSelectorConfig(
                    options=generator_options,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            )

        summary_parts = []
        if self._new_lights:
            summary_parts.append(f"{len(self._new_lights)} lights")
        if self._new_tanks:
            summary_parts.append(f"{len(self._new_tanks)} tanks")
        if self._new_water_heaters:
            summary_parts.append(f"{len(self._new_water_heaters)} water heaters")
        if self._new_water_pumps:
            summary_parts.append(f"{len(self._new_water_pumps)} water pumps")
        if self._new_generators:
            summary_parts.append(f"{len(self._new_generators)} generators")

        return self.async_show_form(
            step_id="confirm_new",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "device_summary": f"Found {', '.join(summary_parts)}. Deselect any you don't want to add.",
            },
        )
