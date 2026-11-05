// CPU-only JPG1 client between commands. Caller owns the common npu.lock.
// Reuse the FAC1 lease without reupload; reserve it before all SDK allocations.
#include "frame_lease.h"
#include <chrono>
#include <filesystem>
#include <iostream>
#include <thread>
#include <vector>
#include <fcntl.h>
#include <unistd.h>
using namespace icraft::xrt;
using Json=nlohmann::json;
namespace fs=std::filesystem;
using Clock=std::chrono::steady_clock;
static constexpr uint32_t REG=0x400c2100,ID=0x4a504731;
static constexpr uint64_t CAPACITY=8ull*1024*1024,TOTAL=CAPACITY+128;
static double ms(Clock::time_point t){return std::chrono::duration<double,std::milli>(Clock::now()-t).count();}
static void emit(const Json& q){std::cout<<"\nWCIS_LEASED_JPEG_RESULT "<<q.dump()<<std::endl;}
static void quarantine_check(const fs::path& marker){
 if(fs::exists(marker)){std::ifstream f(marker);Json old;f>>old;if(old.value("boot_id","")==frame_lease::boot_id())throw std::runtime_error("Current boot quarantined");}
}
[[noreturn]] static void fault(const fs::path& marker,const std::string& message){
 std::ofstream f(marker);f<<Json{{"boot_id",frame_lease::boot_id()},{"source","JPG1_lease"},{"message",message},{"automatic_retry",false}}.dump(2)<<std::endl;
 std::cerr<<message<<std::endl;std::_Exit(3);
}
static bool valid_sha(const std::string& s){
 if(s.size()!=64)return false;
 for(char c:s)if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))return false;
 return true;
}
static Json compress(const Json& q){
 const auto started=Clock::now();
 const auto lease=frame_lease::Lease::parse(q.at("retained_frame"));
 if(lease.w!=1920||lease.h!=1080||lease.pitch!=1920*(lease.rgb565?2:4))
  throw std::runtime_error("JPG1 requires tightly packed native 1920x1080 lease");
 const auto pts=frame_lease::number(q,"pts_us");
 const std::string digest=q.at("source_sha256").get<std::string>();
 if(!valid_sha(digest))throw std::runtime_error("Missing source digest binding");
 const fs::path marker=q.at("fault_marker").get<std::string>();quarantine_check(marker);
 const fs::path output=q.at("output_jpeg").get<std::string>();
 // Reserve the file before hardware access. O_EXCL prevents replacing a record.
 const int fd=::open(output.c_str(),O_WRONLY|O_CREAT|O_EXCL,0600);
 if(fd<0)throw std::runtime_error("JPEG output exists or cannot be created");
 bool hardware_started=false;
 try{
  Json result;const auto open_start=Clock::now();
  auto device=Device::Open("axi://zg330aiu?npu=0x40000000&dma=0x80000000");
  const double open_ms=ms(open_start);
  {
   auto regs=device.defaultRegRegion();
   if(regs.read(REG,false)!=ID||(regs.read(REG+4,false)&1)||
      regs.read(REG+36,false)!=1920||regs.read(REG+40,false)!=1080)
    throw std::runtime_error("JPG1 absent, busy or incompatible");
   // Reservation is deliberately BEFORE the output allocation.
   frame_lease::Reservation held(device,lease);
   auto memory=device.defaultMemRegion().malloc(TOTAL,true,64);
   const uint64_t base=memory->begin.addr();
   if(base%64||base>=frame_lease::WINDOW||TOTAL>frame_lease::WINDOW-base)
    throw std::runtime_error("JPEG output outside verified window");
   held.check();
   std::vector<char> guard(64,static_cast<char>(0xa5));
   memory.write(0,guard.data(),64);memory.write(TOTAL-64,guard.data(),64);
   const std::vector<uint32_t> words={lease.id,static_cast<uint32_t>(lease.source_address()),
    static_cast<uint32_t>(base+64),static_cast<uint32_t>(CAPACITY),lease.rgb565?0u:1u};
   for(size_t i=0;i<words.size();++i)regs.write(REG+16+i*4,words[i],false);
   for(size_t i=0;i<words.size();++i)if(regs.read(REG+16+i*4,false)!=words[i])throw std::runtime_error("JPG1 descriptor mismatch");
   const auto execution=Clock::now();hardware_started=true;
   regs.write(REG,1,false);uint32_t status=0;
   do{
    status=regs.read(REG+4,false);
    if(ms(execution)>10000)fault(marker,"JPG1 lease DMA deadline exceeded");
    if(!(status&2))std::this_thread::sleep_for(std::chrono::microseconds(100));
   }while(!(status&2));
   if((status&1)||((status>>4)&15)||(status&8)||regs.read(REG+8,false)!=lease.id)
    fault(marker,"JPG1 lease completion/frame mismatch");
   const double execution_ms=ms(execution);
   const uint32_t bytes=regs.read(REG+12,false),cycles=regs.read(REG+48,false);
   if(bytes<100||bytes>CAPACITY||!cycles)fault(marker,"Invalid leased JPEG size/cycles");
   std::vector<char> jpeg(frame_lease::aligned(bytes));
   const auto read_start=Clock::now();memory.read(jpeg.data(),64,jpeg.size());
   const double read_ms=ms(read_start);
   if(static_cast<unsigned char>(jpeg[0])!=255||static_cast<unsigned char>(jpeg[1])!=216||
      static_cast<unsigned char>(jpeg[bytes-2])!=255||static_cast<unsigned char>(jpeg[bytes-1])!=217)
    fault(marker,"Leased JPEG SOI/EOI absent");
   for(uint64_t offset:std::vector<uint64_t>{0,TOTAL-64}){
    std::vector<char> actual(64);memory.read(actual.data(),offset,64);
    if(actual!=guard)fault(marker,"JPEG output guard changed");
   }
   held.check();
   const auto write_start=Clock::now();
   size_t written=0;
   while(written<bytes){const auto n=::write(fd,jpeg.data()+written,bytes-written);if(n<=0)throw std::runtime_error("JPEG file write failed");written+=static_cast<size_t>(n);}
   if(::fsync(fd)!=0)throw std::runtime_error("JPEG fsync failed");
   result={{"status","compressed"},{"backend","JPG1_FPGA"},{"frame_id",lease.id},{"frame_token",lease.token},
    {"pts_us",pts},{"source_sha256",digest},{"source_uploaded",false},{"frame_preserved",true},
    {"allocation_base",base},{"allocation_bytes",TOTAL},{"lease_reserved_bytes",lease.bytes},
    {"jpeg_bytes",bytes},{"output_jpeg",output.string()},{"quality",regs.read(REG+44,false)},
    {"read_blocks",regs.read(REG+64,false)},{"write_blocks",regs.read(REG+68,false)},
    {"hw_cycles",cycles},{"device_open_ms",open_ms},{"pl_and_poll_ms",execution_ms},
    {"readback_ms",read_ms},{"write_and_fsync_ms",ms(write_start)}};
  }
  Device::Close(device);::close(fd);
  result["device_closed"]=true;result["worker_ms"]=ms(started);return result;
 }catch(const std::exception& e){
  ::close(fd);
  if(hardware_started)fault(marker,e.what());
  throw;
 }
}
int main(int argc,char** argv){
 if(argc==2&&std::string(argv[1])=="--help"){
  std::cout<<"wcis_jpeg_leased --serve; CPU-only idle, per-command SDK ownership, FAC1 lease required. Caller holds npu.lock.\n";return 0;
 }
 if(argc!=2||std::string(argv[1])!="--serve")return 2;
 try{
  emit({{"status","ready"},{"device_opened",false},{"frame_leases",true},{"boot_id",frame_lease::boot_id()}});
  std::string line;
  while(std::getline(std::cin,line)){
   if(line.size()>65536)throw std::runtime_error("Oversize JPEG command");
   const auto q=Json::parse(line);
   if(q.at("op")=="finish"){emit({{"status","closed"},{"device_closed",true}});return 0;}
   if(q.at("op")!="frame")throw std::runtime_error("Unknown JPEG lease command");
   emit(compress(q));
  }
  return 0;
 }catch(const std::exception& e){emit({{"status","error"},{"message",e.what()},{"automatic_retry",false}});return 2;}
}
