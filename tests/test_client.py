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
    OneControlConnectionError,
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

    # An unreachable controller must raise, so the coordinator marks the
    # update failed and entities go unavailable instead of silently "unknown".

    @pytest.mark.asyncio
    async def test_read_all_sensors_connection_failure_raises(self):
        """A refused connection surfaces as OneControlConnectionError."""
        client = OneControlClient("192.168.1.1")

        with patch("asyncio.open_connection", side_effect=ConnectionRefusedError):
            with pytest.raises(OneControlConnectionError):
                await client.read_all_sensors()

    @pytest.mark.asyncio
    async def test_read_all_sensors_timeout_names_the_error(self):
        """A timeout has an empty str(); the raised message must still say what happened."""
        client = OneControlClient("192.168.1.1")

        with patch("asyncio.open_connection", side_effect=asyncio.TimeoutError):
            with pytest.raises(OneControlConnectionError) as excinfo:
                await client.read_all_sensors()

        message = str(excinfo.value)
        assert "TimeoutError" in message
        assert "192.168.1.1:6969" in message

    @pytest.mark.asyncio
    async def test_read_all_sensors_error_includes_os_error_detail(self):
        """An OSError's detail (e.g. host unreachable) is kept in the message."""
        client = OneControlClient("192.168.1.1")

        with patch("asyncio.open_connection", side_effect=OSError(113, "No route to host")):
            with pytest.raises(OneControlConnectionError) as excinfo:
                await client.read_all_sensors()

        assert "No route to host" in str(excinfo.value)


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
