"""Constants for Lippert OneControl integration."""
from typing import Final

DOMAIN: Final = "lippert_onecontrol"

# Default connection settings
DEFAULT_HOST: Final = "192.168.1.1"
DEFAULT_PORT: Final = 6969

# Timeouts
CONNECT_TIMEOUT: Final = 10
COMMAND_TIMEOUT: Final = 5

# Update intervals (seconds)
SCAN_INTERVAL: Final = 30  # For sensors
LIGHT_POLL_INTERVAL: Final = 5  # For light state

# Device types from OneControl
DEVICE_TYPE_LIGHT: Final = "light"
DEVICE_TYPE_TANK: Final = "tank"
DEVICE_TYPE_GENERATOR: Final = "generator"
DEVICE_TYPE_WATER_HEATER: Final = "water_heater"

# All known function IDs from decompiled OneControl app
# These are ALL possible devices - actual presence is discovered via auto-discovery
FUNCTION_NAMES: Final = {
    # Lights
    32: "Kitchen Ceiling Light",
    41: "Living Room Ceiling Light", 
    48: "Porch Light",
    59: "Kitchen Light",
    63: "Bed Ceiling Light",
    122: "Scare Light",
    105: "Awning Light",
    # Tanks
    67: "Fresh Tank",
    68: "Grey Tank",
    69: "Black Tank",
    70: "LP Tank",
    # Other
    95: "Generator",
    88: "Landing Gear",
    4: "Electric Water Heater",
    5: "Water Pump",
    3: "Gas Water Heater",
}

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
    "fresh": "Utility",
    "grey": "Utility",
    "gray": "Utility",
    "black": "Utility",
    "lp": "Utility",
    "propane": "Utility",
    "generator": "Utility",
    "water heater": "Utility",
    "water pump": "Utility",
}


def get_suggested_area(name: str) -> str | None:
    """Get suggested area based on device name."""
    name_lower = name.lower()
    for keyword, area in AREA_MAPPING.items():
        if keyword in name_lower:
            return area
    return None


# Generator counter
GENERATOR_COUNTER: Final = 0x87

# Config flow
CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_DISCOVERED_DEVICES: Final = "discovered_devices"
CONF_DISCOVERED_LIGHTS: Final = "discovered_lights"
CONF_DISCOVERED_TANKS: Final = "discovered_tanks"

# Services
SERVICE_REFRESH: Final = "refresh"
SERVICE_ALL_LIGHTS_ON: Final = "all_lights_on"
SERVICE_ALL_LIGHTS_OFF: Final = "all_lights_off"
