"""Decode a reviewed SDI2 snapshot. Offline only: never opens MMIO or SDK.

Rate/family/scan encodings: AMD/Xilinx SMPTE SD/HD/3G-SDI PG071,
tables 3-1/3-2 and RX ports. These describe TRANSPORT, not necessarily picture.
"""
import argparse
import json
from pathlib import Path

RATE = {2: "24000/1001", 3: "24/1", 4: "48000/1001", 5: "25/1",
        6: "30000/1001", 7: "30/1", 8: "48/1", 9: "50/1",
        10: "60000/1001", 11: "60/1"}
FAMILY = {0: [1920, 1080], 1: [1280, 720], 2: [2048, 1080],
          3: [1920, 1080], 8: [720, 486], 9: [720, 576]}


def decode(words):
    if (not isinstance(words, list) or len(words) != 13 or
            any(type(w) is not int or not 0 <= w <= 0xffffffff for w in words)):
        raise ValueError("Expected exactly thirteen uint32 words")
    if words[0] != 0x53444932 or words[1] != 1:
        raise ValueError("Unsupported design: SDI2 v1 is required")
    status, raw = words[2], words[6]
    if status & ~31 or raw & ~4095 or words[12] == 0:
        raise ValueError("Invalid SDI2 reserved bits or CFG frequency")
    fresh = bool(status & 1 and status & 2 and words[5] < words[12] // 10)
    locked = bool(raw & 1) if fresh else None
    mode, family, rate = (raw >> 1) & 3, (raw >> 3) & 15, (raw >> 7) & 15
    result = dict(source="sdi2_snapshot", sequence=words[3], fresh=fresh,
                  snapshot_age_seconds=words[5]/words[12],
                  cfg_tick=words[4], cfg_hz=words[12],
                  snapshot_pending=bool(status & 4),
                  reference_clock_stable=bool(status & 8),
                  gt_reset_released=bool(status & 16),
                  transport_locked=locked, raw_flags=raw,
                  transport_mode=None, transport_geometry=None,
                  transport_frame_rate=None, transport_scan=None,
                  measured_active_geometry=None, rx_cycles=None,
                  frame_boundaries=None, line_starts=None, active_pixels=None)
    if fresh:
        result.update(rx_cycles=words[7], frame_boundaries=words[8],
                      line_starts=words[9], active_pixels=words[10])
    if locked:
        result.update(transport_mode={0: "HD-SDI", 1: "SD-SDI", 2: "3G-SDI"}.get(mode),
                      transport_geometry=FAMILY.get(family),
                      transport_frame_rate=RATE.get(rate),
                      transport_scan="progressive" if raw & 2048 else "interlaced")
        width, height = words[11] & 65535, words[11] >> 16
        if width and height:
            result["measured_active_geometry"] = [width, height]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="JSON list of 13 coherent register words")
    args = parser.parse_args()
    print(json.dumps(decode(json.loads(args.snapshot.read_text(encoding="utf-8-sig"))),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
