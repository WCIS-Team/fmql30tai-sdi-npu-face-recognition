#pragma once
#include <chrono>
#include <cstdint>
#include <thread>

namespace wcis {
enum class VisionMode : std::uint32_t { Bypass = 1, Standby = 2, Active = 3 };
enum class RateResult { Applied, UnsupportedBitstream, BusyTimeout, Rejected, FrameTimeout };

// Device exposes the existing iCraft defaultRegRegion().read/write methods.
// Call from the sole owner of the camera/NPU session; no new /dev/mem mapping.
template<class Device>
RateResult set_vision_mode(Device& device, VisionMode mode,
                          std::uint64_t camera_base = 0x40080000,
                          std::chrono::milliseconds timeout = std::chrono::milliseconds(1500)) {
    auto region = device.defaultRegRegion();
    if (region.read(camera_base + 0xc0) != 0x57434953u)
        return RateResult::UnsupportedBitstream;
    const auto until = std::chrono::steady_clock::now() + timeout;
    while (region.read(camera_base + 0xbc) & 8u) {
        if (std::chrono::steady_clock::now() >= until) return RateResult::BusyTimeout;
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    const auto word = static_cast<std::uint32_t>(mode);
    region.write(camera_base + 0xb8, word);
    if ((region.read(camera_base + 0xb8) & 7u) != word) return RateResult::Rejected;
    do {
        const auto status = region.read(camera_base + 0xbc);
        if (!(status & 8u) && (status & 3u) == word) return RateResult::Applied;
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    } while (std::chrono::steady_clock::now() < until);
    return RateResult::FrameTimeout;
}
} // namespace wcis
