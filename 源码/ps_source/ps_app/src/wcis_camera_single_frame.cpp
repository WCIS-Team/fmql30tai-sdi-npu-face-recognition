// Bounded maintenance probe. The launcher verifies BOOT and owns both hardware locks.
#include "pipeline/io/input/sdicamera.hpp"
#include "wcis_capture_wait.hpp"
#include "wcis_sdi_diagnostics.hpp"
#include <fstream>
#include <iostream>
#include <sys/file.h>
#include <cstdlib>
int main(int argc,char** argv) {
  if(argc!=3 && argc!=4) {std::cerr<<"Usage: --inspect EXPECTED_BOOT | --capture EXPECTED_BOOT OUTPUT.rgb565\n";return 2;}
  bool capture=std::string(argv[1])=="--capture";
  if((capture && argc!=4)||(!capture && (argc!=3||std::string(argv[1])!="--inspect")))return 2;
  std::string boot;std::ifstream("/proc/sys/kernel/random/boot_id")>>boot;
  if(boot.empty()||boot!=argv[2])return 2;
  // Locks are inherited from the maintenance launcher; direct invocation is forbidden.
  const char* lock1=std::getenv("WCIS_NPU_LOCK_FD");
  const char* lock2=std::getenv("WCIS_CAMERA_LOCK_FD");
  if(!lock1||!lock2)return 2;
  for(auto value:{lock1,lock2}) {
    int fd=std::atoi(value);if(fd<3||fcntl(fd,F_GETFD)<0||flock(fd,LOCK_EX|LOCK_NB))return 2;
  }
  try {
    spdlog::set_level(spdlog::level::warn);
    std::cerr<<"stage=device_open\n"<<std::flush;
    auto device=icraft::xrt::Device::Open("axi://zg330aiu?npu=0x40000000&dma=0x80000000");
    auto fpai=device.cast<fpai::FPAIDevice>();auto regs=fpai.defaultRegRegion();
    constexpr uint64_t base=0x40080000;
    auto read=[&](uint32_t off){return static_cast<uint32_t>(regs.read(base+off));};
    if(read(0x0c)!=0x20230218)throw std::runtime_error("frame controller version mismatch");
    std::cout<<"CAMERA_REGISTERS {";
    bool first=true;
    for(auto off:{0x04,0x08,0x18,0x44,0x50,0x58,0x64,0x68,0x6c,0x70,0x84,0x88,0xb4}) {
      if(!first)std::cout<<",";first=false;
      std::cout<<"\"0x"<<std::hex<<off<<"\":"<<std::dec<<read(off);
    }
    std::cout<<"}\n"<<std::flush;
    bool input_ready=false;
    for(int sample=0;sample<3;++sample) {
      auto diag=wcis::read_sdi_diagnostics([&](uint64_t address){return static_cast<uint32_t>(regs.read(address));},base);
      if(diag.state!=wcis::SdiReadState::Ready)throw std::runtime_error("SDI2 diagnostics unavailable or incoherent");
      std::cout<<"SDI2 [";
      for(unsigned i=0;i<diag.words.size();++i){if(i)std::cout<<",";std::cout<<diag.words[i];}
      std::cout<<"]\n"<<std::flush;
      input_ready=(diag.words[2]&3)==3 && (diag.words[6]&1) && diag.words[11]==((1080u<<16)|1920u);
      if(sample<2)std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    if(!capture)return 0;
    if(!input_ready)throw std::runtime_error("real SDI input not fresh, locked, and 1920x1080; capture not requested");
    if(read(0x04)||read(0x08)||read(0x44)||read(0x70))throw std::runtime_error("camera busy or reset pending");
    auto chunk=fpai.getMemRegion("udma").malloc(1920*1080*2,false);
    auto addr=chunk->begin.addr();
    if(addr%8||addr<0x30100000||addr+1920*1080*2>0x38100000)throw std::runtime_error("unverified DMA allocation");
    fpai::GenericSDICamera camera(0,fpai,1920,1080,camera_fmt::RGB565,1920,1080,
      camera_fmt::RGB565,crop_position::center,640,352,crop_position::center,base,false);
    if(read(0xb4)!=0||(read(0x18)&1)!=1)throw std::runtime_error("real camera source readback failed");
    regs.write(base+0x44,0);regs.write(base+0x08,0);
    std::cerr<<"stage=capture_request vtc=0 width=1920 height=1080\n"<<std::flush;
    camera.take(chunk);
    auto result=wcis::wait_capture([&]{return read(0x58);},[]{return false;},2000,true);
    if(result.state!=wcis::CaptureState::Done) {
      std::cerr<<"CAPTURE_TIMEOUT status="<<result.status<<"; no retry, no buffer reuse\n"<<std::flush;
      std::_Exit(3);
    }
    std::vector<char> pixels(1920*1080*2);chunk.read(pixels.data(),0,pixels.size());
    std::ofstream out(argv[3],std::ios::binary);out.write(pixels.data(),pixels.size());out.close();
    if(!out)throw std::runtime_error("frame output failed");
    std::cout<<"CAPTURE_DONE bytes="<<pixels.size()<<" vtc=0\n"<<std::flush;
    return 0;
  }catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 2;}
}
