#pragma once
#include <chrono>
#include <cstdint>
#include <thread>
namespace wcis {
enum class CaptureState { Done, Error, Timeout, Interrupted };
struct CaptureResult { CaptureState state; uint32_t status; };
// Vendor SDICamera::wait can reset forever after an error. This preview never resets.
template<class ReadStatus, class Stop>
CaptureResult wait_capture(ReadStatus read, Stop stop, int timeout_ms, bool require_idle = false) {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout_ms);
    uint32_t status = 0;
    bool observed_idle = !require_idle;
    while (!stop()) {
        status = read();
        if (status & 4) return {CaptureState::Error, status};
        if (!(status & 1)) observed_idle = true;
        else if (observed_idle) return {CaptureState::Done, status};
        if (std::chrono::steady_clock::now() >= deadline) return {CaptureState::Timeout, status};
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    return {CaptureState::Interrupted, status};
}
}
