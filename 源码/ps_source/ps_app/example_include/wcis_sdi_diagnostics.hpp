#pragma once
#include <array>
#include <cstdint>
#include <stdexcept>

namespace wcis {
// Caller MUST first validate the loaded design and existing register bridge.
// This helper does not authorize MMIO and must not be used to probe an unknown
// bitstream. The factory image has no SDI2 block; its result is Unsupported.
enum class SdiReadState { Ready, Unsupported, ChangedDuringRead };
struct SdiDiagnosticRead {
    SdiReadState state;
    std::array<std::uint32_t,13> words{};
};
template<class ReadRegister>
SdiDiagnosticRead read_sdi_diagnostics(ReadRegister read, std::uint64_t camera_base) {
    if (read(camera_base+0x100) != 0x53444932 || read(camera_base+0x104) != 1)
        return {SdiReadState::Unsupported,{}};
    for (int attempt=0; attempt<3; ++attempt) {
        SdiDiagnosticRead result{SdiReadState::Ready,{}};
        const auto before = read(camera_base+0x10c);
        for (unsigned i=0; i<result.words.size(); ++i)
            result.words[i] = read(camera_base+0x100+4*i);
        const auto after = read(camera_base+0x10c);
        if (before==after && result.words[3]==before &&
            result.words[0]==0x53444932 && result.words[1]==1)
            return result;
    }
    return {SdiReadState::ChangedDuringRead,{}};
}
}
