// Bounded ModelBackend experiment: NPU frame A and FAC1 frame B, one allocator.
// Reuses the vendor Session callback pattern proved by parallel_npu_jpeg_runner.
// It does not capture, schedule a live service, alter model arithmetic, or unlock.
#include "frame_lease.h"
#include <icraft-xrt/core/session.h>
#include <icraft-xrt/dev/host_device.h>
#include <icraft-backends/hostbackend/backend.h>
#include <icraft-backends/zg330backend/zg330backend.h>
#include <icraft-xir/ops/hard_op.h>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <thread>
#include <sys/file.h>
#include <fcntl.h>
#include <unistd.h>
using namespace icraft::xrt;
using Json=nlohmann::json;namespace fs=std::filesystem;using Clock=std::chrono::steady_clock;
static constexpr uint32_t REG=0x400c2000;
static const fs::path marker="/root/wcis-face/hardware-review-required.json";
static double ms(Clock::time_point t){return std::chrono::duration<double,std::milli>(Clock::now()-t).count();}
static void emit(const Json& q){std::cout<<"\nWCIS_PL_NPU_RESULT "<<q.dump()<<std::endl;}
[[noreturn]] static void fault(const std::string& text){
 std::ofstream f(marker);f<<Json{{"boot_id",frame_lease::boot_id()},{"source","NPU_FAC1_trial"},{"message",text},{"automatic_retry",false}}.dump(2)<<std::endl;
 emit({{"status","error"},{"message",text}});std::_Exit(3);
}
struct NextPL {
 Device device;MemChunk memory;frame_lease::Lease lease;std::vector<char> source;
 uint32_t pixels;bool started=false;Clock::time_point start_time;
 NextPL(Device d,const Json& q):device(d){
  auto regs=device.defaultRegRegion();if(regs.read(REG,false)!=0x46414331||(regs.read(REG+4,false)&1))throw std::runtime_error("FAC1 absent or busy");
  const auto w=frame_lease::number(q,"src_w"),h=frame_lease::number(q,"src_h"),pitch=frame_lease::number(q,"pitch_bytes");
  const bool rgb565=q.at("rgb565");
  if(!w||!h||w>8192||h>8192||pitch%8||pitch<w*(rgb565?2:4)||pitch>65536)throw std::runtime_error("Invalid next-frame source geometry");
  const auto cw=frame_lease::number(q,"content_w"),ch=frame_lease::number(q,"content_h"),dw=frame_lease::number(q,"canvas_w"),dh=frame_lease::number(q,"canvas_h");
  if(!cw||!ch||cw>dw||ch>dh||!dw||!dh||dw>640||dh>640)throw std::runtime_error("Invalid next-frame output geometry");
  const uint64_t bytes=pitch*h,total=128+frame_lease::aligned(bytes)+frame_lease::OUTPUT_CAPACITY;
  const fs::path path=q.at("input_rgbx").get<std::string>();if(total>frame_lease::MAX_BYTES||fs::file_size(path)!=bytes)throw std::runtime_error("Next-frame source length/allocation mismatch");
  memory=device.defaultMemRegion().malloc(total,true,64);
  lease=frame_lease::Lease::parse({{"schema_version",1},{"allocation_base",memory->begin.addr()},{"allocation_bytes",total},{"src_w",w},{"src_h",h},{"pitch_bytes",pitch},
      {"frame_id",q.at("frame_id")},{"frame_token",q.at("frame_token")},{"boot_id",frame_lease::boot_id()},{"rgb565",rgb565}});
  std::vector<char> data(total,static_cast<char>(0xa5));source.resize(bytes);std::ifstream f(path,std::ios::binary);f.read(source.data(),bytes);if(!f)throw std::runtime_error("Cannot read next frame");
  std::copy(source.begin(),source.end(),data.begin()+64);const auto head=lease.guard(),tail=lease.guard(true);
  std::copy(head.begin(),head.end(),data.begin());std::copy(tail.begin(),tail.end(),data.begin()+lease.guard_offset);memory.write(0,data.data(),data.size());
  pixels=dw*dh;std::vector<char> initialized(pixels*4);const auto init=Clock::now();
  do{memory.read(initialized.data(),lease.output_offset,initialized.size());if(std::all_of(initialized.begin(),initialized.end(),[](char c){return c==static_cast<char>(0xa5);}))break;
   if(ms(init)>2000)fault("Next-frame initialization visibility deadline");}while(true);
  std::vector<uint32_t> words={lease.id,static_cast<uint32_t>(lease.source_address()),static_cast<uint32_t>(pitch),static_cast<uint32_t>(lease.output_address()),
   static_cast<uint32_t>((h<<16)|w),static_cast<uint32_t>((ch<<16)|cw),static_cast<uint32_t>((dh<<16)|dw),(rgb565?2u:0u)|(q.value("replicate",true)?1u:0u),0};
  if(q.at("inverse_q16").size()!=6)throw std::runtime_error("Expected six affine coefficients");
  for(const auto& v:q.at("inverse_q16")){if(!v.is_number_integer())throw std::runtime_error("Noninteger affine coefficient");const auto n=v.get<int64_t>();if(n<INT32_MIN||n>INT32_MAX)throw std::runtime_error("Affine coefficient overflow");words.push_back(static_cast<uint32_t>(n));}
  for(size_t i=0;i<words.size();++i)regs.write(REG+16+i*4,words[i],false);
  for(size_t i=0;i<words.size();++i)if(regs.read(REG+16+i*4,false)!=words[i])throw std::runtime_error("Next-frame descriptor readback mismatch");
  check();
 }
 uint32_t status()const{return device.defaultRegRegion().read(REG+4,false);}
 void check()const{
  std::array<char,64> a{},b{};memory.read(a.data(),0,64);memory.read(b.data(),lease.guard_offset,64);
  if(a!=lease.guard()||b!=lease.guard(true))throw std::runtime_error("Next-frame guard changed");
  for(const auto& x:memory->region.memManager().getAllMemChunk()){
   const auto base=x->begin.addr(),bytes=x->byte_size;if(base==lease.base&&bytes==lease.bytes)continue;
   if(base<lease.base+lease.bytes&&lease.base<base+bytes)throw std::runtime_error("NPU allocation overlaps next-frame storage");
  }
 }
 void start(){
  if(started||(status()&1))throw std::runtime_error("Next-frame operation already running");started=true;start_time=Clock::now();device.defaultRegRegion().write(REG,1,false);
  while(!(status()&1))if(ms(start_time)>2)fault("Next-frame START did not establish a fresh busy interval");
 }
 Json finish(const fs::path& out){
  if(!started)throw std::runtime_error("Next-frame operation not submitted");auto regs=device.defaultRegRegion();uint32_t s=0;
  do{s=status();if(ms(start_time)>10000)fault("Next-frame completion deadline");if(!(s&2))std::this_thread::sleep_for(std::chrono::microseconds(50));}while(!(s&2));
  if((s&1)||(s&8)||((s>>4)&15)||regs.read(REG+8,false)!=lease.id||regs.read(REG+12,false)!=pixels)fault("Next-frame completion identity/error mismatch");
  const double done_ms=ms(start_time);std::vector<char> output(pixels*4);const auto readback=Clock::now();unsigned reads=0;
  do{memory.read(output.data(),lease.output_offset,output.size());++reads;bool partial=false;for(size_t i=3;i<output.size();i+=4)partial|=output[i]!=0;
   if(!partial)break;if(ms(readback)>2000)fault("Next-frame output visibility deadline");}while(true);
  const double readback_ms=ms(readback);std::vector<char> actual(source.size());memory.read(actual.data(),64,actual.size());if(actual!=source)fault("Next-frame source changed during NPU/PL execution");check();
  std::ofstream f(out,std::ios::binary);f.write(output.data(),output.size());f.close();if(!f)throw std::runtime_error("Cannot save next-frame pixels");
  return {{"frame_id",lease.id},{"frame_token",lease.token},{"done_observed_ms",done_ms},{"readback_ms",readback_ms},{"output_reads",reads},
      {"file",out.string()},{"bytes",output.size()},{"source_equal",true},{"guards_equal",true},{"lease",lease.json()}};
 }
};
static Json run(const icraft::xir::Network& network,Device device,const Json& q){
 const bool overlap=q.at("mode")=="overlap";const auto start_all=Clock::now();
 const fs::path out=q.at("output_directory").get<std::string>();if(fs::exists(out))throw std::runtime_error("Output already exists");fs::create_directories(out);
 NextPL next(device,q.at("pl"));const auto npu_frame=frame_lease::number(q,"npu_frame_id");
 if(!npu_frame||npu_frame>0xffffffffULL||npu_frame==next.lease.id)throw std::runtime_error("Expected two distinct frame identities");
 auto session=Session::Create<icraft::xrt::zg330::ZG330Backend,HostBackend>(network,{device,HostDevice::Default()});
 auto backend=session->backends[0].cast<icraft::xrt::zg330::ZG330Backend>();backend.disableMergeHardOp();backend.disableEtmOptimize();backend.ocmOptimize(icraft::xrt::zg330::OcmOpt::None);session.apply();session.enableTimeProfile(false);next.check();
 const auto type=network.inputs()[0].tensorType();const size_t bytes=type.numElements()*sizeof(float);const fs::path input=q.at("input_f32").get<std::string>();if(fs::file_size(input)!=bytes)throw std::runtime_error("NPU input length mismatch");
 std::vector<float> data(bytes/4);std::ifstream f(input,std::ios::binary);f.read(reinterpret_cast<char*>(data.data()),bytes);if(!f)throw std::runtime_error("NPU input read failed");for(float v:data)if(!std::isfinite(v))throw std::runtime_error("Nonfinite NPU input");
 auto host=HostDevice::MemRegion().malloc(bytes);host.write(0,reinterpret_cast<char*>(data.data()),bytes);Tensor tensor(type,host);
 Json witness=Json::object();int64_t selected=-1;bool witnessed=false;const double preparation_ms=ms(start_all);const auto start=Clock::now();
 session.setPreCallBack([&](const Session&,const icraft::xir::Operation& op,const Backend& b,std::vector<Tensor>&){
  if(selected<0&&b.is<icraft::xrt::zg330::ZG330Backend>()&&op.is<icraft::xir::HardOp>()&&op->name.find("Conv2d")!=std::string::npos){
   selected=op->op_id;if(overlap)next.start();witness={{"op_id",selected},{"op_name",op->name},{"pre_ms",ms(start)},{"pl_status_before_conv",next.status()}};
  }
 });
 session.setPostCallBack([&](const Session&,const icraft::xir::Operation& op,const Backend& b,std::vector<Tensor>& values){
  if(!witnessed&&op->op_id==selected&&b.is<icraft::xrt::zg330::ZG330Backend>()){
   if(values.empty())throw std::runtime_error("No convolution output tensors");for(auto& v:values)if(!v.waitForReady(std::chrono::microseconds(10000000),std::chrono::microseconds(50)))fault("Convolution completion deadline");
   witness["conv_outputs_ready"]=true;witness["post_ready_ms"]=ms(start);witness["pl_status_after_conv_ready"]=next.status();witnessed=true;
  }
 });
 try{
  auto outputs=session.forward({tensor});for(auto& v:outputs)if(!v.waitForReady(std::chrono::microseconds(10000000),std::chrono::microseconds(50)))fault("NPU graph completion deadline");
  const double npu_ms=ms(start);if(!witnessed)throw std::runtime_error("No actual convolution witness");if(!overlap)next.start();
  auto pl=next.finish(out/"next.rgbx");const double both_ms=ms(start);Json records=Json::array();
  if(outputs.size()!=network.outputs().size())throw std::runtime_error("NPU output count mismatch");
  for(size_t i=0;i<outputs.size();++i){const auto count=network.outputs()[i].tensorType().numElements();if(!outputs[i].dtype()->element_dtype.isFP32()||outputs[i].dtype().numElements()!=count)throw std::runtime_error("NPU output contract mismatch");
   const auto path=out/(std::to_string(i)+".f32");std::ofstream file(path,std::ios::binary);outputs[i].dump(file,"SFB");file.close();if(!file||fs::file_size(path)!=count*4)throw std::runtime_error("NPU output dump mismatch");records.push_back({{"index",i},{"elements",count},{"file",path.string()}});
  }
  next.check();int bound=0;for(const auto& b:session.backendBindings())if(b.second.is<icraft::xrt::zg330::ZG330Backend>())++bound;if(!bound)throw std::runtime_error("No bound NPU operations");
  const bool proven=overlap&&((witness.at("pl_status_before_conv").get<uint32_t>()&1)!=0)&&((witness.at("pl_status_after_conv_ready").get<uint32_t>()&1)!=0);
  device.reset(1);next.check();return {{"status","completed"},{"mode",q.at("mode")},{"role",q.at("role")},{"npu_frame_id",npu_frame},{"pl",pl},{"outputs",records},{"npu_bound_ops",bound},
      {"convolution_witness",witness},{"overlap_proven",proven},{"preparation_ms",preparation_ms},{"npu_ready_ms",npu_ms},{"both_ready_ms",both_ms},{"one_sdk_owner",true}};
 }catch(const std::exception& e){fault(e.what());}
}
int main(int argc,char** argv){
 if(argc!=3||std::string(argv[1])!="--serve")return 2;
 try{
  for(const char* name:{"WCIS_NPU_LOCK_FD","WCIS_CAMERA_LOCK_FD"}){const char* v=getenv(name);if(!v)return 2;const int fd=atoi(v);if(fd<3||fcntl(fd,F_GETFD)<0||flock(fd,LOCK_EX|LOCK_NB))return 2;}
  const fs::path manifest=fs::absolute(argv[2]);std::ifstream f(manifest);Json cfg;f>>cfg;if(cfg.at("schema_version")!=1||cfg.at("generated")!=true)throw std::runtime_error("Unverified model manifest");
  std::map<std::string,icraft::xir::Network> models;
  for(const std::string role:{"yunet","mobilefacenet"}){const auto& m=cfg.at("models").at(role);auto network=icraft::xir::Network::CreateFromJsonFile((manifest.parent_path()/m.at("json").get<std::string>()).string());network.lazyLoadParamsFromFile((manifest.parent_path()/m.at("raw").get<std::string>()).string());models.emplace(role,network);}
  emit({{"status","ready"},{"device_opened",false},{"boot_id",frame_lease::boot_id()}});std::string line;
  while(std::getline(std::cin,line)){
   if(line.size()>65536)throw std::runtime_error("Oversize request");auto q=Json::parse(line);if(q.at("mode")!="serial"&&q.at("mode")!="overlap")throw std::runtime_error("Invalid trial mode");
   if(q.at("boot_id")!=frame_lease::boot_id())throw std::runtime_error("Trial boot changed");
   if(fs::exists(marker)){std::ifstream g(marker);Json old;g>>old;if(old.value("boot_id","")==frame_lease::boot_id())throw std::runtime_error("Hardware quarantined");}
   auto device=Device::Open("axi://zg330aiu?npu=0x40000000&dma=0x80000000");const auto geometry=device.cast<ZG330Device>().getRowsCols();if(cfg.at("rows")!=geometry.first||cfg.at("cols")!=geometry.second)fault("MPE geometry mismatch");
   Json result;try{result=run(models.at(q.at("role").get<std::string>()),device,q);}catch(const std::exception& e){fault(e.what());}
   Device::Close(device);result["device_closed"]=true;emit(result);
  }
  return 0;
 }catch(const std::exception& e){emit({{"status","error"},{"message",e.what()}});return 2;}
}
