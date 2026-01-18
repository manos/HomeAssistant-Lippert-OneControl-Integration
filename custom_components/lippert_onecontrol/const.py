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

# Known function IDs (from decompiled OneControl app)
FUNCTION_NAMES: Final = {
    32: "Kitchen Ceiling Light",
    41: "Living Room Ceiling Light",
    48: "Porch Light",
    59: "Kitchen Light",
    63: "Bed Ceiling Light",
    122: "Scare Light",
    67: "Fresh Tank",
    68: "Grey Tank",
    69: "Black Tank",
    70: "LP Tank",
    95: "Generator",
    88: "Landing Gear",
    105: "Awning",
    4: "Electric Water Heater",
    5: "Water Pump",
    3: "Gas Water Heater",
}

# Known light counters (discovered from your RV)
KNOWN_LIGHTS: Final = {
    0x28: {"name": "Kitchen Ceiling Light", "func_id": 59},
    0x77: {"name": "Living Room Ceiling Light", "func_id": 41},
    0xFB: {"name": "Bed Ceiling Light", "func_id": 63},
    0xCF: {"name": "Porch Light", "func_id": 48},
    0x15: {"name": "Awning Light", "func_id": 105},
    0xFF: {"name": "Scare Light", "func_id": 122},
}

# Known tank counters
KNOWN_TANKS: Final = {
    0x04: {"name": "Grey Tank", "func_id": 68},
    0x3E: {"name": "Fresh Tank", "func_id": 67},
    0x86: {"name": "Black Tank", "func_id": 69},
    0x10: {"name": "LP Tank", "func_id": 70},
}

# Generator counter
GENERATOR_COUNTER: Final = 0x87

# Config flow
CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_DISCOVERED_DEVICES: Final = "discovered_devices"
CONF_ENABLED_LIGHTS: Final = "enabled_lights"
CONF_ENABLED_TANKS: Final = "enabled_tanks"

# Services
SERVICE_REFRESH: Final = "refresh"
SERVICE_ALL_LIGHTS_ON: Final = "all_lights_on"
SERVICE_ALL_LIGHTS_OFF: Final = "all_lights_off"
