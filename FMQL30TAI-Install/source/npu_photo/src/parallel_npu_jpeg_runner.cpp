// One SDK device, one allocator, one immutable frame. No threads or extra
// Device::Open while engines are busy. Caller retains the release npu.lock.
#include "frame_lease.h"
#include <icraft-xrt/core/session.h>
#include <icraft-xrt/dev/host_device.h>
#include <icraft-backends/hostbackend/backend.h>
#include <icraft-backends/zg330backend/zg330backend.h>
#include <icraft-xir/ops/hard_op.h>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <iostream>
#include <map>
#include <thread>
#include <vector>
using namespace icraft::xrt;
using Json=nlohmann::json;
namespace fs=std::filesystem;
using Clock=std::chrono::steady_clock;
static constexpr uint32_t JPG=0x400c2100;
static constexpr uint64_t CAP=8ull*1024*1024,TOTAL=CAP+128;
static double ms(Clock::time_point t){return std::chrono::duration<double,std::milli>(Clock::now()-t).count();}
static void emit(const Json& q){std::cout<<"\nWCIS_PARALLEL_RESULT "<<q.dump()<<std::endl;}
[[noreturn]] static void fault(const fs::path& marker,const std::string& msg){
 std::ofstream f(marker);f<<Json{{"boot_id",frame_lease::boot_id()},{"source","NPU_JPG1_parallel"},{"message",msg},{"automatic_retry",false}}.dump(2)<<std::endl;
 std::cerr<<msg<<std::endl;std::_Exit(3);
}
struct JPEG {
 Device device;frame_lease::Lease lease;MemChunk memory;fs::path marker;bool started=false,complete=false;
 Clock::time_point epoch,started_at;uint32_t cycles=0;double finished_ms=0;
 JPEG(Device d,const frame_lease::Lease& l,const fs::path& m):device(d),lease(l),marker(m){
  auto r=device.defaultRegRegion();
  if(r.read(JPG,false)!=0x4a504731||(r.read(JPG+4,false)&1)||r.read(JPG+36,false)!=1920||r.read(JPG+40,false)!=1080)
   throw std::runtime_error("JPG1 absent/busy/incompatible");
  memory=device.defaultMemRegion().malloc(TOTAL,true,64);auto base=memory->begin.addr();
  if(base%64||base>=frame_lease::WINDOW||TOTAL>frame_lease::WINDOW-base)throw std::runtime_error("JPEG allocation outside verified window");
  std::vector<char> guard(64,static_cast<char>(0xa5));memory.write(0,guard.data(),64);memory.write(TOTAL-64,guard.data(),64);
 }
 uint32_t status()const{return device.defaultRegRegion().read(JPG+4,false);}
 void start(){
  if(started)throw std::runtime_error("JPEG already submitted");
  auto r=device.defaultRegRegion();if(status()&1)throw std::runtime_error("JPEG unexpectedly busy before submit");
  const auto base=memory->begin.addr();
  const std::vector<uint32_t> words={lease.id,static_cast<uint32_t>(lease.source_address()),static_cast<uint32_t>(base+64),static_cast<uint32_t>(CAP),lease.rgb565?0u:1u};
  for(size_t i=0;i<words.size();++i)r.write(JPG+16+i*4,words[i],false);
  for(size_t i=0;i<words.size();++i)if(r.read(JPG+16+i*4,false)!=words[i])throw std::runtime_error("JPEG descriptor mismatch");
  started=true;started_at=Clock::now();r.write(JPG,1,false);
 }
 Json finish(const fs::path& path){
  if(!started)throw std::runtime_error("JPEG was not submitted");
  auto r=device.defaultRegRegion();uint32_t s;
  do{s=status();if(ms(started_at)>10000)fault(marker,"JPEG parallel deadline");if(!(s&2))std::this_thread::sleep_for(std::chrono::microseconds(50));}while(!(s&2));
  if((s&1)||((s>>4)&15)||(s&8)||r.read(JPG+8,false)!=lease.id)fault(marker,"JPEG parallel completion/frame error");
  complete=true;finished_ms=ms(epoch);const auto bytes=r.read(JPG+12,false);cycles=r.read(JPG+48,false);
  if(bytes<100||bytes>CAP||!cycles)fault(marker,"Invalid parallel JPEG bytes/cycles");
  std::vector<char> data(frame_lease::aligned(bytes));memory.read(data.data(),64,data.size());
  if(static_cast<unsigned char>(data[0])!=255||static_cast<unsigned char>(data[1])!=216||static_cast<unsigned char>(data[bytes-2])!=255||static_cast<unsigned char>(data[bytes-1])!=217)
   fault(marker,"Parallel JPEG SOI/EOI absent");
  std::vector<char> guard(64,static_cast<char>(0xa5)),actual(64);
  for(uint64_t offset:std::vector<uint64_t>{0,TOTAL-64}){memory.read(actual.data(),offset,64);if(actual!=guard)fault(marker,"Parallel JPEG guard changed");}
  std::ofstream f(path,std::ios::binary);f.write(data.data(),bytes);f.close();if(!f)throw std::runtime_error("JPEG file write failed");
  return {{"file",path.string()},{"bytes",bytes},{"cycles",cycles},{"read_blocks",r.read(JPG+64,false)},{"write_blocks",r.read(JPG+68,false)},
   {"started_ms",std::chrono::duration<double,std::milli>(started_at-epoch).count()},{"completion_observed_ms",finished_ms},
   {"allocation_base",memory->begin.addr()},{"allocation_bytes",TOTAL}};
 }
};
static Json run(const icraft::xir::Network& network,Device device,frame_lease::Reservation& held,const Json& q){
 const bool overlap=q.at("mode")=="overlap";
 const auto marker=fs::path(q.at("fault_marker").get<std::string>());
 const auto out=fs::path(q.at("output_directory").get<std::string>());
 if(fs::exists(out))throw std::runtime_error("Output directory exists");
 fs::create_directories(out);
 // Allocate both owned output regions before session setup/submission.
 JPEG jpeg(device,held.lease,marker);held.check();
 auto session=Session::Create<icraft::xrt::zg330::ZG330Backend,HostBackend>(network,{device,HostDevice::Default()});
 auto backend=session->backends[0].cast<icraft::xrt::zg330::ZG330Backend>();
 backend.disableMergeHardOp();backend.disableEtmOptimize();backend.ocmOptimize(icraft::xrt::zg330::OcmOpt::None);
 session.apply();session.enableTimeProfile(false);held.check();
 const auto type=network.inputs()[0].tensorType();const size_t bytes=type.numElements()*sizeof(float);
 const fs::path input=q.at("input_f32").get<std::string>();if(fs::file_size(input)!=bytes)throw std::runtime_error("Tensor length mismatch");
 std::vector<float> data(bytes/4);std::ifstream f(input,std::ios::binary);f.read(reinterpret_cast<char*>(data.data()),bytes);
 if(!f)throw std::runtime_error("Tensor read failed");
 for(float v:data)if(!std::isfinite(v))throw std::runtime_error("Nonfinite input");
 auto host=HostDevice::MemRegion().malloc(bytes);host.write(0,reinterpret_cast<char*>(data.data()),bytes);Tensor tensor(type,host);
 Json witness=Json::object();int64_t selected=-1;bool witnessed=false;const auto start=Clock::now();jpeg.epoch=start;
 session.setPreCallBack([&](const Session&,const icraft::xir::Operation& op,const Backend& b,std::vector<Tensor>&){
  if(selected<0&&b.is<icraft::xrt::zg330::ZG330Backend>()&&op.is<icraft::xir::HardOp>()&&op->name.find("Conv2d")!=std::string::npos){
   selected=op->op_id;if(overlap)jpeg.start();
   witness={{"op_id",selected},{"op_name",op->name},{"pre_ms",ms(start)},{"jpeg_status_before_npu",jpeg.status()}};
  }
 });
 session.setPostCallBack([&](const Session&,const icraft::xir::Operation& op,const Backend& b,std::vector<Tensor>& values){
  if(!witnessed&&op->op_id==selected&&b.is<icraft::xrt::zg330::ZG330Backend>()){
   if(values.empty())throw std::runtime_error("Convolution callback has no output tensors");
   for(auto& v:values)if(!v.waitForReady(std::chrono::microseconds(10000000),std::chrono::microseconds(50)))fault(marker,"NPU convolution completion deadline");
   witness["output_tensors_ready"]=true;witness["output_count"]=values.size();witness["post_ready_ms"]=ms(start);
   witness["jpeg_status_after_npu_ready"]=jpeg.status();witnessed=true;
  }
 });
 try{
  auto outputs=session.forward({tensor});
  for(auto& v:outputs)if(!v.waitForReady(std::chrono::microseconds(10000000),std::chrono::microseconds(50)))fault(marker,"NPU graph deadline");
  const double npu_ready_ms=ms(start);
  if(!witnessed)throw std::runtime_error("No real ZG330 convolution witness");
  if(!overlap)jpeg.start();
  const auto image=jpeg.finish(out/"output.jpg");const double both_ready_ms=ms(start);
  held.check();Json records=Json::array();
  for(size_t i=0;i<outputs.size();++i){
   const auto count=network.outputs()[i].tensorType().numElements();
   if(!outputs[i].dtype()->element_dtype.isFP32()||outputs[i].dtype().numElements()!=count)throw std::runtime_error("Output contract mismatch");
   const auto path=out/(std::to_string(i)+".f32");std::ofstream stream(path,std::ios::binary);outputs[i].dump(stream,"SFB");stream.close();
   if(!stream||fs::file_size(path)!=count*4)throw std::runtime_error("Output file length mismatch");
   records.push_back({{"index",i},{"elements",count},{"file",path.string()}});
  }
  int bound=0;for(const auto& binding:session.backendBindings())if(binding.second.is<icraft::xrt::zg330::ZG330Backend>())++bound;
  if(bound<1)throw std::runtime_error("No hardware NPU binding");
  const bool proof=overlap&&witness.value("output_tensors_ready",false)&&
   ((witness.at("jpeg_status_before_npu").get<uint32_t>()&1)!=0)&&((witness.at("jpeg_status_after_npu_ready").get<uint32_t>()&1)!=0);
  return {{"status","completed"},{"mode",q.at("mode")},{"frame_id",held.lease.id},{"frame_token",held.lease.token},
   {"outputs",records},{"jpeg",image},{"npu_bound_ops",bound},{"convolution_witness",witness},{"overlap_proven",proof},
   {"npu_ready_ms",npu_ready_ms},{"both_ready_ms",both_ready_ms},{"frame_preserved",true},{"source_uploaded",false}};
 }catch(const std::exception& e){
  // A concurrent accelerator must never lose its output allocation on error.
  // Retain all handles/lock via quarantine and process termination until review.
  fault(marker,e.what());
 }
}
int main(int argc,char** argv){
 if(argc==2&&std::string(argv[1])=="--help"){std::cout<<"wcis_npu_jpeg_parallel --serve MODELS.json; one shared SDK device per command, original frame lease required.\n";return 0;}
 if(argc!=3||std::string(argv[1])!="--serve")return 2;
 try{
  const fs::path manifest=fs::absolute(argv[2]);std::ifstream f(manifest);Json cfg;f>>cfg;
  std::map<std::string,icraft::xir::Network> models;
  for(const std::string role:{"yunet","mobilefacenet"}){
   const auto& m=cfg.at("models").at(role);
   auto net=icraft::xir::Network::CreateFromJsonFile((manifest.parent_path()/m.at("json").get<std::string>()).string());
   net.lazyLoadParamsFromFile((manifest.parent_path()/m.at("raw").get<std::string>()).string());models.emplace(role,net);
  }
  emit({{"status","ready"},{"device_opened",false},{"boot_id",frame_lease::boot_id()}});
  std::string line;while(std::getline(std::cin,line)){
   if(line.size()>65536)throw std::runtime_error("Oversize request");
   const auto q=Json::parse(line);
   if(q.at("mode")!="serial"&&q.at("mode")!="overlap")throw std::runtime_error("Unknown execution mode");
   const auto lease=frame_lease::Lease::parse(q.at("retained_frame"));
   if(lease.w!=1920||lease.h!=1080||lease.pitch!=1920*(lease.rgb565?2:4))throw std::runtime_error("Native packed 1080p lease required");
   const fs::path marker=q.at("fault_marker").get<std::string>();
   if(fs::exists(marker)){std::ifstream f(marker);Json old;f>>old;if(old.value("boot_id","")==frame_lease::boot_id())throw std::runtime_error("Hardware quarantined");}
   auto device=Device::Open("axi://zg330aiu?npu=0x40000000&dma=0x80000000");
   const auto geometry=device.cast<ZG330Device>().getRowsCols();if(cfg.at("rows")!=geometry.first||cfg.at("cols")!=geometry.second)throw std::runtime_error("MPE geometry mismatch");
   Json result;
   {frame_lease::Reservation held(device,lease);result=run(models.at(q.at("role").get<std::string>()),device,held,q);held.check();}
   Device::Close(device);result["device_closed"]=true;emit(result);
  }
  return 0;
 }catch(const std::exception& e){emit({{"status","error"},{"message",e.what()}});return 2;}
}
