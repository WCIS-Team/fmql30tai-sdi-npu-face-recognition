#pragma once
// A CPU-side frame lease spans sequential SDK opens. No SDK handle survives
// Device::Close. Every hardware owner first reserves the exact SDK-chosen range.
#include <icraft-xrt/dev/zg330_device.h>
#include <nlohmann/json.hpp>
#include <array>
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <stdexcept>
#include <string>
namespace frame_lease {
using Json=nlohmann::json;
using namespace icraft::xrt;
static constexpr uint64_t WINDOW=0x08000000,MAX_BYTES=64*1024*1024;
static constexpr uint64_t OUTPUT_CAPACITY=640*640*4,GUARD_BYTES=64;
inline uint64_t aligned(uint64_t n){return (n+63)&~uint64_t(63);}
inline std::string boot_id(){std::ifstream f("/proc/sys/kernel/random/boot_id");std::string value;std::getline(f,value);if(value.empty())throw std::runtime_error("No boot identity");return value;}
inline uint64_t number(const Json& q,const char* key){
 const auto& v=q.at(key);if(!v.is_number_integer()||v.get<int64_t>()<0)throw std::runtime_error("Invalid frame integer");return v.get<uint64_t>();
}
inline bool valid_token(const std::string& token){
 if(token.size()!=32)return false;
 for(char c:token)if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))return false;
 return true;
}
struct Lease {
 uint64_t base,bytes,source_bytes,output_offset,guard_offset,w,h,pitch;
 uint32_t id;bool rgb565;std::string token,boot;
 static Lease parse(const Json& q){
  if(q.at("schema_version")!=1)throw std::runtime_error("Unknown frame lease schema");
  Lease a{};a.base=number(q,"allocation_base");a.bytes=number(q,"allocation_bytes");
  a.w=number(q,"src_w");a.h=number(q,"src_h");a.pitch=number(q,"pitch_bytes");
  const auto id=number(q,"frame_id");if(!id||id>0xffffffffULL)throw std::runtime_error("Invalid frame ID");a.id=static_cast<uint32_t>(id);
  a.token=q.at("frame_token").get<std::string>();a.boot=q.at("boot_id").get<std::string>();a.rgb565=q.at("rgb565").get<bool>();
  if(!valid_token(a.token)||a.boot!=boot_id())throw std::runtime_error("Stale/invalid frame lease identity");
  if(!a.w||!a.h||a.w>8192||a.h>8192||a.pitch%8||a.pitch<a.w*(a.rgb565?2:4)||a.pitch>65536)throw std::runtime_error("Invalid retained frame geometry");
  a.source_bytes=a.pitch*a.h;a.output_offset=64+aligned(a.source_bytes);a.guard_offset=a.output_offset+OUTPUT_CAPACITY;
  if(a.bytes!=a.guard_offset+64||a.base%64||a.bytes>MAX_BYTES||a.base>=WINDOW||a.bytes>WINDOW-a.base)throw std::runtime_error("Frame outside allocated FAC1 window");
  return a;
 }
 Json json() const{return {{"schema_version",1},{"allocation_base",base},{"allocation_bytes",bytes},{"src_w",w},{"src_h",h},{"pitch_bytes",pitch},{"frame_id",id},{"frame_token",token},{"boot_id",boot},{"rgb565",rgb565}};}
 std::array<char,64> guard(bool tail=false)const{
  std::array<char,64> g{};const std::string magic="FAC1_FRAME_V1";std::copy(magic.begin(),magic.end(),g.begin());
  std::copy(token.begin(),token.end(),g.begin()+16);
  const uint32_t fields[]={id,static_cast<uint32_t>(w),static_cast<uint32_t>(h),static_cast<uint32_t>(pitch)};
  for(size_t i=0;i<4;i++)for(size_t b=0;b<4;b++)g[48+i*4+b]=static_cast<char>(fields[i]>>(b*8));
  if(tail)for(char& v:g)v=static_cast<char>(static_cast<unsigned char>(v)^0x5a);
  return g;
 }
 uint64_t source_address()const{return base+64;}
 uint64_t output_address()const{return base+output_offset;}
};
class Reservation {
public:
 Lease lease;MemChunk chunk;
 Reservation(const Device& device,const Lease& value):lease(value),chunk(device.defaultMemRegion().malloc(MemPtr(value.base),value.bytes,nullptr,true)){
  if(chunk->begin.addr()!=value.base||chunk->byte_size!=value.bytes)throw std::runtime_error("SDK did not reserve exact frame interval");
  check();
 }
 void check()const{
  std::array<char,64> head{},tail{};chunk.read(head.data(),0,64);chunk.read(tail.data(),lease.guard_offset,64);
  if(head!=lease.guard()||tail!=lease.guard(true))throw std::runtime_error("Retained frame guard mismatch");
  for(const auto& other:chunk->region.memManager().getAllMemChunk()){
   const auto base=other->begin.addr(),bytes=other->byte_size;
   if(base==lease.base&&bytes==lease.bytes)continue;
   if(base<lease.base+lease.bytes&&lease.base<base+bytes)throw std::runtime_error("NPU allocation overlaps retained frame");
  }
 }
};
}
