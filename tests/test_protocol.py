"""Tests for OneControl protocol implementation."""
import sys
from pathlib import Path

# Add the onecontrol package directly to avoid homeassistant import
sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components" / "lippert_onecontrol"))
from onecontrol.protocol import (
    crc8_maxim,
    cobs_encode,
    cobs_decode_single,
    decode_frames,
    tea_encrypt,
)


class TestCRC8Maxim:
    """Tests for CRC-8/MAXIM checksum."""

    def test_empty_data(self):
        """Test CRC of empty data."""
        result = crc8_maxim(b"")
        assert result == 0x55  # Init value unchanged

    def test_single_byte(self):
        """Test CRC of single byte."""
        result = crc8_maxim(bytes([0x00]))
        assert isinstance(result, int)
        assert 0 <= result <= 255

    def test_known_frame(self):
        """Test CRC of a known frame from captures."""
        # Frame: 01 06 80 00 (Register command)
        payload = bytes([0x01, 0x06, 0x80, 0x00])
        crc = crc8_maxim(payload)
        assert isinstance(crc, int)
        assert 0 <= crc <= 255

    def test_deterministic(self):
        """Test CRC is deterministic."""
        data = bytes([0x01, 0x02, 0x03, 0x04])
        result1 = crc8_maxim(data)
        result2 = crc8_maxim(data)
        assert result1 == result2

    def test_different_data_different_crc(self):
        """Test different data produces different CRC."""
        crc1 = crc8_maxim(bytes([0x01, 0x02]))
        crc2 = crc8_maxim(bytes([0x01, 0x03]))
        assert crc1 != crc2


class TestCOBSEncode:
    """Tests for COBS encoding."""

    def test_simple_no_zeros(self):
        """Test encoding data with no zeros."""
        payload = bytes([0x01, 0x02, 0x03])
        encoded = cobs_encode(payload)
        # Should start and end with 0x00
        assert encoded[0] == 0x00
        assert encoded[-1] == 0x00

    def test_empty_payload(self):
        """Test encoding empty payload."""
        encoded = cobs_encode(b"")
        assert encoded[0] == 0x00
        assert encoded[-1] == 0x00

    def test_single_byte(self):
        """Test encoding single byte."""
        encoded = cobs_encode(bytes([0x42]))
        assert encoded[0] == 0x00
        assert encoded[-1] == 0x00
        assert len(encoded) >= 3  # delimiter + data + crc + delimiter

    def test_roundtrip(self):
        """Test encode then decode returns original."""
        original = bytes([0x01, 0x06, 0x80, 0x00])
        encoded = cobs_encode(original)
        
        # Decode (remove delimiters)
        inner = encoded[1:-1]
        decoded = cobs_decode_single(inner)
        
        # Should have original + CRC
        assert decoded[:-1] == original
        # CRC should match
        assert decoded[-1] == crc8_maxim(original)


class TestCOBSDecoding:
    """Tests for COBS decoding."""

    def test_simple_decode(self):
        """Test decoding simple data."""
        # Encode first
        payload = bytes([0x01, 0x02, 0x03])
        encoded = cobs_encode(payload)
        inner = encoded[1:-1]
        
        decoded = cobs_decode_single(inner)
        assert decoded[:-1] == payload

    def test_empty_returns_empty(self):
        """Test decoding empty data."""
        result = cobs_decode_single(b"")
        assert result == b""


class TestDecodeFrames:
    """Tests for decoding multiple COBS frames."""

    def test_single_frame(self):
        """Test decoding single frame."""
        payload = bytes([0x01, 0x06, 0x80, 0x00])
        encoded = cobs_encode(payload)
        
        frames = decode_frames(encoded)
        assert len(frames) == 1
        assert frames[0] == payload

    def test_multiple_frames(self):
        """Test decoding multiple frames."""
        p1 = bytes([0x01, 0x06, 0x80, 0x00])
        p2 = bytes([0x08, 0x00, 0x80, 0x00])
        
        data = cobs_encode(p1) + cobs_encode(p2)
        frames = decode_frames(data)
        
        assert len(frames) == 2
        assert frames[0] == p1
        assert frames[1] == p2

    def test_corrupted_frame_skipped(self):
        """Test that corrupted frames are skipped."""
        good_frame = cobs_encode(bytes([0x01, 0x02, 0x03]))
        bad_data = bytes([0x00, 0xFF, 0xFF, 0x00])  # Invalid COBS
        
        frames = decode_frames(good_frame + bad_data)
        # Should only get the good frame
        assert len(frames) >= 1

    def test_empty_data(self):
        """Test decoding empty data."""
        frames = decode_frames(b"")
        assert frames == []


class TestTEAEncrypt:
    """Tests for TEA encryption."""

    def test_deterministic(self):
        """Test encryption is deterministic."""
        seed = 0x12345678
        cypher = 0xB16B00B5
        
        result1 = tea_encrypt(seed, cypher)
        result2 = tea_encrypt(seed, cypher)
        
        assert result1 == result2

    def test_returns_32bit(self):
        """Test result is 32-bit integer."""
        result = tea_encrypt(0x12345678, 0xB16B00B5)
        assert 0 <= result <= 0xFFFFFFFF

    def test_different_seed_different_result(self):
        """Test different seeds produce different results."""
        cypher = 0xB16B00B5
        result1 = tea_encrypt(0x11111111, cypher)
        result2 = tea_encrypt(0x22222222, cypher)
        assert result1 != result2

    def test_known_cypher_constant(self):
        """Test with the known REMOTE_CONTROL_CYPHER constant."""
        REMOTE_CONTROL_CYPHER = 0xB16B00B5
        result = tea_encrypt(0x00000000, REMOTE_CONTROL_CYPHER)
        assert isinstance(result, int)
        assert result != 0  # Encryption should change the value

    def test_zero_seed(self):
        """Test with zero seed."""
        result = tea_encrypt(0x00000000, 0xB16B00B5)
        assert isinstance(result, int)

    def test_max_values(self):
        """Test with maximum 32-bit values."""
        result = tea_encrypt(0xFFFFFFFF, 0xFFFFFFFF)
        assert 0 <= result <= 0xFFFFFFFF


class TestProtocolIntegration:
    """Integration tests for protocol functions."""

    def test_full_frame_cycle(self):
        """Test complete frame encode/decode cycle."""
        # Simulate a register command
        register = bytes([0x01, 0x06, 0x80, 0x00])
        
        # Encode
        encoded = cobs_encode(register)
        
        # Decode
        frames = decode_frames(encoded)
        
        # Verify
        assert len(frames) == 1
        assert frames[0] == register

    def test_identity_frame(self):
        """Test identity frame encoding."""
        # Identity command: 08 00 [session] 00 [uuid...]
        uuid = bytes([0x1c, 0x88, 0x43, 0x4f, 0xaf, 0x67, 0x82])
        identity = bytes([0x08, 0x00, 0x80, 0x00]) + uuid
        
        encoded = cobs_encode(identity)
        frames = decode_frames(encoded)
        
        assert len(frames) == 1
        assert frames[0] == identity

    def test_control_frame(self):
        """Test control frame encoding."""
        # Control command: 00 [protocol] [conn] [counter] [value]
        control = bytes([0x00, 0x80, 0x42, 0x28, 0x01])  # Turn on light 0x28
        
        encoded = cobs_encode(control)
        frames = decode_frames(encoded)
        
        assert len(frames) == 1
        assert frames[0] == control
