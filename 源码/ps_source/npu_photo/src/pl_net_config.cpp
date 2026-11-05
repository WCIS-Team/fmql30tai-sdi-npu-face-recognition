// Bounded NTP2 TX-only configuration. No camera requests, pixel DMA or model load.
// Caller first admits the candidate BOOT and normally closes the SDK owner.
#include "frame_lease.h"
#include <arpa/inet.h>
#include <chrono>
#include <filesystem>
#include <fcntl.h>
#include <iostream>
#include <optional>
#include <sys/file.h>
#include <thread>
#include <unistd.h>
#include <vector>
using namespace icraft::xrt;
using Json=nlohmann::json;namespace fs=std::filesystem;
static constexpr uint64_t NET=0x400c2200;
static double now(){return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();}
static void pause_us(unsigned us){std::this_thread::sleep_for(std::chrono::microseconds(us));}
static Json load(const fs::path& p){std::ifstream f(p);Json q;f>>q;return q;}
static uint32_t ip(const Json& q,const char* key){in_addr a{};const auto s=q.at(key).get<std::string>();if(inet_pton(AF_INET,s.c_str(),&a)!=1)throw std::runtime_error("Invalid IPv4 setting");return ntohl(a.s_addr);}
static uint32_t number(const Json& q,const char* key,uint32_t maximum=0xffffffffu){const auto n=frame_lease::number(q,key);if(n>maximum)throw std::runtime_error("Setting outside uint32 bounds");return n;}
int main(int argc,char** argv){
 std::optional<Device> device;bool admitted=false;Json report;
 try{
  if(argc!=2)throw std::runtime_error("Expected one admission/config JSON path");
  const auto q=load(argv[1]);const auto boot=frame_lease::boot_id();const auto mode=q.at("mode").get<std::string>();
  if(mode!="inspect"&&mode!="disable"&&mode!="enable")throw std::runtime_error("Unknown mode");
  if(q.at("boot_id")!=boot)throw std::runtime_error("Stale configuration boot");
  const auto proof=load("/root/wcis-face/candidates/face-camera-ready-20261020/live/boot-proof.json");
  if(proof.at("boot_id")!=boot||proof.at("boot_files").at("BOOT.bin")!=q.at("boot_sha256"))throw std::runtime_error("Candidate startup admission missing");
  const fs::path marker="/root/wcis-face/hardware-review-required.json";
  if(fs::exists(marker)&&load(marker).value("boot_id","")==boot)throw std::runtime_error("Hardware review required");
  for(const char* name:{"WCIS_NPU_LOCK_FD","WCIS_CAMERA_LOCK_FD"}){
   const char* value=getenv(name);if(!value)throw std::runtime_error("Missing inherited hardware lock");
   const int fd=std::stoi(value);if(fd<3||fcntl(fd,F_GETFD)<0||flock(fd,LOCK_EX|LOCK_NB))throw std::runtime_error("Hardware ownership is not exclusive");
  }
  // Validate all deployment settings before opening the device.
  uint32_t session=0,local=0,destination=0;uint64_t mac=0,next_hop=0;uint16_t sport=0,dport=0;
  if(mode=="enable"){
   session=number(q,"session");local=ip(q,"local_ip");destination=ip(q,"destination_ip");
   next_hop=frame_lease::number(q,"next_hop_mac");
   mac=frame_lease::number(q,"mac");sport=number(q,"source_port",65535);dport=number(q,"destination_port",65535);
   if(!session||!local||!destination||!sport||!dport||!mac||mac>0xffffffffffffull||(mac&(1ull<<40)))throw std::runtime_error("Invalid unicast deployment settings");
   if(!next_hop||next_hop>0xffffffffffffull||(next_hop&(1ull<<40)))throw std::runtime_error("Explicit unicast next-hop MAC required");
  }
  device=Device::Open("axi://zg330aiu?npu=0x40000000&dma=0x80000000");auto r=device->defaultRegRegion();
  if(r.read(NET,false)!=0x4e545032||r.read(NET+0x5c,false)!=7||r.read(NET+0x54,false)!=1920||r.read(NET+0x58,false)!=1080)throw std::runtime_error("NTP2 TX-only firmware/capability/geometry mismatch");
  admitted=true;report={{"boot_id",boot},{"mode",mode},{"pixel_dma",false},{"models_loaded",false},{"automatic_retry",false}};
  auto write=[&](unsigned off,uint32_t value){r.write(NET+off,value,false);};
  auto read=[&](unsigned off){return static_cast<uint32_t>(r.read(NET+off,false));};
  auto status=[&](){return Json{{"enable",read(4)},{"status",read(8)},{"session",read(12)},
   {"rejected_writes",read(0x2c)},{"jpeg_frames",read(0x40)},{"rejected_frames",read(0x44)},
   {"udp_frames",read(0x48)},{"aborted_frames",read(0x4c)},{"udp_packets",read(0x50)}};};
  report["before"]=status();
  if(mode!="inspect"){
   write(4,0);if(read(4)!=0)throw std::runtime_error("Could not disable NTP2");pause_us(1000);
  }
  if(mode=="enable"){
   write(0x38,0);pause_us(20000);write(0x38,1);pause_us(50000);
   auto mdio=[&](bool reading,unsigned phy,unsigned reg,uint16_t data,bool absent_ok=false)->std::optional<uint16_t>{
    if(read(0x34)&0x10000)throw std::runtime_error("MDIO is already busy");
    write(0x30,(reading?0x40000000u:0)|(phy<<21)|(reg<<16)|data);
    const auto deadline=now()+.1;uint32_t s;
    do{s=read(0x34);if(now()>deadline)throw std::runtime_error("MDIO deadline");if((s&0x10000)||!(s&0x20000))pause_us(10);}while((s&0x10000)||!(s&0x20000));
    if(s&0x40000){if(absent_ok)return {};throw std::runtime_error("PHY read turnaround failed");}
    return static_cast<uint16_t>(s);
   };
   unsigned phy=32;uint32_t identity=0;
   for(unsigned address=0;address<32;++address){
    auto high=mdio(true,address,2,0,true);if(!high)continue;
    auto low=mdio(true,address,3,0,true);if(!low)continue;
    const uint32_t id=(uint32_t(*high)<<16)|*low;
    if(id==0x0000011a){if(phy!=32)throw std::runtime_error("Multiple YT8521 PHYs");phy=address;identity=id;}
   }
   if(phy==32)throw std::runtime_error("Expected YT8521 PHY not found");
   auto ext_read=[&](uint16_t address){mdio(false,phy,0x1e,address);return *mdio(true,phy,0x1f,0);};
   auto ext_write=[&](uint16_t address,uint16_t value){mdio(false,phy,0x1e,address);mdio(false,phy,0x1f,value);};
   const auto chip=ext_read(0xa001),delay=ext_read(0xa003);
   // The existing eMMC and the RGMII data pins share the verified 1.8 V bank.
   // Do not change PHY LDO/voltage straps or guess a different interface mode.
   if(((chip>>4)&3)<2||(chip&7)!=0)throw std::runtime_error("PHY strap voltage/mode differs from admitted RGMII bank");
   // The shared-clock serializers supply +2 ns TX skew. Clear ONLY the
   // extra TX delay and inversion; RX settings are unused and preserved.
   ext_write(0xa003,delay&~0x400fu);
   if((ext_read(0xa003)&0x400f)||ext_read(0xa001)!=chip)throw std::runtime_error("PHY TX delay/strap readback mismatch");
   const auto bmcr=*mdio(true,phy,0,0);mdio(false,phy,0,(bmcr&~0x8c00u)|0x1200u);
   const auto deadline=now()+5.;uint16_t bmsr=0,ssr=0;
   do{
    mdio(true,phy,1,0);bmsr=*mdio(true,phy,1,0);ssr=*mdio(true,phy,0x11,0);
    if((bmsr&0x24)==0x24&&(ssr&0xec00)==0xac00)break;
    pause_us(50000);
   }while(now()<deadline);
   report["phy"]={{"address",phy},{"id",identity},{"chip_config_before",chip},{"delay_before",delay},{"delay_after",ext_read(0xa003)},{"bmsr",bmsr},{"specific_status",ssr}};
   if((bmsr&0x24)!=0x24||(ssr&0xec00)!=0xac00)throw std::runtime_error("PL PHY did not negotiate 1000 Mbps full duplex");
   for(const auto& word:std::vector<std::pair<unsigned,uint32_t>>{{12,session},{16,uint32_t(mac)},{20,uint32_t(mac>>32)},
       {24,local},{28,destination},{40,(uint32_t(sport)<<16)|dport},{0x60,uint32_t(next_hop)},{0x64,uint32_t(next_hop>>32)}}){
    write(word.first,word.second);if(read(word.first)!=word.second)throw std::runtime_error("Network configuration readback mismatch");
   }
   const auto rejected=read(0x2c);write(4,1);pause_us(1000);
   if(read(4)!=1||read(0x2c)!=rejected)throw std::runtime_error("Network enable rejected");
  }
  report["after"]=status();Device::Close(*device);device.reset();
  report["sdk_closed"]=true;report["status"]="configured";std::cout<<"WCIS_NET_RESULT "<<report.dump()<<std::endl;return 0;
 }catch(const std::exception& e){
  if(device){try{if(admitted)device->defaultRegRegion().write(NET+4,0,false);Device::Close(*device);device.reset();}catch(...){}}
  report["status"]="error";report["message"]=e.what();report["sdk_closed"]=!device.has_value();
  std::cout<<"WCIS_NET_RESULT "<<report.dump()<<std::endl;return 2;
 }
}
