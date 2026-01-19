"""High-level OneControl client for Lippert RV systems.

This client handles:
- Light control (ON/OFF) with proper authentication
- Tank level reading
- Battery voltage reading  
- Generator hour meter reading

CRITICAL: Each control command requires a FRESH connection with authentication!
"""
from __future__ import annotations

import asyncio
import logging
import struct
import time
from typing import Optional

from .protocol import cobs_encode, decode_frames, tea_encrypt

_LOGGER = logging.getLogger(__name__)

# TEA cipher constant for REMOTE_CONTROL
REMOTE_CONTROL_CYPHER = 0xB16B00B5

# Default UUID for identity
DEFAULT_UUID = bytes([0x1c, 0x88, 0x43, 0x4f, 0xaf, 0x67, 0x82])

# Universal control values (work for all devices)
UNIVERSAL_PROTOCOL = 0x80
UNIVERSAL_SESSION = 0x80
UNIVERSAL_CONN = 0x40
UNIVERSAL_DEVICE = 0x04

# Generator-specific constants (uses different protocol!)
GENERATOR_COUNTER = 0x87
GENERATOR_PROTOCOL = 0x81
GENERATOR_CONN = 0xe8

# Generator state enum
GENERATOR_STATE_OFF = 0
GENERATOR_STATE_PRIMING = 1
GENERATOR_STATE_STARTING = 2
GENERATOR_STATE_RUNNING = 3
GENERATOR_STATE_STOPPING = 4

GENERATOR_STATE_NAMES = {
    GENERATOR_STATE_OFF: "Off",
    GENERATOR_STATE_PRIMING: "Priming",
    GENERATOR_STATE_STARTING: "Starting",
    GENERATOR_STATE_RUNNING: "Running",
    GENERATOR_STATE_STOPPING: "Stopping",
}


class OneControlClient:
    """Client for communicating with Lippert OneControl."""

    def __init__(self, host: str, port: int = 6969) -> None:
        """Initialize the client."""
        self.host = host
        self.port = port

    async def light_on(self, counter: int, retries: int = 2) -> bool:
        """Turn on a light by its counter with retries."""
        for attempt in range(retries + 1):
            result = await self._control_light(counter, on=True)
            if result:
                return True
            if attempt < retries:
                _LOGGER.warning("Light %02X ON failed, retrying (%d/%d)...", counter, attempt + 1, retries)
                await asyncio.sleep(0.5)
        return False

    async def light_off(self, counter: int, retries: int = 2) -> bool:
        """Turn off a light by its counter with retries."""
        for attempt in range(retries + 1):
            result = await self._control_light(counter, on=False)
            if result:
                return True
            if attempt < retries:
                _LOGGER.warning("Light %02X OFF failed, retrying (%d/%d)...", counter, attempt + 1, retries)
                await asyncio.sleep(0.5)
        return False

    async def _control_light(self, counter: int, on: bool) -> bool:
        """Control a light (internal implementation)."""
        reader: Optional[asyncio.StreamReader] = None
        writer: Optional[asyncio.StreamWriter] = None

        try:
            # Fresh connection for each command
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=10.0
            )

            # Clear initial data
            await asyncio.sleep(0.3)
            try:
                await asyncio.wait_for(reader.read(8192), timeout=0.3)
            except asyncio.TimeoutError:
                pass

            async def send(payload: bytes) -> None:
                writer.write(cobs_encode(payload))
                await writer.drain()

            async def recv(timeout: float = 0.5) -> list[bytes]:
                try:
                    data = await asyncio.wait_for(reader.read(8192), timeout=timeout)
                    return decode_frames(data)
                except asyncio.TimeoutError:
                    return []

            # 1. Register
            await send(bytes([0x01, 0x06, UNIVERSAL_SESSION, 0x00]))
            await asyncio.sleep(0.1)

            # 2. Identity
            await send(bytes([0x08, 0x00, UNIVERSAL_SESSION, 0x00]) + DEFAULT_UUID)
            await asyncio.sleep(0.2)
            await recv()

            # 3. Seed Request
            await send(bytes([
                0x02, UNIVERSAL_PROTOCOL, UNIVERSAL_CONN, counter,
                0x42, 0x00, UNIVERSAL_DEVICE
            ]))

            # 4. Wait for seed
            seed = None
            for _ in range(10):
                await asyncio.sleep(0.3)
                frames = await recv()
                for f in frames:
                    # Look for seed response: 06 8x ... 42 00 [device] [seed]
                    if len(f) >= 11 and f[0] == 0x06 and (f[1] & 0x80) and f[4] == 0x42:
                        seed = int.from_bytes(f[7:11], 'big')
                        break
                if seed:
                    break

            if seed is None:
                _LOGGER.error("No seed received for light %02X", counter)
                return False

            # 5. Compute key
            key = tea_encrypt(seed, REMOTE_CONTROL_CYPHER)
            key_bytes = struct.pack('>I', key)

            # 6. Key Transmit
            await send(bytes([
                0x06, UNIVERSAL_PROTOCOL, UNIVERSAL_CONN, counter,
                0x43, 0x00, UNIVERSAL_DEVICE
            ]) + key_bytes)
            await asyncio.sleep(0.2)
            await recv()

            # 7. Control command
            ctrl_conn = UNIVERSAL_CONN + 2
            value = 0x01 if on else 0x00
            await send(bytes([
                0x00, UNIVERSAL_PROTOCOL, ctrl_conn, counter, value
            ]))

            await asyncio.sleep(0.3)
            _LOGGER.debug("Light %02X turned %s", counter, "ON" if on else "OFF")
            return True

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout controlling light %02X", counter)
            return False
        except Exception as err:
            _LOGGER.error("Error controlling light %02X: %s", counter, err)
            return False

        finally:
            if writer:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

    async def read_all_sensors(self, duration: float = 3.0) -> dict:
        """
        Read ALL sensor data in a SINGLE connection.
        
        This is much more efficient than calling individual read methods,
        which each open separate connections.
        
        Returns dict with:
        - tanks: {counter: level_percentage}
        - battery_voltage: float | None
        - generator_hours: float | None
        - generator_state: int | None
        """
        reader: Optional[asyncio.StreamReader] = None
        writer: Optional[asyncio.StreamWriter] = None

        result = {
            "tanks": {},
            "battery_voltage": None,
            "generator_hours": None,
            "generator_state": None,
        }

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=10.0
            )

            async def send(payload: bytes) -> None:
                writer.write(cobs_encode(payload))
                await writer.drain()

            # Register once
            await send(bytes([0x01, 0x06, UNIVERSAL_SESSION, 0x00]))
            await asyncio.sleep(0.1)
            await send(bytes([0x08, 0x00, UNIVERSAL_SESSION, 0x00]) + DEFAULT_UUID)

            # Collect ALL broadcast frames in one pass
            start = time.monotonic()

            while time.monotonic() - start < duration:
                try:
                    data = await asyncio.wait_for(reader.read(8192), timeout=0.5)
                    frames = decode_frames(data)
                    for f in frames:
                        # Tank levels: 01 03 [counter] [level]
                        if len(f) >= 4 and f[0] == 0x01 and f[1] == 0x03:
                            counter = f[2]
                            level = f[3]
                            result["tanks"][counter] = level

                        # Generator Genie status: 05 03 87 [state] [volt_hi] [volt_lo] ...
                        elif len(f) >= 6 and f[0] == 0x05 and f[1] == 0x03 and f[2] == 0x87:
                            result["generator_state"] = f[3]
                            result["battery_voltage"] = f[4] + f[5] / 256.0

                        # Hour meter: 05 03 80 [uint32 BE seconds] [status]
                        elif len(f) >= 8 and f[0] == 0x05 and f[1] == 0x03 and f[2] == 0x80:
                            operating_seconds = int.from_bytes(f[3:7], 'big')
                            result["generator_hours"] = operating_seconds / 3600.0

                except asyncio.TimeoutError:
                    continue

            _LOGGER.debug(
                "read_all_sensors: tanks=%d, voltage=%s, hours=%s, state=%s",
                len(result["tanks"]),
                result["battery_voltage"],
                result["generator_hours"],
                result["generator_state"],
            )
            return result

        except Exception as err:
            _LOGGER.error("Error reading sensors: %s", err)
            return result

        finally:
            if writer:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

    async def read_tank_levels(self, duration: float = 3.0) -> dict[int, int]:
        """
        Read tank levels from controller broadcasts.
        
        Returns dict mapping counter to level percentage (0-100).
        """
        reader: Optional[asyncio.StreamReader] = None
        writer: Optional[asyncio.StreamWriter] = None

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=10.0
            )

            async def send(payload: bytes) -> None:
                writer.write(cobs_encode(payload))
                await writer.drain()

            # Register
            await send(bytes([0x01, 0x06, UNIVERSAL_SESSION, 0x00]))
            await asyncio.sleep(0.1)
            await send(bytes([0x08, 0x00, UNIVERSAL_SESSION, 0x00]) + DEFAULT_UUID)

            # Collect 01 03 frames
            levels: dict[int, int] = {}
            start = time.monotonic()

            while time.monotonic() - start < duration:
                try:
                    data = await asyncio.wait_for(reader.read(8192), timeout=0.5)
                    frames = decode_frames(data)
                    for f in frames:
                        # 01 03 frames: 01 03 [counter] [level]
                        if len(f) >= 4 and f[0] == 0x01 and f[1] == 0x03:
                            counter = f[2]
                            level = f[3]
                            levels[counter] = level

                except asyncio.TimeoutError:
                    continue

            return levels

        except Exception as err:
            _LOGGER.error("Error reading tank levels: %s", err)
            return {}

        finally:
            if writer:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

    async def read_battery_voltage(self, timeout: float = 3.0) -> Optional[float]:
        """
        Read battery voltage from Generator Genie broadcasts.
        
        Returns voltage as float, or None if not found.
        """
        reader: Optional[asyncio.StreamReader] = None
        writer: Optional[asyncio.StreamWriter] = None

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=10.0
            )

            async def send(payload: bytes) -> None:
                writer.write(cobs_encode(payload))
                await writer.drain()

            # Register
            await send(bytes([0x01, 0x06, UNIVERSAL_SESSION, 0x00]))
            await asyncio.sleep(0.1)
            await send(bytes([0x08, 0x00, UNIVERSAL_SESSION, 0x00]) + DEFAULT_UUID)

            # Look for 05 03 87 frame (Generator Genie status)
            start = time.monotonic()

            while time.monotonic() - start < timeout:
                try:
                    data = await asyncio.wait_for(reader.read(8192), timeout=0.5)
                    frames = decode_frames(data)
                    for f in frames:
                        # Generator Genie: 05 03 87 [state] [volt_hi] [volt_lo] ...
                        if len(f) >= 6 and f[0] == 0x05 and f[1] == 0x03 and f[2] == 0x87:
                            voltage = f[4] + f[5] / 256.0
                            return voltage

                except asyncio.TimeoutError:
                    continue

            return None

        except Exception as err:
            _LOGGER.error("Error reading battery voltage: %s", err)
            return None

        finally:
            if writer:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

    async def read_generator_hours(self, timeout: float = 3.0) -> Optional[float]:
        """
        Read generator operating hours from controller broadcasts.
        
        Returns hours as float, or None if not found.
        """
        reader: Optional[asyncio.StreamReader] = None
        writer: Optional[asyncio.StreamWriter] = None

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=10.0
            )

            async def send(payload: bytes) -> None:
                writer.write(cobs_encode(payload))
                await writer.drain()

            # Register
            await send(bytes([0x01, 0x06, UNIVERSAL_SESSION, 0x00]))
            await asyncio.sleep(0.1)
            await send(bytes([0x08, 0x00, UNIVERSAL_SESSION, 0x00]) + DEFAULT_UUID)

            # Look for 05 03 80 frame (Hour meter)
            start = time.monotonic()

            while time.monotonic() - start < timeout:
                try:
                    data = await asyncio.wait_for(reader.read(8192), timeout=0.5)
                    frames = decode_frames(data)
                    for f in frames:
                        # Hour meter: 05 03 80 [uint32 BE seconds] [status]
                        if len(f) >= 8 and f[0] == 0x05 and f[1] == 0x03 and f[2] == 0x80:
                            operating_seconds = int.from_bytes(f[3:7], 'big')
                            hours = operating_seconds / 3600.0
                            return hours

                except asyncio.TimeoutError:
                    continue

            return None

        except Exception as err:
            _LOGGER.error("Error reading generator hours: %s", err)
            return None

        finally:
            if writer:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

    async def read_generator_state(self, timeout: float = 3.0) -> int | None:
        """
        Read generator state from Generator Genie broadcasts.
        
        Returns state as int:
        - 0 = Off
        - 1 = Priming
        - 2 = Starting
        - 3 = Running
        - 4 = Stopping
        
        Or None if not found.
        """
        reader: Optional[asyncio.StreamReader] = None
        writer: Optional[asyncio.StreamWriter] = None

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=10.0
            )

            async def send(payload: bytes) -> None:
                writer.write(cobs_encode(payload))
                await writer.drain()

            # Register
            await send(bytes([0x01, 0x06, UNIVERSAL_SESSION, 0x00]))
            await asyncio.sleep(0.1)
            await send(bytes([0x08, 0x00, UNIVERSAL_SESSION, 0x00]) + DEFAULT_UUID)

            # Look for 05 03 87 frame (Generator Genie status)
            start = time.monotonic()

            while time.monotonic() - start < timeout:
                try:
                    data = await asyncio.wait_for(reader.read(8192), timeout=0.5)
                    frames = decode_frames(data)
                    for f in frames:
                        # Generator Genie: 05 03 87 [state] ...
                        if len(f) >= 4 and f[0] == 0x05 and f[1] == 0x03 and f[2] == 0x87:
                            return f[3]

                except asyncio.TimeoutError:
                    continue

            return None

        except Exception as err:
            _LOGGER.error("Error reading generator state: %s", err)
            return None

        finally:
            if writer:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

    async def generator_on(self) -> bool:
        """Turn on the generator."""
        return await self._control_generator(on=True)

    async def generator_off(self) -> bool:
        """Turn off the generator."""
        return await self._control_generator(on=False)

    async def _control_generator(self, on: bool) -> bool:
        """
        Control the generator (internal implementation).
        
        IMPORTANT: Generator uses DIFFERENT protocol than lights!
        - Protocol: 0x81 (not 0x80)
        - Control frame type: 0x01 (not 0x00)
        - ON command: 0x02
        - OFF command: 0x01
        """
        reader: Optional[asyncio.StreamReader] = None
        writer: Optional[asyncio.StreamWriter] = None

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=10.0
            )

            async def send(payload: bytes) -> None:
                writer.write(cobs_encode(payload))
                await writer.drain()

            async def recv(timeout: float = 0.5) -> list[bytes]:
                try:
                    data = await asyncio.wait_for(reader.read(8192), timeout=timeout)
                    return decode_frames(data)
                except asyncio.TimeoutError:
                    return []

            # 1. Register
            session = 0x7a
            await send(bytes([0x01, 0x06, session, 0x00]))
            await asyncio.sleep(0.1)
            await send(bytes([0x08, 0x00, session, 0x00]) + DEFAULT_UUID)
            await asyncio.sleep(0.3)
            await recv(0.3)

            # 2. Seed request - Protocol 0x81, device type 42 00 04
            await send(bytes([
                0x02, GENERATOR_PROTOCOL, GENERATOR_CONN, GENERATOR_COUNTER,
                0x42, 0x00, 0x04
            ]))

            # 3. Wait for seed (comes on protocol 0x82)
            seed = None
            for _ in range(10):
                await asyncio.sleep(0.3)
                frames = await recv()
                for f in frames:
                    # Look for 06 82 ... 42 00 04 [seed]
                    if len(f) >= 11 and f[0] == 0x06 and f[1] == 0x82 and f[4] == 0x42:
                        seed = int.from_bytes(f[7:11], 'big')
                        break
                if seed:
                    break

            if seed is None:
                _LOGGER.error("Generator: No seed received")
                return False

            # 4. Compute key
            key = tea_encrypt(seed, REMOTE_CONTROL_CYPHER)
            key_bytes = struct.pack('>I', key)

            # 5. Key transmit - device type 43 00 04
            await send(bytes([
                0x06, GENERATOR_PROTOCOL, GENERATOR_CONN, GENERATOR_COUNTER,
                0x43, 0x00, 0x04
            ]) + key_bytes)
            await asyncio.sleep(0.2)
            await recv()

            # 6. Control command - Frame type 0x01 (NOT 0x00!)
            # Commands: 0x02 = ON, 0x01 = OFF
            cmd = 0x02 if on else 0x01
            ctrl_conn = GENERATOR_CONN + 2
            await send(bytes([
                0x01, GENERATOR_PROTOCOL, ctrl_conn, GENERATOR_COUNTER,
                0x00, cmd
            ]))
            await asyncio.sleep(0.3)
            await recv()

            _LOGGER.debug("Generator turned %s", "ON" if on else "OFF")
            return True

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout controlling generator")
            return False
        except Exception as err:
            _LOGGER.error("Error controlling generator: %s", err)
            return False

        finally:
            if writer:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

    async def discover_devices(self, duration: float = 5.0) -> dict:
        """
        Discover all devices from controller broadcasts.
        
        Returns dict with:
        - lights: {counter_hex: {"name": str, "func_id": int}}
        - tanks: {counter_hex: {"name": str, "func_id": int}}
        - has_generator: bool
        
        This discovers actual devices present in the RV, not just
        all possible device types.
        """
        # Known function IDs from decompiled app
        # CRITICAL: Only include CONFIRMED lights - motors/heaters use same protocol!
        FUNCTION_NAMES = {
            # CONFIRMED LIGHTS (safe to toggle)
            32: "Kitchen Ceiling Light",
            33: "Kitchen Sconce Light",
            41: "Living Room Ceiling Light",
            48: "Porch Light",
            49: "Awning Light",  # The actual LIGHT, not motor
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
            # MOTORS/OTHER (NOT lights! Do NOT auto-add as lights!)
            # 105 = Awning MOTOR (extend/retract) - NOT a light!
            # 107 = Water Tank Heater (heating pad under fresh tank)
            # 88 = Landing Gear / Leveler
            # 89-90 = Stabilizers
            # 96 = Vent Cover
            # 97 = Main Slide
            105: "Awning",  # Motor, not light
            107: "Water Tank Heater",  # Heating pad - NOT a light!
            88: "Landing Gear",
            89: "Front Stabilizer",
            90: "Rear Stabilizer",
            96: "Vent Cover",
            97: "Main Slide",
            4: "Electric Water Heater",
            3: "Gas Water Heater",
            5: "Water Pump",
        }
        
        # ONLY include func_ids we are 100% SURE are lights
        # Removed: 105 (awning motor), 107 (may control water heater)
        LIGHT_FUNC_IDS = {32, 33, 41, 48, 49, 50, 57, 58, 59, 63, 122}
        TANK_FUNC_IDS = {67, 68, 69, 70, 71, 176}
        GENERATOR_FUNC_ID = 95
        
        # Future: Motors that need different handling
        # MOTOR_FUNC_IDS = {105, 97}  # Awning, Main Slide

        reader: Optional[asyncio.StreamReader] = None
        writer: Optional[asyncio.StreamWriter] = None
        
        lights: dict[str, dict] = {}
        tanks: dict[str, dict] = {}
        has_generator = False

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=10.0
            )

            async def send(payload: bytes) -> None:
                writer.write(cobs_encode(payload))
                await writer.drain()

            # Register
            await send(bytes([0x01, 0x06, UNIVERSAL_SESSION, 0x00]))
            await asyncio.sleep(0.1)
            await send(bytes([0x08, 0x00, UNIVERSAL_SESSION, 0x00]) + DEFAULT_UUID)

            # Collect broadcasts
            start = time.monotonic()
            while time.monotonic() - start < duration:
                try:
                    data = await asyncio.wait_for(reader.read(8192), timeout=0.5)
                    frames = decode_frames(data)
                    for f in frames:
                        # 08 02 frames: 08 02 [counter] 00 7d 28 [??] 00 [func_id] ...
                        if len(f) >= 9 and f[0] == 0x08 and f[1] == 0x02:
                            counter = f[2]
                            func_id = f[8]
                            
                            if func_id <= 0:
                                continue
                                
                            counter_hex = f"{counter:02x}"
                            name = FUNCTION_NAMES.get(func_id, f"Device {func_id}")
                            
                            if func_id in LIGHT_FUNC_IDS:
                                if counter_hex not in lights:
                                    lights[counter_hex] = {
                                        "name": name,
                                        "func_id": func_id,
                                    }
                                    _LOGGER.debug("Discovered light: %s (counter=%s)", name, counter_hex)
                            elif func_id in TANK_FUNC_IDS:
                                if counter_hex not in tanks:
                                    tanks[counter_hex] = {
                                        "name": name,
                                        "func_id": func_id,
                                    }
                                    _LOGGER.debug("Discovered tank: %s (counter=%s)", name, counter_hex)
                            elif func_id == GENERATOR_FUNC_ID:
                                has_generator = True
                                _LOGGER.debug("Discovered generator")

                except asyncio.TimeoutError:
                    continue

            _LOGGER.info("Discovery complete: %d lights, %d tanks, generator=%s",
                        len(lights), len(tanks), has_generator)
            
            return {
                "lights": lights,
                "tanks": tanks,
                "has_generator": has_generator,
            }

        except Exception as err:
            _LOGGER.error("Error during device discovery: %s", err)
            return {"lights": {}, "tanks": {}, "has_generator": False}

        finally:
            if writer:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
