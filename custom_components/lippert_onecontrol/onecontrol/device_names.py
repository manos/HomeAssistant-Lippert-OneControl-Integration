"""Device function ID to name mapping from decompiled OneControl app.

These are device NAME lookups keyed by func_id.  Actual devices present in
a given RV are discovered at runtime via 0x08 0x02 registration broadcasts.
The func_id determines the device TYPE, not whether it is safe to control.
"""

FUNCTION_NAMES: dict[int, str] = {
    # LIGHTS (safe to auto-toggle via latching relay)
    32: "Kitchen Ceiling Light",
    33: "Kitchen Sconce Light",
    41: "Living Room Ceiling Light",
    48: "Porch Light",
    49: "Awning Light",  # The actual LIGHT near the awning
    50: "Outdoor Light",
    57: "Bedroom Light",
    58: "Living Room Light",
    59: "Kitchen Light",
    63: "Bed Ceiling Light",
    122: "Scare Light",
    # TANKS (read-only sensors)
    67: "Fresh Tank",
    68: "Grey Tank",
    69: "Black Tank",
    70: "LP Tank",
    71: "Generator Fuel Tank",
    176: "LP Tank",
    # GENERATOR
    95: "Generator",
    # MOTORS / OTHER — require special handling, NOT lights
    105: "Awning",  # Awning MOTOR (extend/retract)
    107: "Water Tank Heater",  # Heating pad under fresh tank
    88: "Landing Gear",  # Leveler
    89: "Front Stabilizer",
    90: "Rear Stabilizer",
    96: "Vent Cover",
    97: "Main Slide",
    4: "Electric Water Heater",
    3: "Gas Water Heater",
    5: "Water Pump",
}
