// Finite comparison on actual 1080p SDI. One SDK owner, no model or BOOT writes.
#include "frame_lease.h"
#include "pipeline/io/input/sdicamera.hpp"
#include "wcis_camera_mmio.hpp"
#include "wcis_owner_vpu.hpp"
#include "wcis_capture_wait.hpp"
#include "wcis_sdi_diagnostics.hpp"
#include <atomic>
#include <csignal>
#include <deque>
#include <mutex>
#include <sys/file.h>
using namespace icraft::xrt;
using Json=nlohmann::json;namespace fs=std::filesystem;
constexpr uint64_t CAM=0x40080000,JPG=0x400c2100;
constexpr size_t WIDTH=1920,HEIGHT=1080,RAW=WIDTH*HEIGHT*2,CAPACITY=8*1024*1024;
static fs::path marker="/root/wcis-face/hardware-review-required.json",workspace;
static std::string boot;static volatile std::sig_atomic_t stopping=0;
static void stop(int){stopping=1;}
static double now(){return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();}
[[noreturn]] static void fault(const std::string& msg){
 const Json q={{"boot_id",boot},{"source","encoder_trial"},{"message",msg},{"automatic_retry",false}};
 std::ofstream f(marker);f<<q.dump(2);f.close();std::ofstream detail(workspace/"fault.json");detail<<q.dump(2);detail.close();
 std::cerr<<msg<<std::endl;std::_Exit(3);
}
static void save(const fs::path& p,const Json& q){std::ofstream f(p);f<<q.dump(2);f.close();if(!f)throw std::runtime_error("Trial report write failed");}
static void bytes(const fs::path& p,const std::vector<unsigned char>& b){std::ofstream f(p,std::ios::binary);f.write(reinterpret_cast<const char*>(b.data()),b.size());f.close();if(!f)throw std::runtime_error("Trial image write failed");}
struct Frame{uint32_t id;double requested,completed;std::vector<unsigned char> raw;};
class TrialCamera {
 std::vector<MemChunk> buffers;std::array<const char*,2> pointers{};std::array<uint32_t,2> addresses{};
 CameraMmio regs;std::optional<unsigned> pending;double requested=0;
 std::shared_ptr<const Frame> latest;std::mutex mutex;std::thread thread;std::atomic<bool> halt{false};
 void arm(unsigned i){
  if(pending||regs.read(4)||regs.read(8)||regs.read(0x18)||regs.read(0x44)||regs.read(0x70))throw std::runtime_error("Trial camera branch busy");
  auto d=wcis::read_sdi_diagnostics([&](uint64_t a){return regs.read(a-CAM);},CAM);
  if(d.state!=wcis::SdiReadState::Ready||(d.words[2]&3)!=3||!(d.words[6]&1)||d.words[11]!=((1080u<<16)|1920u))throw std::runtime_error("Trial requires locked real 1080p SDI");
  pending=i;requested=now();++requests;regs.write(0x50,addresses[i]>>3);regs.write(4,1);
  const double deadline=now()+.01;while(regs.read(0x58)&1)if(now()>deadline)fault("Trial camera stale DONE did not clear");
 }
 void drain(){
  if(!pending)return;
  auto r=wcis::wait_capture([&]{return regs.read(0x58);},[]{return false;},2000,false);
  if(r.state!=wcis::CaptureState::Done)fault("Trial camera DMA did not complete");pending.reset();
 }
 void grab(bool check=false){
  if(!pending)arm(0);const unsigned i=*pending;const double pts=requested;drain();const double completed=now();arm(1-i);
  std::vector<unsigned char> raw(RAW);CameraMmio::before_copy();std::memcpy(raw.data(),pointers[i],RAW);
  if(check){std::vector<unsigned char> verify(RAW);buffers[i].read(reinterpret_cast<char*>(verify.data()),0,RAW);if(verify!=raw)throw std::runtime_error("Trial UDMA mapping differs from SDK readback");}
  auto image=std::make_shared<const Frame>(Frame{++captured,pts,completed,std::move(raw)});
  std::lock_guard<std::mutex> lock(mutex);latest=std::move(image);
 }
public:
 std::atomic<uint32_t> captured{0};std::atomic<uint64_t> requests{0};unsigned drained=0;
 explicit TrialCamera(const Device& dev){
  auto r=dev.defaultRegRegion();
  if(r.read(CAM+12)!=0x20230218||r.read(CAM+4)||r.read(CAM+8)||r.read(CAM+0x44)||r.read(CAM+0x70))throw std::runtime_error("Trial camera firmware/busy mismatch");
  for(unsigned i=0;i<2;++i){
   auto b=dev.getMemRegion("udma").malloc(RAW,true,64);const auto addr=b->begin.addr();
   if(addr%64||addr<0x30100000||addr+RAW>0x38100000)throw std::runtime_error("Trial camera allocation outside admitted UDMA range");
   for(const auto& old:buffers)if(addr<old->begin.addr()+RAW&&old->begin.addr()<addr+RAW)throw std::runtime_error("Trial camera allocations overlap");
   pointers[i]=b->begin.cptr();addresses[i]=addr;buffers.push_back(b);
  }
  // Configure only the PS branch, preserving the FAC1/ImageMake route disabled.
  for(const auto& w:std::vector<std::pair<uint32_t,uint32_t>>{{0x18,0},{0x44,0},{8,0},{0xb4,0},{0x5c,1919},{0x60,1079},{0x64,(1920u<<16)|1080u},{0x68,0x11},{0x78,0},{0x6c,RAW/8}}){r.write(CAM+w.first,w.second);if(r.read(CAM+w.first)!=w.second||regs.read(w.first)!=w.second)throw std::runtime_error("Trial camera setup readback mismatch");}
  if(regs.read(12)!=r.read(CAM+12)||regs.read(0x100)!=0x53444932)throw std::runtime_error("Trial camera direct mapping not admitted");
  grab(true);grab(true);
  thread=std::thread([this]{try{while(!halt&&!stopping)grab();}catch(const std::exception& e){fault(e.what());}});
 }
 std::shared_ptr<const Frame> next(uint32_t after){
  const double deadline=now()+2;
  for(;;){{std::lock_guard<std::mutex> lock(mutex);if(latest&&latest->id>after)return latest;}
   if(now()>deadline)throw std::runtime_error("Trial source did not advance");std::this_thread::sleep_for(std::chrono::milliseconds(1));}
 }
 void close(){halt=true;if(thread.joinable())thread.join();if(pending){drain();++drained;}buffers.clear();}
 ~TrialCamera(){if(thread.joinable())fault("Trial camera must be explicitly drained before destruction");}
};
class PlJpeg {
 Device dev;MemChunk memory;uint64_t base;size_t high_water=64;
 static constexpr size_t SOURCE=64,DEST=SOURCE+RAW+64,TOTAL=DEST+CAPACITY+64;
 void guard(){std::array<char,64> g;for(auto off:{size_t(0),DEST-64,TOTAL-64}){memory.read(g.data(),off,64);for(char c:g)if(c!=static_cast<char>(0xa5))fault("Trial PL JPEG allocation guard changed");}}
public:
 explicit PlJpeg(Device d):dev(d),memory(d.defaultMemRegion().malloc(TOTAL,true,64)),base(memory->begin.addr()){
  auto r=d.defaultRegRegion();if(r.read(JPG)!=0x4a504731||(r.read(JPG+4)&1)||r.read(JPG+36)!=WIDTH||r.read(JPG+40)!=HEIGHT||r.read(JPG+44)!=75)throw std::runtime_error("Trial JPG1 geometry/quality contract mismatch");
  if(base%64||base>=frame_lease::WINDOW||TOTAL>frame_lease::WINDOW-base)throw std::runtime_error("Trial PL allocation outside admitted window");
  std::vector<char> init(TOTAL,static_cast<char>(0xa5));memory.write(0,init.data(),init.size());guard();
 }
 std::pair<std::vector<unsigned char>,Json> encode(const Frame& f){
  const double t=now();memory.write(SOURCE,const_cast<char*>(reinterpret_cast<const char*>(f.raw.data())),RAW);
  const double upload=(now()-t)*1000;std::vector<char> init(high_water,static_cast<char>(0xa5));memory.write(DEST,init.data(),init.size());
  auto r=dev.defaultRegRegion();if(r.read(JPG+4)&1)fault("Trial JPG1 busy before submission");
  const std::array<uint32_t,5> words{{f.id,static_cast<uint32_t>(base+SOURCE),static_cast<uint32_t>(base+DEST),CAPACITY,0}};
  for(unsigned i=0;i<words.size();++i)r.write(JPG+16+4*i,words[i]);
  for(unsigned i=0;i<words.size();++i)if(r.read(JPG+16+4*i)!=words[i])throw std::runtime_error("Trial JPG1 descriptor readback mismatch");
  const double execution=now();r.write(JPG,1);uint32_t s;
  do{s=r.read(JPG+4);if(now()-execution>10)fault("Trial JPG1 execution deadline");if(!(s&2))std::this_thread::sleep_for(std::chrono::microseconds(100));}while(!(s&2));
  if((s&1)||(s&0xf8)||r.read(JPG+8)!=f.id)fault("Trial JPG1 completion mismatch");
  const double encode_ms=(now()-execution)*1000;const size_t n=r.read(JPG+12);if(n<100||n>CAPACITY||r.read(JPG+64)!=RAW/64||r.read(JPG+68)!=(n+63)/64)fault("Trial JPG1 byte/block count mismatch");
  const auto cycles=r.read(JPG+48);std::vector<unsigned char> jpeg(frame_lease::aligned(n));const double read_start=now();memory.read(reinterpret_cast<char*>(jpeg.data()),DEST,jpeg.size());jpeg.resize(n);
  if(jpeg[0]!=255||jpeg[1]!=216||jpeg[n-2]!=255||jpeg[n-1]!=217)fault("Trial JPG1 incomplete JPEG markers");
  const double read_ms=(now()-read_start)*1000;high_water=std::max(high_water,static_cast<size_t>(frame_lease::aligned(n)));guard();
  return {std::move(jpeg),{{"source_upload_ms",upload},{"pl_and_poll_ms",encode_ms},{"readback_ms",read_ms},{"total_ms",(now()-t)*1000},{"hw_cycles",cycles},{"source_upload_bytes",RAW},{"bytes",n},{"frame_id",f.id}}};
 }
 void verify_source(const Frame& f){std::vector<unsigned char> b(RAW);memory.read(reinterpret_cast<char*>(b.data()),SOURCE,b.size());if(b!=f.raw)fault("Trial JPEG source changed in PL DDR");guard();}
};
static cv::Mat bgr(const Frame& f){cv::Mat raw(HEIGHT,WIDTH,CV_8UC2,const_cast<unsigned char*>(f.raw.data())),out;cv::cvtColor(raw,out,cv::COLOR_BGR5652BGR);return out;}
static double validate(const std::vector<unsigned char>& jpeg,const Frame& frame){auto image=cv::imdecode(jpeg,cv::IMREAD_COLOR);if(image.cols!=WIDTH||image.rows!=HEIGHT)fault("Trial JPEG did not decode to actual SDI dimensions");const auto score=cv::PSNR(bgr(frame),image);if(score<20)fault("Trial JPEG color/frame comparison failed");return score;}
static std::vector<unsigned char> nv12(JpegEncoder& encoder,const Frame& f){
 cv::Mat i420;cv::cvtColor(bgr(f),i420,cv::COLOR_BGR2YUV_I420);const size_t y=WIDTH*HEIGHT,uv=encoder.uvOffset();std::vector<unsigned char> data(encoder.inputBytes());
 if(uv<y||uv+y/2>data.size())throw std::runtime_error("Trial VPU NV12 bounds invalid");std::memcpy(data.data(),i420.data,y);
 for(size_t i=0;i<y/4;++i){data[uv+i*2]=i420.data[y+i];data[uv+i*2+1]=i420.data[y+y/4+i];}return data;
}
static void publish(const std::vector<unsigned char>& jpeg,const Frame& f,const TrialCamera& camera,unsigned encoded,const char* encoder){
 const Json meta={{"source","camera"},{"state","ready"},{"boot_id",boot},{"pid",getpid()},{"frame_id",f.id},{"captured",camera.captured.load()},{"encoded",encoded},{"width",WIDTH},{"height",HEIGHT},{"fps_limit",30},{"captured_at",f.requested},{"capture_completion_observed_at",f.completed},{"updated_at",now()},{"encoder",encoder}};
 const auto text=meta.dump();const uint32_t n=text.size();std::ofstream file(workspace/"latest.tmp",std::ios::binary);file.write(reinterpret_cast<const char*>(&n),4);file.write(text.data(),text.size());file.write(reinterpret_cast<const char*>(jpeg.data()),jpeg.size());file.close();if(!file)throw std::runtime_error("Trial frame publish failed");fs::rename(workspace/"latest.tmp",workspace/"latest.frame");save(workspace/"status.json",meta);
}
int main(int argc,char** argv){
 if(argc!=3)return 2;boot=argv[1];workspace=argv[2];if(boot!=frame_lease::boot_id()||workspace.parent_path()!=fs::path("/dev/shm")||workspace.filename().string().find("wcis-encoder-")!=0)return 2;
 for(const char* name:{"WCIS_NPU_LOCK_FD","WCIS_CAMERA_LOCK_FD"}){const char* value=getenv(name);if(!value)return 2;int fd=atoi(value);if(fd<3||fcntl(fd,F_GETFD)<0||flock(fd,LOCK_EX|LOCK_NB))return 2;}
 if(fs::exists(marker)){std::ifstream file(marker);Json old;file>>old;if(old.value("boot_id","")==boot)return 2;}
 std::signal(SIGTERM,stop);std::signal(SIGINT,stop);fs::create_directories(workspace);
 try{
  auto device=Device::Open("axi://zg330aiu?npu=0x40000000&dma=0x80000000");Json report={{"boot_id",boot},{"source","real_SDI"},{"width",WIDTH},{"height",HEIGHT},{"pairs",Json::array()},{"phases",Json::array()}};
  {
   TrialCamera camera(device);PlJpeg pl(device);JpegEncoder vpu(30,WIDTH,HEIGHT,75);unsigned encoded=0;uint32_t last=0;
   auto warm=camera.next(0);auto warm_data=nv12(vpu,*warm);vpu.enqueueDataPtr(reinterpret_cast<char*>(warm_data.data()));vpu.enqueueDataPtr(reinterpret_cast<char*>(warm_data.data()));
   for(unsigned i=0;i<2;++i){std::vector<unsigned char> jpeg;if(!vpu.take(jpeg,3000))fault("Trial VPU warmup deadline");validate(jpeg,*warm);}
   for(unsigned i=0;i<6&&!stopping;++i){
    auto f=camera.next(last);last=f->id;auto p=pl.encode(*f);const double t=now();auto data=nv12(vpu,*f);const double prep=(now()-t)*1000;
    vpu.enqueueDataPtr(reinterpret_cast<char*>(data.data()));std::vector<unsigned char> jpeg;if(!vpu.take(jpeg,3000))fault("Trial VPU encoding deadline");
    const double vpu_ms=(now()-t)*1000;const double pl_psnr=validate(p.first,*f),vpu_psnr=validate(jpeg,*f);pl.verify_source(*f);
    report["pairs"].push_back({{"frame_id",f->id},{"pl",p.second},{"pl_psnr",pl_psnr},{"vpu_ms",vpu_ms},{"vpu_prepare_ms",prep},{"vpu_psnr",vpu_psnr},{"vpu_bytes",jpeg.size()}});
    if(i==5){bytes(workspace/"paired-pl.jpg",p.first);bytes(workspace/"paired-vpu.jpg",jpeg);bytes(workspace/"paired-source.rgb565",f->raw);}
   }
   for(const std::string mode:{"PL_JPG1","VPU_JPEG"}){
    const double start=now();unsigned count=0;Json samples=Json::array();last=0;
    while(!stopping&&now()-start<6){
     auto f=camera.next(last);last=f->id;std::vector<unsigned char> jpeg;Json sample;
     if(mode=="PL_JPG1"){auto result=pl.encode(*f);jpeg=std::move(result.first);sample=result.second;}
     else{const double t=now();auto data=nv12(vpu,*f);vpu.enqueueDataPtr(reinterpret_cast<char*>(data.data()));if(!vpu.take(jpeg,3000))fault("Trial VPU live deadline");sample={{"total_ms",(now()-t)*1000},{"frame_id",f->id},{"bytes",jpeg.size()}};}
     if(count<2)sample["psnr"]=validate(jpeg,*f);
     publish(jpeg,*f,camera,++encoded,mode.c_str());sample["published_at"]=now();samples.push_back(sample);++count;
    }
    report["phases"].push_back({{"encoder",mode},{"frames",count},{"seconds",now()-start},{"fps",count/(now()-start)},{"samples",samples}});
   }
   vpu.streamOff();camera.close();report["captured"]=camera.captured.load();report["camera_requests"]=camera.requests.load();report["camera_drained"]=camera.drained;
  }
  Device::Close(device);report["sdk_closed"]=true;report["passed"]=!stopping;save(workspace/"result.json",report);std::cout<<"WCIS_ENCODER_TRIAL_STOPPED "<<report["captured"]<<std::endl;return stopping?2:0;
 }catch(const std::exception& e){fault(e.what());}
}
