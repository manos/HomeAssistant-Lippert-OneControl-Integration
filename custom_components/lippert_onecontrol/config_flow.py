"""Config flow for Lippert OneControl integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT

from .const import DOMAIN, DEFAULT_HOST, DEFAULT_PORT

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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)

            # Check if already configured
            await self.async_set_unique_id(f"lippert_onecontrol_{host}")
            self._abort_if_unique_id_configured()

            # Test connection
            if await validate_connection(host, port):
                return self.async_create_entry(
                    title=f"Lippert OneControl ({host})",
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                    },
                )
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
