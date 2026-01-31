"""Lippert OneControl integration for Home Assistant.

Control RV lights, generator, read tank levels, battery voltage,
generator state, and generator hours via the Lippert OneControl system.
"""
from __future__ import annotations

import asyncio
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, SOURCE_INTEGRATION_DISCOVERY
from homeassistant.const import Platform, EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant, Event

from .const import DOMAIN, CONF_HOST, CONF_PORT, DEFAULT_HOST, DEFAULT_PORT
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


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Lippert OneControl component."""
    _LOGGER.debug("OneControl async_setup called")
    
    async def _async_discover(event: Event | None = None) -> None:
        """Try to discover OneControl controller."""
        _LOGGER.debug("OneControl discovery starting...")
        
        # Check if already configured
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.data.get(CONF_HOST) == DEFAULT_HOST:
                _LOGGER.debug("OneControl already configured, skipping discovery")
                return

        # Try to connect to the default IP
        _LOGGER.debug("Checking for OneControl at %s:%d", DEFAULT_HOST, DEFAULT_PORT)
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(DEFAULT_HOST, DEFAULT_PORT),
                timeout=3.0
            )
            writer.close()
            await writer.wait_closed()
            
            _LOGGER.info("OneControl controller discovered at %s:%d!", DEFAULT_HOST, DEFAULT_PORT)
            
            # Trigger discovery flow
            await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_INTEGRATION_DISCOVERY},
                data={CONF_HOST: DEFAULT_HOST, CONF_PORT: DEFAULT_PORT},
            )
        except (asyncio.TimeoutError, OSError, ConnectionRefusedError) as err:
            _LOGGER.debug("No OneControl controller found at %s:%d: %s", DEFAULT_HOST, DEFAULT_PORT, err)

    # Wait for HA to fully start, then run discovery
    if hass.is_running:
        # HA already started, run now
        hass.async_create_task(_async_discover())
    else:
        # Wait for HA to start
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _async_discover)
    
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Lippert OneControl from a config entry."""
    _LOGGER.info("Setting up Lippert OneControl integration")

    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)

    # Create the coordinator
    coordinator = OneControlCoordinator(hass, host, port)

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
    _LOGGER.info("Reloading Lippert OneControl after config update (new devices added)")
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Lippert OneControl integration")

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
