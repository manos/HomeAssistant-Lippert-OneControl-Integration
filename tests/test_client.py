"""Tests for OneControl client."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add the onecontrol package directly to avoid homeassistant import
sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components" / "lippert_onecontrol"))
from onecontrol.client import (
    OneControlClient,
    REMOTE_CONTROL_CYPHER,
    DEFAULT_UUID,
    UNIVERSAL_PROTOCOL,
    UNIVERSAL_SESSION,
    UNIVERSAL_CONN,
    UNIVERSAL_DEVICE,
)
from onecontrol.protocol import tea_encrypt


class TestOneControlClientInit:
    """Tests for client initialization."""

    def test_init_default_port(self):
        """Test client initialization with default port."""
        client = OneControlClient("192.168.1.1")
        assert client.host == "192.168.1.1"
        assert client.port == 6969

    def test_init_custom_port(self):
        """Test client initialization with custom port."""
        client = OneControlClient("192.168.1.1", port=1234)
        assert client.host == "192.168.1.1"
        assert client.port == 1234


class TestConstants:
    """Tests for protocol constants."""

    def test_remote_control_cypher(self):
        """Test the REMOTE_CONTROL_CYPHER constant."""
        assert REMOTE_CONTROL_CYPHER == 0xB16B00B5

    def test_default_uuid_length(self):
        """Test DEFAULT_UUID has correct length."""
        assert len(DEFAULT_UUID) == 7

    def test_universal_values(self):
        """Test universal control values."""
        assert UNIVERSAL_PROTOCOL == 0x80
        assert UNIVERSAL_SESSION == 0x80
        assert UNIVERSAL_CONN == 0x40
        assert UNIVERSAL_DEVICE == 0x04


class TestLightControl:
    """Tests for light control methods."""

    @pytest.mark.asyncio
    async def test_light_on_connection_failure(self):
        """Test light_on handles connection failure."""
        client = OneControlClient("192.168.1.1")
        
        with patch("asyncio.open_connection", side_effect=asyncio.TimeoutError):
            result = await client.light_on(0x28)
            assert result is False

    @pytest.mark.asyncio
    async def test_light_off_connection_failure(self):
        """Test light_off handles connection failure."""
        client = OneControlClient("192.168.1.1")
        
        with patch("asyncio.open_connection", side_effect=asyncio.TimeoutError):
            result = await client.light_off(0x28)
            assert result is False

    @pytest.mark.asyncio
    async def test_light_on_no_seed(self):
        """Test light_on fails gracefully when no seed received."""
        client = OneControlClient("192.168.1.1")
        
        mock_reader = AsyncMock()
        mock_writer = MagicMock()
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()
        
        # Return empty data (no seed)
        mock_reader.read = AsyncMock(return_value=b"")
        
        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            with patch("asyncio.wait_for", side_effect=[
                (mock_reader, mock_writer),  # Connection
                b"",  # Initial read
                *[asyncio.TimeoutError() for _ in range(20)]  # Timeouts for seed wait
            ]):
                result = await client.light_on(0x28)
                # Should fail because no seed received
                assert result is False


class TestSensorReading:
    """Tests for read_all_sensors (the unified sensor reader)."""

    # On connection failure, read_all_sensors returns the initial result dict
    # with None/empty values rather than raising.
    EMPTY_RESULT = {
        "tanks": {},
        "battery_voltage": None,
        "generator_hours": None,
        "generator_state": None,
        "relay_states": {},
    }

    @pytest.mark.asyncio
    async def test_read_all_sensors_connection_failure(self):
        """Test read_all_sensors returns defaults on connection failure."""
        client = OneControlClient("192.168.1.1")

        with patch("asyncio.open_connection", side_effect=ConnectionRefusedError):
            result = await client.read_all_sensors()
            assert result == self.EMPTY_RESULT

    @pytest.mark.asyncio
    async def test_read_all_sensors_timeout(self):
        """Test read_all_sensors returns defaults on timeout."""
        client = OneControlClient("192.168.1.1")

        with patch("asyncio.open_connection", side_effect=asyncio.TimeoutError):
            result = await client.read_all_sensors()
            assert result == self.EMPTY_RESULT

    @pytest.mark.asyncio
    async def test_read_all_sensors_accepts_generator_counters(self):
        """Test read_all_sensors accepts optional generator_counters param."""
        client = OneControlClient("192.168.1.1")

        with patch("asyncio.open_connection", side_effect=ConnectionRefusedError):
            result = await client.read_all_sensors(generator_counters=[0x24, 0x43])
            assert result == self.EMPTY_RESULT


class TestTEAAuthentication:
    """Tests for TEA authentication."""

    def test_tea_encrypt_with_remote_control_cypher(self):
        """Test TEA encryption with REMOTE_CONTROL_CYPHER."""
        seed = 0x12345678
        key = tea_encrypt(seed, REMOTE_CONTROL_CYPHER)
        
        # Key should be a 32-bit value
        assert 0 <= key <= 0xFFFFFFFF
        
        # Key should be deterministic
        key2 = tea_encrypt(seed, REMOTE_CONTROL_CYPHER)
        assert key == key2

    def test_tea_encrypt_different_seeds(self):
        """Test different seeds produce different keys."""
        key1 = tea_encrypt(0x11111111, REMOTE_CONTROL_CYPHER)
        key2 = tea_encrypt(0x22222222, REMOTE_CONTROL_CYPHER)
        key3 = tea_encrypt(0x33333333, REMOTE_CONTROL_CYPHER)
        
        # All should be different
        assert len({key1, key2, key3}) == 3
