"""Tests for config migration from V1 (counter-keyed) to V2 (func_id-keyed).

The migration logic is pure dict transformation with no HA dependencies,
so we test it by inlining the same logic here.
"""
def _migrate_v1_to_v2(data: dict) -> dict:
    """Migrate V1 config (counter-keyed) to V2 (func_id-keyed).

    This is an exact copy of the function in __init__.py for testability
    without HA imports.

    V1 format: {"28": {"name": "Bedroom Light", "func_id": 57}}
    V2 format: {"57": {"name": "Bedroom Light"}}
    """
    DEVICE_KEYS = (
        "discovered_lights",
        "discovered_tanks",
        "discovered_water_heaters",
        "discovered_water_pumps",
        "discovered_generators",
    )

    def _convert(devices: dict) -> dict:
        new_devices: dict = {}
        for _counter_hex, info in devices.items():
            func_id = info.get("func_id")
            if func_id is not None:
                new_devices[str(func_id)] = {"name": info["name"]}
            else:
                new_devices[_counter_hex] = info
        return new_devices

    new_data = dict(data)
    for key in DEVICE_KEYS:
        if key in new_data and new_data[key]:
            new_data[key] = _convert(new_data[key])

    if new_data.pop("has_generator", None):
        if "discovered_generators" not in new_data or not new_data["discovered_generators"]:
            new_data["discovered_generators"] = {"95": {"name": "Generator"}}

    return new_data


class TestMigrationV1ToV2:
    """Tests for _migrate_v1_to_v2 config migration."""

    def test_migrate_lights(self):
        """Test migrating V1 lights config to V2."""
        v1_data = {
            "host": "192.168.1.1",
            "port": 6969,
            "discovered_lights": {
                "28": {"name": "Bedroom Light", "func_id": 57},
                "2a": {"name": "Kitchen Ceiling Light", "func_id": 48},
            },
            "discovered_tanks": {},
            "discovered_water_heaters": {},
            "discovered_water_pumps": {},
            "discovered_generators": {},
        }
        v2_data = _migrate_v1_to_v2(v1_data)
        
        # Keys should now be func_id strings
        assert "57" in v2_data["discovered_lights"]
        assert "48" in v2_data["discovered_lights"]
        # Old counter-hex keys should be gone
        assert "28" not in v2_data["discovered_lights"]
        assert "2a" not in v2_data["discovered_lights"]
        # func_id should be stripped from the value dict
        assert "func_id" not in v2_data["discovered_lights"]["57"]
        assert v2_data["discovered_lights"]["57"]["name"] == "Bedroom Light"

    def test_migrate_generators(self):
        """Test migrating V1 generators config to V2."""
        v1_data = {
            "host": "192.168.1.1",
            "port": 6969,
            "discovered_lights": {},
            "discovered_tanks": {},
            "discovered_water_heaters": {},
            "discovered_water_pumps": {},
            "discovered_generators": {
                "5c": {"name": "Generator", "func_id": 95},
            },
        }
        v2_data = _migrate_v1_to_v2(v1_data)
        
        assert "95" in v2_data["discovered_generators"]
        assert "5c" not in v2_data["discovered_generators"]
        assert v2_data["discovered_generators"]["95"]["name"] == "Generator"

    def test_migrate_legacy_has_generator(self):
        """Test migrating legacy has_generator flag."""
        v1_data = {
            "host": "192.168.1.1",
            "port": 6969,
            "has_generator": True,
            "discovered_lights": {},
            "discovered_tanks": {},
            "discovered_water_heaters": {},
            "discovered_water_pumps": {},
            "discovered_generators": {},
        }
        v2_data = _migrate_v1_to_v2(v1_data)
        
        assert "95" in v2_data["discovered_generators"]
        assert v2_data["discovered_generators"]["95"]["name"] == "Generator"
        assert "has_generator" not in v2_data

    def test_migrate_already_v2(self):
        """Test migration is no-op for already V2 config."""
        v2_data = {
            "host": "192.168.1.1",
            "port": 6969,
            "discovered_lights": {
                "57": {"name": "Bedroom Light"},
            },
            "discovered_tanks": {},
            "discovered_water_heaters": {},
            "discovered_water_pumps": {},
            "discovered_generators": {},
        }
        result = _migrate_v1_to_v2(v2_data)
        
        assert result["discovered_lights"] == v2_data["discovered_lights"]

    def test_migrate_water_heaters_and_pumps(self):
        """Test migrating V1 water heaters and pumps."""
        v1_data = {
            "host": "192.168.1.1",
            "port": 6969,
            "discovered_lights": {},
            "discovered_tanks": {
                "10": {"name": "Fresh Tank", "func_id": 67},
            },
            "discovered_water_heaters": {
                "1a": {"name": "Gas Water Heater", "func_id": 3},
                "1b": {"name": "Electric Water Heater", "func_id": 4},
            },
            "discovered_water_pumps": {
                "1c": {"name": "Water Pump", "func_id": 5},
            },
            "discovered_generators": {},
        }
        v2_data = _migrate_v1_to_v2(v1_data)
        
        assert "67" in v2_data["discovered_tanks"]
        assert "3" in v2_data["discovered_water_heaters"]
        assert "4" in v2_data["discovered_water_heaters"]
        assert "5" in v2_data["discovered_water_pumps"]
        assert v2_data["discovered_tanks"]["67"]["name"] == "Fresh Tank"

    def test_migrate_preserves_host_port(self):
        """Test migration preserves non-device fields."""
        v1_data = {
            "host": "10.0.0.1",
            "port": 7070,
            "discovered_lights": {},
            "discovered_tanks": {},
            "discovered_water_heaters": {},
            "discovered_water_pumps": {},
            "discovered_generators": {},
        }
        v2_data = _migrate_v1_to_v2(v1_data)
        
        assert v2_data["host"] == "10.0.0.1"
        assert v2_data["port"] == 7070
