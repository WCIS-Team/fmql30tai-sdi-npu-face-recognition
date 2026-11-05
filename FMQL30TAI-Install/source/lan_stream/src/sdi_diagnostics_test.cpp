#include "wcis_sdi_diagnostics.hpp"
#include <iostream>
#include <stdexcept>
using wcis::SdiReadState;
static void require(bool condition) { if (!condition) throw std::runtime_error("SDI2 reader test failed"); }
int main() {
    unsigned reads=0;
    auto legacy=wcis::read_sdi_diagnostics([&](std::uint64_t addr) {
        ++reads; require(addr==0x40080100); return std::uint32_t(0);
    },0x40080000);
    require(legacy.state==SdiReadState::Unsupported && reads==1);
    std::array<std::uint32_t,13> words{};
    words[0]=0x53444932; words[1]=1; words[3]=8; words[6]=0x801;
    auto stable=wcis::read_sdi_diagnostics([&](std::uint64_t addr) {
        require(addr>=0x40080100 && addr<=0x40080130 && !(addr&3));
        return words[(addr-0x40080100)/4];
    },0x40080000);
    require(stable.state==SdiReadState::Ready && stable.words==words);
    unsigned seq_reads=0;
    auto changed=wcis::read_sdi_diagnostics([&](std::uint64_t addr) {
        if(addr==0x4008010c) return std::uint32_t(++seq_reads);
        return words[(addr-0x40080100)/4];
    },0x40080000);
    require(changed.state==SdiReadState::ChangedDuringRead && seq_reads==9);
    std::cout << "PASS sdi_diagnostics_reader: legacy rejection, stable snapshot, bounded incoherent read rejection; no MMIO\n";
}
