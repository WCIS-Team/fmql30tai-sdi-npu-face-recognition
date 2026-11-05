// CPU-only command process; preserves the frame lease, never an open device.
#include "frame_lease.h"
#include <chrono>
#include <filesystem>
#include <iostream>
#include <optional>
#include <thread>
#include <vector>
using namespace icraft::xrt;
using Json=nlohmann::json;
namespace fs=std::filesystem;
using Clock=std::chrono::steady_clock;
static constexpr uint32_t REG=0x400c2000,ID=0x46414331;
static double ms(Clock::time_point t){return std::chrono::duration<double,std::milli>(Clock::now()-t).count();}
static void emit(const Json& value){std::cout<<"\nWCIS_PL_RESULT "<<value.dump()<<std::endl;}
[[noreturn]] static void fault(const fs::path& path,const std::string& message){
 std::ofstream file(path);file<<Json{{"boot_id",frame_lease::boot_id()},{"source","retained_frame"},{"message",message},{"automatic_retry",false}}.dump(2)<<std::endl;
 std::cerr<<message<<std::endl;std::_Exit(3);
}
struct State {frame_lease::Lease lease;fs::path input,marker;uint64_t runs=0;};
static void checked_firmware(const Device& device){auto regs=device.defaultRegRegion();if(regs.read(REG,false)!=ID||(regs.read(REG+4,false)&1))throw std::runtime_error("FAC1 absent or busy");}
static void quarantine_check(const fs::path& marker){
 if(fs::exists(marker)){std::ifstream f(marker);Json old;f>>old;if(old.value("boot_id","")==frame_lease::boot_id())throw std::runtime_error("Hardware quarantined in current boot");}
}
static Json run_transform(State& state,const Device& device,const MemChunk& memory,const Json& q,bool uploaded){
 const auto start=Clock::now();const auto& lease=state.lease;
 const uint64_t cw=frame_lease::number(q,"content_w"),ch=frame_lease::number(q,"content_h"),dw=frame_lease::number(q,"canvas_w"),dh=frame_lease::number(q,"canvas_h");
 if(!cw||!ch||!dw||!dh||cw>dw||ch>dh||dw>640||dh>640)throw std::runtime_error("Invalid retained output dimensions");
 const uint64_t output_bytes=dw*dh*4;if(output_bytes>frame_lease::OUTPUT_CAPACITY)throw std::runtime_error("Output outside retained scratch");
 if(q.at("inverse_q16").size()!=6)throw std::runtime_error("Invalid affine coefficients");
 std::vector<uint32_t> words={lease.id,static_cast<uint32_t>(lease.source_address()),static_cast<uint32_t>(lease.pitch),static_cast<uint32_t>(lease.output_address()),
  static_cast<uint32_t>((lease.h<<16)|lease.w),static_cast<uint32_t>((ch<<16)|cw),static_cast<uint32_t>((dh<<16)|dw),
  (lease.rgb565?2u:0u)|(q.value("replicate",false)?1u:0u),q.value("border",0u)};
 for(const auto& v:q.at("inverse_q16")){
  if(!v.is_number_integer())throw std::runtime_error("Noninteger affine coefficient");
  const auto n=v.get<int64_t>();
  if(n<INT32_MIN||n>INT32_MAX)throw std::runtime_error("Affine coefficient outside int32");
  words.push_back(static_cast<uint32_t>(n));
 }
 const fs::path output=q.at("output_rgbx").get<std::string>();if(fs::exists(output))throw std::runtime_error("Output already exists");
 std::vector<char> pixels(output_bytes,static_cast<char>(0xa5));
 // Subsequent transforms initialize only their output, never upload source again.
 if(!uploaded)memory.write(lease.output_offset,pixels.data(),pixels.size());
 auto regs=device.defaultRegRegion();for(size_t i=0;i<words.size();i++)regs.write(REG+0x10+i*4,words[i],false);
 for(size_t i=0;i<words.size();i++)if(regs.read(REG+0x10+i*4,false)!=words[i])throw std::runtime_error("Descriptor readback mismatch");
 const auto execution=Clock::now();
 try{
  regs.write(REG,1,false);uint32_t status=0;
  do{status=regs.read(REG+4,false);if(ms(execution)>10000)fault(state.marker,"Retained frame PL deadline exceeded");if(!(status&2))std::this_thread::sleep_for(std::chrono::microseconds(100));}while(!(status&2));
  if((status&1)||((status>>4)&15)||(status&8)||regs.read(REG+8,false)!=lease.id||regs.read(REG+12,false)!=dw*dh)throw std::runtime_error("Invalid retained frame completion");
  memory.read(pixels.data(),lease.output_offset,output_bytes);
  for(size_t i=3;i<output_bytes;i+=4)if(pixels[i]!=0)throw std::runtime_error("Retained frame output canary remains");
  std::ofstream f(output,std::ios::binary);f.write(pixels.data(),pixels.size());f.close();if(!f)throw std::runtime_error("Cannot write retained output");
 }catch(const std::exception& e){fault(state.marker,e.what());}
 ++state.runs;
 return {{"status","preprocessed"},{"frame_id",lease.id},{"frame_token",lease.token},{"frame_lease",lease.json()},
  {"pixels",dw*dh},{"source_uploads",1},{"source_upload_bytes",lease.source_bytes},{"source_uploaded_this_command",uploaded},
  {"ddr_frame_reused",!uploaded},{"pl_and_readback_ms",ms(execution)},{"transform_ms",ms(start)},
  {"backend","FAC1_customop_PL"},{"normalization_in_PL",false},{"device_closed",false}};
}
int main(int argc,char** argv){
 if(argc==2&&std::string(argv[1])=="--help"){std::cout<<"wcis_face_pl_retained --serve; caller holds the full request hardware lock. CPU-only startup; one bounded lease.\n";return 0;}
 if(argc!=2||std::string(argv[1])!="--serve")return 2;
 std::optional<State> state;
 try{
  emit({{"status","ready"},{"frame_leases",true},{"device_opened",false},{"boot_id",frame_lease::boot_id()}});
  std::string line;
  while(std::getline(std::cin,line)){
   const auto started=Clock::now();if(line.size()>65536)throw std::runtime_error("Oversize frame command");
   const auto q=Json::parse(line);const auto op=q.at("op").get<std::string>();
   if(op=="release"){
    if(!state||q.at("frame_token")!=state->lease.token||q.at("frame_id")!=state->lease.id)throw std::runtime_error("Release belongs to another frame");
    emit({{"status","released"},{"frame_id",state->lease.id},{"frame_token",state->lease.token},{"source_uploads",1},{"device_opened",false}});state.reset();continue;
   }
   if(op!="begin"&&op!="transform"&&op!="verify")throw std::runtime_error("Unknown frame command");
   if(op=="begin"){
    if(state)throw std::runtime_error("Previous frame still leased");
    State fresh{};fresh.input=q.at("input_rgbx").get<std::string>();fresh.marker=q.at("fault_marker").get<std::string>();quarantine_check(fresh.marker);
    const auto w=frame_lease::number(q,"src_w"),h=frame_lease::number(q,"src_h"),pitch=frame_lease::number(q,"pitch_bytes");
    if(!w||!h||w>8192||h>8192||pitch%8||pitch<w*(q.value("rgb565",false)?2:4)||pitch>65536)throw std::runtime_error("Invalid source geometry");
    const auto source_bytes=pitch*h,total=128+frame_lease::aligned(source_bytes)+frame_lease::OUTPUT_CAPACITY;
    if(total>frame_lease::MAX_BYTES||fs::file_size(fresh.input)!=source_bytes)throw std::runtime_error("Invalid bounded source allocation");
    std::vector<char> data(total,static_cast<char>(0xa5));std::ifstream input(fresh.input,std::ios::binary);input.read(data.data()+64,source_bytes);if(!input)throw std::runtime_error("Incomplete source read");
    auto device=Device::Open("axi://zg330aiu?npu=0x40000000&dma=0x80000000");checked_firmware(device);Json result;
    {
     auto memory=device.defaultMemRegion().malloc(total,true,64);
     Json description={{"schema_version",1},{"allocation_base",memory->begin.addr()},{"allocation_bytes",total},{"src_w",w},{"src_h",h},{"pitch_bytes",pitch},
      {"frame_id",q.at("frame_id")},{"frame_token",q.at("frame_token")},{"boot_id",frame_lease::boot_id()},{"rgb565",q.value("rgb565",false)}};
     fresh.lease=frame_lease::Lease::parse(description);const auto head=fresh.lease.guard(),tail=fresh.lease.guard(true);
     std::copy(head.begin(),head.end(),data.begin());std::copy(tail.begin(),tail.end(),data.begin()+fresh.lease.guard_offset);
     memory.write(0,data.data(),total);state=std::move(fresh);result=run_transform(*state,device,memory,q,true);
    }
    Device::Close(device);result["device_closed"]=true;result["worker_wall_ms"]=ms(started);emit(result);
   }else{
    if(!state||q.at("frame_id")!=state->lease.id||q.at("frame_token")!=state->lease.token)throw std::runtime_error("Command belongs to another frame");
    quarantine_check(state->marker);auto device=Device::Open("axi://zg330aiu?npu=0x40000000&dma=0x80000000");checked_firmware(device);Json result;
    {
     frame_lease::Reservation held(device,state->lease);
     if(op=="verify"){
      std::vector<char> expected(state->lease.source_bytes),actual(expected.size());std::ifstream input(state->input,std::ios::binary);input.read(expected.data(),expected.size());if(!input)throw std::runtime_error("Cannot read verification source");
      held.chunk.read(actual.data(),64,actual.size());if(actual!=expected)fault(state->marker,"Retained full source differs after device handoff");
      result={{"status","verified"},{"frame_id",state->lease.id},{"frame_token",state->lease.token},{"source_uploads",1},{"full_source_equal",true}};
     }else result=run_transform(*state,device,held.chunk,q,false);
     held.check();
    }
    Device::Close(device);result["device_closed"]=true;result["worker_wall_ms"]=ms(started);emit(result);
   }
  }
  return 0;
 }catch(const std::exception& e){emit({{"status","error"},{"message",e.what()}});return 2;}
}
