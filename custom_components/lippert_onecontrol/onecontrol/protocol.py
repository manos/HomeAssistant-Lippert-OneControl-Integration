"""Low-level OneControl protocol implementation.

Implements:
- COBS encoding/decoding with CRC-8/MAXIM
- TEA cipher for authentication
- Frame parsing
"""

# Pre-computed CRC-8/MAXIM lookup table (poly=0x8C reflected)
_CRC8_TABLE = [0] * 256
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_c >> 1) ^ 0x8C if _c & 1 else _c >> 1
    _CRC8_TABLE[_i] = _c


def crc8_maxim(data: bytes, init: int = 0x55) -> int:
    """CRC-8/MAXIM (poly=0x8C reflected, init=0x55)."""
    crc = init
    for b in data:
        crc = _CRC8_TABLE[(crc ^ b) & 0xFF]
    return crc


def cobs_encode(payload: bytes) -> bytes:
    """COBS encode with CRC-8."""
    crc = crc8_maxim(payload)
    data = bytes(payload) + bytes([crc])
    out = bytearray()
    i = 0
    while i < len(data):
        code_pos = len(out)
        out.append(0)
        count = 0
        while i < len(data) and data[i] != 0 and count < 63:
            out.append(data[i])
            i += 1
            count += 1
        zeros = 0
        while i < len(data) and data[i] == 0 and zeros < 3:
            i += 1
            zeros += 1
        out[code_pos] = count + (zeros * 64)
    return bytes([0x00]) + bytes(out) + bytes([0x00])


def cobs_decode_single(encoded: bytes) -> bytes:
    """Decode a single COBS block."""
    out = bytearray()
    i = 0
    while i < len(encoded):
        code = encoded[i]
        i += 1
        count = code & 63
        zeros = code >> 6
        for _ in range(count):
            if i < len(encoded):
                out.append(encoded[i])
                i += 1
        for _ in range(zeros):
            out.append(0x00)
    return bytes(out)


def decode_frames(data: bytes) -> list[bytes]:
    """Decode multiple COBS frames from data stream."""
    frames = []
    buf = bytearray()
    for b in data:
        if b == 0:
            if buf:
                try:
                    decoded = cobs_decode_single(bytes(buf))
                    if len(decoded) >= 2:
                        p = decoded[:-1]
                        crc = decoded[-1]
                        if crc == crc8_maxim(p):
                            frames.append(p)
                except Exception:
                    pass
                buf = bytearray()
        else:
            buf.append(b)
    return frames


def tea_encrypt(seed: int, cypher: int) -> int:
    """
    Modified TEA cipher for seed/key authentication.
    
    Constants spell "Copyright IDSsnc" in ASCII.
    """
    K1 = 0x436F7079  # "Copy"
    K2 = 0x72696768  # "righ"
    K3 = 0x74204944  # "t ID"
    K4 = 0x53736E63  # "Ssnc"
    DELTA = 0x9E3779B9
    
    v0, v1 = seed, cypher
    sum_val = DELTA
    
    for _ in range(32):
        v0 = (v0 + (((v1 << 4) + K1) ^ (v1 + sum_val) ^ ((v1 >> 5) + K2))) & 0xFFFFFFFF
        v1 = (v1 + (((v0 << 4) + K3) ^ (v0 + sum_val) ^ ((v0 >> 5) + K4))) & 0xFFFFFFFF
        sum_val = (sum_val + DELTA) & 0xFFFFFFFF
    
    return v0
