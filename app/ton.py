import base64
import re

_RAW = re.compile(r"^-?\d+:[0-9a-fA-F]{64}$")


def _crc16(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


def valid_address(addr: str) -> bool:
    """Проверка TON-адреса: raw (0:abc…) или user-friendly (UQ…/EQ…) с контрольной суммой."""
    addr = addr.strip()
    if _RAW.match(addr):
        return True
    if len(addr) != 48:
        return False
    try:
        raw = base64.urlsafe_b64decode(addr.replace("+", "-").replace("/", "_"))
    except Exception:
        return False
    if len(raw) != 36 or (raw[0] & 0x3F) != 0x11:  # bounceable/non-bounceable (+testnet-флаг)
        return False
    return _crc16(raw[:34]) == int.from_bytes(raw[34:], "big")
