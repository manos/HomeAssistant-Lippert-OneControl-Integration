"""Lippert OneControl integration for Home Assistant.

Controls and monitors RV devices via the Lippert OneControl system:
- Lights (ON/OFF)
- Generator (ON/OFF, state, hours, battery voltage)
- Water heaters (gas & electric ON/OFF with broadcast state tracking)
- Water pump (ON/OFF with broadcast state tracking)
- Tank sensors (Fresh, Grey, Black, LP)
- Leveler buttons (Auto Level, Retract, Cancel)

Config version 2: devices keyed by func_id (stable) instead of counter (volatile).
"""
from __future__ import annotations

import asyncio
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, SOURCE_INTEGRATION_DISCOVERY
from homeassistant.const import Platform, EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant, Event

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_PORT,
    DEFAULT_HOST,
    DEFAULT_PORT,
    CONF_DISCOVERED_LIGHTS,
    CONF_DISCOVERED_TANKS,
    CONF_DISCOVERED_WATER_HEATERS,
    CONF_DISCOVERED_WATER_PUMPS,
    CONF_DISCOVERED_GENERATORS,
)
from .coordinator import OneControlCoordinator

_LOGGER = logging.getLogger(__name__)

# Empty schema allows async_setup to be called without YAML config
CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.Schema({})},
    extra=vol.ALLOW_EXTRA,
)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.SWITCH,
]


def _migrate_v1_to_v2(data: dict) -> dict:
    """Migrate V1 config (counter-keyed) to V2 (func_id-keyed).

    V1 format: {"28": {"name": "Bedroom Light", "func_id": 57}}
    V2 format: {"57": {"name": "Bedroom Light"}}
    """
    def _convert(devices: dict) -> dict:
        new_devices: dict = {}
        for _counter_hex, info in devices.items():
            func_id = info.get("func_id")
            if func_id is not None:
                # V1 entry with func_id embedded -- migrate
                new_devices[str(func_id)] = {"name": info["name"]}
            else:
                # Already V2 or unknown format -- keep as-is
                new_devices[_counter_hex] = info
        return new_devices

    new_data = dict(data)
    for key in (CONF_DISCOVERED_LIGHTS, CONF_DISCOVERED_TANKS,
                CONF_DISCOVERED_WATER_HEATERS, CONF_DISCOVERED_WATER_PUMPS,
                CONF_DISCOVERED_GENERATORS):
        if key in new_data and new_data[key]:
            new_data[key] = _convert(new_data[key])

    # Handle legacy has_generator flag
    if new_data.pop("has_generator", None):
        if CONF_DISCOVERED_GENERATORS not in new_data or not new_data[CONF_DISCOVERED_GENERATORS]:
            new_data[CONF_DISCOVERED_GENERATORS] = {"95": {"name": "Generator"}}

    return new_data


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old config entry to current version."""
    if config_entry.version < 2:
        _LOGGER.info("Migrating OneControl config entry from version %d to 2", config_entry.version)
        new_data = _migrate_v1_to_v2(dict(config_entry.data))
        hass.config_entries.async_update_entry(
            config_entry,
            data=new_data,
            version=2,
        )
        _LOGGER.info("Migration to V2 (func_id-based) complete")
    return True


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Lippert OneControl component."""
    _LOGGER.debug("OneControl async_setup called")
    
    async def _async_discover(event: Event | None = None) -> None:
        """Try to discover OneControl controller."""
        _LOGGER.debug("OneControl discovery starting...")
        
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.data.get(CONF_HOST) == DEFAULT_HOST:
                _LOGGER.debug("OneControl already configured, skipping discovery")
                return

        _LOGGER.debug("Checking for OneControl at %s:%d", DEFAULT_HOST, DEFAULT_PORT)
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(DEFAULT_HOST, DEFAULT_PORT),
                timeout=3.0
            )
            writer.close()
            await writer.wait_closed()
            
            _LOGGER.info("OneControl controller discovered at %s:%d!", DEFAULT_HOST, DEFAULT_PORT)
            
            await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_INTEGRATION_DISCOVERY},
                data={CONF_HOST: DEFAULT_HOST, CONF_PORT: DEFAULT_PORT},
            )
        except (asyncio.TimeoutError, OSError, ConnectionRefusedError) as err:
            _LOGGER.debug("No OneControl controller found at %s:%d: %s", DEFAULT_HOST, DEFAULT_PORT, err)

    if hass.is_running:
        hass.async_create_task(_async_discover())
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _async_discover)
    
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Lippert OneControl from a config entry."""
    _LOGGER.debug("Setting up Lippert OneControl integration")

    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)

    coordinator = OneControlCoordinator(hass, host, port)
    
    # Generator presence -- V2 config: generators dict keyed by func_id
    discovered_generators = entry.data.get(CONF_DISCOVERED_GENERATORS, {})
    if discovered_generators:
        coordinator.init_generator()

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register update listener for options flow (rediscovery)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change (e.g., rediscovery adds new devices)."""
    _LOGGER.debug("Reloading Lippert OneControl after config update (new devices added)")
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Lippert OneControl integration")

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
