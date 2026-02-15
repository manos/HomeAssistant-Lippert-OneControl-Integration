"""Constants for Lippert OneControl integration."""
from typing import Final

# Re-export FUNCTION_NAMES so HA platform modules can import from const
from .onecontrol.device_names import FUNCTION_NAMES  # noqa: F401

DOMAIN: Final = "lippert_onecontrol"

# Default connection settings
DEFAULT_HOST: Final = "192.168.1.1"
DEFAULT_PORT: Final = 6969

# Update intervals (seconds)
SCAN_INTERVAL: Final = 7  # Polling interval for sensors and state sync (~3s per read)

# Area mapping - derive suggested area from device name keywords
AREA_MAPPING: Final = {
    "kitchen": "Kitchen",
    "bed": "Bedroom",
    "bedroom": "Bedroom",
    "living": "Living Room",
    "living room": "Living Room",
    "porch": "Outdoor",
    "awning": "Outdoor",
    "scare": "Outdoor",
    "outdoor": "Outdoor",
    "fresh": "Utility",
    "grey": "Utility",
    "gray": "Utility",
    "black": "Utility",
    "lp": "Utility",
    "propane": "Utility",
    "generator": "Utility",
    "water heater": "Utility",
    "water pump": "Utility",
    "water tank heater": "Utility",
}


def get_suggested_area(name: str) -> str | None:
    """Get suggested area based on device name."""
    name_lower = name.lower()
    for keyword, area in AREA_MAPPING.items():
        if keyword in name_lower:
            return area
    return None


# Config flow keys
CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_DISCOVERED_LIGHTS: Final = "discovered_lights"
CONF_DISCOVERED_TANKS: Final = "discovered_tanks"
CONF_DISCOVERED_WATER_HEATERS: Final = "discovered_water_heaters"
CONF_DISCOVERED_WATER_PUMPS: Final = "discovered_water_pumps"
CONF_DISCOVERED_GENERATORS: Final = "discovered_generators"
