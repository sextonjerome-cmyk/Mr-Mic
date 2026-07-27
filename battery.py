"""Headset battery over the HyperX USB dongle.

Windows only exposes battery for Bluetooth audio, so we ask the dongle
directly with the vendor HID request reverse-engineered by
https://github.com/auto94/HyperX-Cloud-2-Battery-Monitor (MIT):
write [0x66, 0x89] padded to 52 bytes, battery %% comes back in byte 4.
Values > 100 mean the headset is off.
"""

import logging

import hid

log = logging.getLogger("mrmic")

VENDOR_HP = 0x03F0
VENDOR_KINGSTON = 0x0951

WRITE_REQUEST = [0x66, 0x89] + [0x00] * 50  # Cloud II Core / Cloud III
BATTERY_BYTE = 4
READ_SIZE = 20
READ_TIMEOUT_MS = 1000


def _find_path():
    """The dongle exposes several HID interfaces; the battery one is the
    vendor-specific interface with the highest usage page (0xFF13 here)."""
    best = None
    for info in hid.enumerate():
        if info["vendor_id"] not in (VENDOR_HP, VENDOR_KINGSTON):
            continue
        product = info.get("product_string") or ""
        if "Cloud II Core" not in product:
            continue
        if best is None or (info["usage"], info["usage_page"]) > (best["usage"], best["usage_page"]):
            best = info
    return best["path"] if best else None


def read_battery():
    """Battery percent 0-100, or None (dongle absent / headset off / error)."""
    path = _find_path()
    if not path:
        return None
    device = hid.device()
    try:
        device.open_path(path)
        device.write(WRITE_REQUEST)
        data = device.read(READ_SIZE, READ_TIMEOUT_MS)
        if len(data) > BATTERY_BYTE:
            level = data[BATTERY_BYTE]
            if 0 < level <= 100:
                return level
        return None
    except (OSError, ValueError):
        log.debug("battery read failed", exc_info=True)
        return None
    finally:
        try:
            device.close()
        except Exception:
            pass


if __name__ == "__main__":
    print(f"Battery: {read_battery()}%")
