"""High-level OneControl client for Lippert RV systems.

This client handles:
- Device discovery via 0x08 0x02 registration broadcasts
- Light control (ON/OFF) with seed/key authentication
- Water heater and water pump control (latching relay toggle)
- Generator control (ON/OFF) with TEA cipher authentication
- Leveler control (Auto Level, Retract, Cancel)
- Sensor reading (tanks, battery voltage, generator state/hours)

Protocol: TCP on port 6969, COBS-encoded frames, CRC-8/MAXIM checksums.
Each control command requires a FRESH connection with full authentication.
"""
from __future__ import annotations

import asyncio
import logging
import struct
import time
from typing import Optional

from .device_names import FUNCTION_NAMES
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
# Counter varies by RV installation - discovered dynamically at config time.
# This value is only used as a fallback default in function signatures.
GENERATOR_COUNTER = 0x24
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

    async def water_heater_on(self, counter: int, retries: int = 2) -> bool:
        """Turn on a water heater by its counter.
        
        Water heaters use the same latching relay protocol as lights.
        """
        for attempt in range(retries + 1):
            result = await self._control_light(counter, on=True)
            if result:
                _LOGGER.debug("Water heater %02X turned ON", counter)
                return True
            if attempt < retries:
                _LOGGER.warning("Water heater %02X ON failed, retrying (%d/%d)...", counter, attempt + 1, retries)
                await asyncio.sleep(0.5)
        return False

    async def water_heater_off(self, counter: int, retries: int = 2) -> bool:
        """Turn off a water heater by its counter.
        
        Water heaters use the same latching relay protocol as lights.
        """
        for attempt in range(retries + 1):
            result = await self._control_light(counter, on=False)
            if result:
                _LOGGER.debug("Water heater %02X turned OFF", counter)
                return True
            if attempt < retries:
                _LOGGER.warning("Water heater %02X OFF failed, retrying (%d/%d)...", counter, attempt + 1, retries)
                await asyncio.sleep(0.5)
        return False

    async def water_pump_on(self, counter: int, retries: int = 2) -> bool:
        """Turn on the water pump by its counter.
        
        Water pump uses the same latching relay protocol as lights.
        """
        for attempt in range(retries + 1):
            result = await self._control_light(counter, on=True)
            if result:
                _LOGGER.debug("Water pump %02X turned ON", counter)
                return True
            if attempt < retries:
                _LOGGER.warning("Water pump %02X ON failed, retrying (%d/%d)...", counter, attempt + 1, retries)
                await asyncio.sleep(0.5)
        return False

    async def water_pump_off(self, counter: int, retries: int = 2) -> bool:
        """Turn off the water pump by its counter.
        
        Water pump uses the same latching relay protocol as lights.
        """
        for attempt in range(retries + 1):
            result = await self._control_light(counter, on=False)
            if result:
                _LOGGER.debug("Water pump %02X turned OFF", counter)
                return True
            if attempt < retries:
                _LOGGER.warning("Water pump %02X OFF failed, retrying (%d/%d)...", counter, attempt + 1, retries)
                await asyncio.sleep(0.5)
        return False

    # ========== LEVELER CONTROL ==========
    # Leveler uses button-press simulation (frame type 0x03)
    # Analysis says NO auth required, but captures show seed/key exchange
    # Try simplified flow: registration -> button (skip seed/key)

    async def _send_leveler_button(self, button: int, device: int = 0x01) -> bool:
        """Send a leveler button press command.
        
        Leveler uses frame type 0x03 with button simulation.
        Based on captures: send registration first, then button command.
        
        Args:
            button: Button code (0x10=AutoLevel, 0x20=Retract, 0x40=Enter, 0x80=Cancel)
            device: Device ID (0x01 for button press, 0x08 for Enter confirmation)
        """
        writer: Optional[asyncio.StreamWriter] = None

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=10.0
            )

            # Skip identity registration - just send leveler commands directly
            # Use two-byte connection like capture: d4 e6 -> d6 e6
            # We'll use 40 40 -> 42 40
            conn_hi = 0x40
            conn_lo = 0x40
            leveler_id = 0xaa  # ID from capture
            
            # Build registration frame (8 bytes)
            reg_frame = bytes([0x02, UNIVERSAL_PROTOCOL, conn_hi, conn_lo, 0x44, 0x02, 0x04, leveler_id])
            
            # Build button frame
            btn_frame = bytes([0x03, UNIVERSAL_PROTOCOL, conn_hi + 2, conn_lo, 0x41, device, 0x02, button])
            
            # Send as compound packet: both COBS-encoded frames in one TCP write
            # This matches how the capture shows them being sent together
            encoded_reg = cobs_encode(reg_frame)
            encoded_btn = cobs_encode(btn_frame)
            compound = encoded_reg + encoded_btn
            _LOGGER.debug("Leveler compound frame: %s", compound.hex())
            writer.write(compound)
            await writer.drain()
            await asyncio.sleep(0.3)

            # Check for ack
            try:
                response = await asyncio.wait_for(reader.read(8192), timeout=0.5)
                if response:
                    frames = decode_frames(response)
                    for f in frames:
                        if len(f) > 0 and f[0] == 0x13:
                            _LOGGER.debug("Leveler ACK received: %s", f.hex())
            except asyncio.TimeoutError:
                pass

            _LOGGER.info("Leveler button 0x%02X sent", button)
            return True

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout sending leveler button")
            return False
        except Exception as err:
            _LOGGER.error("Error sending leveler button: %s", err)
            return False

        finally:
            if writer:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

    async def leveler_auto_level(self) -> bool:
        """Start auto-leveling sequence.
        
        Sends AutoLevel button (0x10) followed by Enter confirmation (0x40).
        The leveler will automatically level the RV.
        
        Note: Requires ACC power ON and parking brake engaged.
        """
        _LOGGER.info("Starting auto-level sequence")
        
        # Press AutoLevel button
        if not await self._send_leveler_button(0x10, device=0x01):
            return False
        
        await asyncio.sleep(0.3)
        
        # Press Enter to confirm
        if not await self._send_leveler_button(0x40, device=0x08):
            return False
        
        _LOGGER.info("Auto-level sequence initiated")
        return True

    async def leveler_retract(self) -> bool:
        """Retract all leveler jacks.
        
        Sends Retract button (0x20) followed by Enter confirmation (0x40).
        All jacks will retract to stored position.
        
        Note: Requires ACC power ON and parking brake engaged.
        """
        _LOGGER.info("Starting retract sequence")
        
        # Press Retract button
        if not await self._send_leveler_button(0x20, device=0x01):
            return False
        
        await asyncio.sleep(0.3)
        
        # Press Enter to confirm
        if not await self._send_leveler_button(0x40, device=0x08):
            return False
        
        _LOGGER.info("Retract sequence initiated")
        return True

    async def leveler_cancel(self) -> bool:
        """Cancel current leveler operation.
        
        Sends Cancel button (0x80) to stop any ongoing leveling operation.
        """
        _LOGGER.info("Cancelling leveler operation")
        
        if not await self._send_leveler_button(0x80, device=0x01):
            return False
        
        _LOGGER.info("Leveler operation cancelled")
        return True

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
        Read ALL sensor data and device registration in a SINGLE connection.
        
        Also captures 0x08 0x02 registration frames to build a live
        func_id <-> counter map.  This map is critical: counters are volatile
        and can change after controller reboots, so every poll cycle
        refreshes the mapping.
        
        Returns dict with:
        - tanks: {counter: level_percentage}
        - battery_voltage: float | None
        - generator_hours: float | None
        - generator_state: int | None
        - relay_states: {counter: bool}
        - device_map: {func_id(int): counter(int)}  -- live registration map
        """
        reader: Optional[asyncio.StreamReader] = None
        writer: Optional[asyncio.StreamWriter] = None

        result: dict = {
            "tanks": {},
            "battery_voltage": None,
            "generator_hours": None,
            "generator_state": None,
            "relay_states": {},  # counter -> bool (on/off) for latching relays
            "device_map": {},    # func_id -> counter (live registration map, last-wins)
            "device_map_all": {},  # func_id -> list[counter] (all counters seen per func_id)
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
                        # Device registration: 08 02 [counter] ... [func_id]
                        # Builds the live func_id -> counter map
                        if len(f) >= 9 and f[0] == 0x08 and f[1] == 0x02:
                            counter = f[2]
                            func_id = f[8]
                            if func_id > 0:
                                result["device_map"][func_id] = counter
                                if func_id not in result["device_map_all"]:
                                    result["device_map_all"][func_id] = []
                                if counter not in result["device_map_all"][func_id]:
                                    result["device_map_all"][func_id].append(counter)

                        # Tank levels: 01 03 [counter] [level]
                        elif len(f) >= 4 and f[0] == 0x01 and f[1] == 0x03:
                            counter = f[2]
                            level = f[3]
                            result["tanks"][counter] = level

                        # Hour meter: 05 03 80 [uint32 BE seconds] [status]
                        # MUST come before generator status check to avoid 0x80 collision
                        elif len(f) >= 8 and f[0] == 0x05 and f[1] == 0x03 and f[2] == 0x80:
                            operating_seconds = int.from_bytes(f[3:7], 'big')
                            result["generator_hours"] = operating_seconds / 3600.0

                        # Generator Genie status: 05 03 [counter] [state] [volt_hi] [volt_lo]
                        # Accept from ANY counter that isn't the hour meter (0x80)
                        elif len(f) >= 6 and f[0] == 0x05 and f[1] == 0x03:
                            result["generator_state"] = f[3]
                            result["battery_voltage"] = f[4] + f[5] / 256.0

                        # RelayBasicLatchingStatus2: 06 03 [counter] [status] ...
                        # Status byte bit 0 = on/off state
                        elif len(f) >= 4 and f[0] == 0x06 and f[1] == 0x03:
                            counter = f[2]
                            status_byte = f[3]
                            is_on = bool(status_byte & 0x01)
                            result["relay_states"][counter] = is_on

                except asyncio.TimeoutError:
                    continue

            _LOGGER.debug(
                "read_all_sensors: tanks=%d, voltage=%s, hours=%s, state=%s, device_map=%d entries",
                len(result["tanks"]),
                result["battery_voltage"],
                result["generator_hours"],
                result["generator_state"],
                len(result["device_map"]),
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

    async def generator_on(self, counter: int = GENERATOR_COUNTER) -> bool:
        """Turn on the generator."""
        return await self._control_generator(on=True, counter=counter)

    async def generator_off(self, counter: int = GENERATOR_COUNTER) -> bool:
        """Turn off the generator."""
        return await self._control_generator(on=False, counter=counter)

    async def _control_generator(self, on: bool, counter: int = GENERATOR_COUNTER) -> bool:
        """
        Control the generator (internal implementation).

        Generator uses protocol 0x81 and conn 0xE8 (not the universal 0x80/0x40
        used by lights). These are fixed values, not session-specific.
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

            # 2. Seed request
            await send(bytes([
                0x02, GENERATOR_PROTOCOL, GENERATOR_CONN, counter,
                0x42, 0x00, 0x04
            ]))

            # 3. Wait for seed
            seed = None
            for _ in range(10):
                await asyncio.sleep(0.3)
                frames = await recv()
                for f in frames:
                    if len(f) >= 11 and f[0] == 0x06 and f[4] == 0x42:
                        seed = int.from_bytes(f[7:11], 'big')
                        break
                if seed:
                    break

            if seed is None:
                _LOGGER.error("Generator: No seed received for counter 0x%02x", counter)
                return False

            # 4. Compute TEA key
            key = tea_encrypt(seed, REMOTE_CONTROL_CYPHER)
            key_bytes = struct.pack('>I', key)

            # 5. Key transmit
            await send(bytes([
                0x06, GENERATOR_PROTOCOL, GENERATOR_CONN, counter,
                0x43, 0x00, 0x04
            ]) + key_bytes)
            await asyncio.sleep(0.2)
            await recv()

            # 6. Control command
            cmd = 0x02 if on else 0x01
            ctrl_conn = GENERATOR_CONN + 2
            await send(bytes([
                0x01, GENERATOR_PROTOCOL, ctrl_conn, counter,
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
        
        Returns dict keyed by func_id (the STABLE device identifier):
        - lights: {func_id_str: {"name": str}}
        - tanks: {func_id_str: {"name": str}}
        - water_heaters: {func_id_str: {"name": str}}
        - water_pumps: {func_id_str: {"name": str}}
        - generators: {func_id_str: {"name": str}}
        
        func_id is permanent (from device firmware). Counters are volatile
        and resolved at runtime via read_all_sensors() device_map.
        """
        # func_id classification sets
        LIGHT_FUNC_IDS = {32, 33, 41, 48, 49, 50, 57, 58, 59, 63, 122}
        TANK_FUNC_IDS = {67, 68, 69, 70, 71, 176}
        GENERATOR_FUNC_ID = 95
        WATER_HEATER_FUNC_IDS = {3, 4, 107}  # 3=Gas, 4=Electric, 107=Water Tank Heater
        WATER_PUMP_FUNC_ID = 5

        reader: Optional[asyncio.StreamReader] = None
        writer: Optional[asyncio.StreamWriter] = None
        
        lights: dict[str, dict] = {}
        tanks: dict[str, dict] = {}
        water_heaters: dict[str, dict] = {}
        water_pumps: dict[str, dict] = {}
        generators: dict[str, dict] = {}

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
                            func_id = f[8]
                            if func_id <= 0:
                                continue

                            fid_str = str(func_id)
                            name = FUNCTION_NAMES.get(func_id, f"Device {func_id}")
                            
                            if func_id in LIGHT_FUNC_IDS:
                                if fid_str not in lights:
                                    lights[fid_str] = {"name": name}
                                    _LOGGER.debug("Discovered light: %s (func_id=%d)", name, func_id)
                            elif func_id in TANK_FUNC_IDS:
                                if fid_str not in tanks:
                                    tanks[fid_str] = {"name": name}
                                    _LOGGER.debug("Discovered tank: %s (func_id=%d)", name, func_id)
                            elif func_id in WATER_HEATER_FUNC_IDS:
                                if fid_str not in water_heaters:
                                    water_heaters[fid_str] = {"name": name}
                                    _LOGGER.debug("Discovered water heater: %s (func_id=%d)", name, func_id)
                            elif func_id == WATER_PUMP_FUNC_ID:
                                if fid_str not in water_pumps:
                                    water_pumps[fid_str] = {"name": name}
                                    _LOGGER.debug("Discovered water pump: %s (func_id=%d)", name, func_id)
                            elif func_id == GENERATOR_FUNC_ID:
                                if fid_str not in generators:
                                    generators[fid_str] = {"name": name}
                                    _LOGGER.debug("Discovered generator: %s (func_id=%d)", name, func_id)

                except asyncio.TimeoutError:
                    continue

            _LOGGER.info("Discovery complete: %d lights, %d tanks, %d water heaters, %d water pumps, %d generators",
                        len(lights), len(tanks), len(water_heaters), len(water_pumps), len(generators))
            
            return {
                "lights": lights,
                "tanks": tanks,
                "water_heaters": water_heaters,
                "water_pumps": water_pumps,
                "generators": generators,
            }

        except Exception as err:
            _LOGGER.error("Error during device discovery: %s", err)
            return {"lights": {}, "tanks": {}, "water_heaters": {}, "water_pumps": {}, "generators": {}}

        finally:
            if writer:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
