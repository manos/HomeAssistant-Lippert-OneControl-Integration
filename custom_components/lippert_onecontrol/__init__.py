"""Lippert OneControl integration for Home Assistant.

Control RV lights, generator, read tank levels, battery voltage,
generator state, and generator hours via the Lippert OneControl system.
"""
from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry, SOURCE_INTEGRATION_DISCOVERY
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_HOST, CONF_PORT, DEFAULT_HOST, DEFAULT_PORT
from .coordinator import OneControlCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Lippert OneControl component.
    
    This runs once when Home Assistant starts and attempts to discover
    the OneControl controller at the default IP (192.168.1.1:6969).
    """
    
    async def _async_discover() -> None:
        """Try to discover OneControl controller."""
        # Check if already configured
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.data.get(CONF_HOST) == DEFAULT_HOST:
                _LOGGER.debug("OneControl already configured, skipping discovery")
                return

        # Try to connect to the default IP
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(DEFAULT_HOST, DEFAULT_PORT),
                timeout=3.0
            )
            writer.close()
            await writer.wait_closed()
            
            _LOGGER.info("OneControl controller discovered at %s:%d", DEFAULT_HOST, DEFAULT_PORT)
            
            # Trigger discovery flow
            await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_INTEGRATION_DISCOVERY},
                data={CONF_HOST: DEFAULT_HOST, CONF_PORT: DEFAULT_PORT},
            )
        except (asyncio.TimeoutError, OSError, ConnectionRefusedError):
            _LOGGER.debug("No OneControl controller found at %s:%d", DEFAULT_HOST, DEFAULT_PORT)

    # Schedule discovery after HA is fully started
    hass.async_create_task(_async_discover())
    
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

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Lippert OneControl integration")

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
