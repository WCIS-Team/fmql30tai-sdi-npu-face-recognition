// SDI capture from the vendor case; VPU JPEG/NV12 contract from repos/vpu-live.
// RGB565 -> NV12 follows its hdmi_display_actor.hpp. No HDMI or model session.
#include "pipeline/io/input/sdicamera.hpp"
#include "pipeline/vpu/vpu.h"
#include "wcis_capture_wait.hpp"
#include "wcis_sdi_diagnostics.hpp"
#include <poll.h>
#include <sys/file.h>
#include <csignal>
#include <deque>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <nlohmann/json.hpp>
namespace fs=std::filesystem;
static volatile std::sig_atomic_t stop_requested=0;
static void signal_stop(int){stop_requested=1;}
static double now(){return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();}
class JpegEncoder:public vpu::Encoder {
public:
 JpegEncoder():Encoder("/dev/video0",540,960,V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE,V4L2_PIX_FMT_NV12,V4L2_BUF_TYPE_VIDEO_CAPTURE,V4L2_PIX_FMT_JPEG,2){
  setFrameRate(5);
  v4l2_control c{};c.id=0x009d0903;c.value=80;
  if(ioctl(fd_,VIDIOC_S_CTRL,&c))throw std::runtime_error("VPU JPEG quality rejected");
  auto& f=input_format_.fmt.pix_mp;
  if(f.width!=960||f.height!=540||(f.num_planes!=1&&f.num_planes!=2)||f.plane_fmt[0].bytesperline!=960||
     (f.num_planes==2&&f.plane_fmt[1].bytesperline!=960))
   throw std::runtime_error("VPU NV12 geometry/stride contract mismatch");
 }
 size_t inputBytes(){size_t n=0;for(auto x:input_buffers.at(0)->byte_per_planes_)n+=x;return n;}
 size_t uvOffset(){return input_format_.fmt.pix_mp.num_planes==2?input_buffers.at(0)->byte_per_planes_.at(0):960*540;}
 bool take(std::vector<unsigned char>& bytes,int timeout){
  pollfd p{fd_,POLLIN,0};int n;
  // A stop requests draining; it must not interrupt dequeuing queued outputs.
  do {n=poll(&p,1,timeout);}while(n<0&&errno==EINTR);
  if(n==0)return false;
  if(n<0||!(p.revents&POLLIN))throw std::runtime_error("VPU output poll failed");
  v4l2_buffer b{};b.type=V4L2_BUF_TYPE_VIDEO_CAPTURE;b.memory=V4L2_MEMORY_MMAP;
  if(ioctl(fd_,VIDIOC_DQBUF,&b))throw std::runtime_error("VPU output dequeue failed");
  auto it=output_buffers.find(b.index);
  if(it==output_buffers.end())throw std::runtime_error("VPU output buffer index invalid");
  size_t offset=b.m.offset&4095,capacity=it->second->byte_per_planes_.at(0);
  if(offset>capacity||b.bytesused>capacity-offset||b.bytesused>5*1024*1024)throw std::runtime_error("VPU output bounds invalid");
  auto ptr=static_cast<unsigned char*>(it->second->ptr_[0])+offset;
  // Own the JPEG bytes before returning the mapped buffer to the driver.
  bytes.assign(ptr,ptr+b.bytesused);
  if(ioctl(fd_,VIDIOC_QBUF,&b))throw std::runtime_error("VPU output requeue failed");
  if(bytes.size()<4||bytes[0]!=255||bytes[1]!=216||bytes[bytes.size()-2]!=255||bytes.back()!=217)
   throw std::runtime_error("VPU did not produce one complete JPEG");
  return true;
 }
};
int main(int argc,char** argv){
 if(argc!=5&&argc!=6){std::cerr<<"Usage: wcis_sdi_vpu_live camera|vtc EXPECTED_BOOT OUTDIR FRAME_LIMIT(0=continuous) [warm]\n";return 2;}
 std::string source=argv[1],boot;std::ifstream("/proc/sys/kernel/random/boot_id")>>boot;
 if((source!="camera"&&source!="vtc")||boot.empty()||boot!=argv[2])return 2;
 // The launcher supplies this only after checking the exact factory BOOT for
 // this boot ID. That image predates SDI2; its real input was tested separately.
 const char* factory_boot=getenv("WCIS_VERIFIED_FACTORY_BOOT");
 const bool factory_input=factory_boot&&std::string(factory_boot)==
  "0088581b738fdef741983d2dfd4dd52363d2d90fddc2fa4dafb30cfdb3b23fca";
 for(const char* name:{"WCIS_NPU_LOCK_FD","WCIS_CAMERA_LOCK_FD"}){
  auto value=getenv(name);if(!value)return 2;int fd=atoi(value);
  if(fd<3||fcntl(fd,F_GETFD)<0||flock(fd,LOCK_EX|LOCK_NB))return 2;
 }
 const int limit=std::stoi(argv[4]);if(limit<0||limit>3600)return 2;
 const bool warm=argc==6&&std::string(argv[5])=="warm";
 if(argc==6&&(!warm||source!="camera"||limit))return 2;
 fs::path out=argv[3];if(out.string().find("/dev/shm/wcis-")!=0)return 2;
 fs::create_directories(out);
 std::signal(SIGINT,signal_stop);std::signal(SIGTERM,signal_stop);
 unsigned captured=0,encoded=0;bool pending=false,configured=false;std::unique_ptr<JpegEncoder> encoder;
 struct Frame{unsigned id;double captured_at;};std::deque<Frame> queue;
 auto metadata=[&](const char* state,unsigned id,double timestamp){
  return std::string("{\"source\":\"")+source+"\",\"state\":\""+state+"\",\"boot_id\":\""+boot+"\",\"pid\":"+std::to_string(getpid())+
   ",\"frame_id\":"+std::to_string(id)+",\"captured\":"+std::to_string(captured)+",\"encoded\":"+std::to_string(encoded)+
   ",\"width\":960,\"height\":540,\"fps_limit\":5,\"captured_at\":"+std::to_string(timestamp)+",\"updated_at\":"+std::to_string(now())+"}";
 };
 auto status=[&](const char* state){std::ofstream f(out/"status.tmp");f<<metadata(state,encoded,0);f.close();fs::rename(out/"status.tmp",out/"status.json");};
 using Json=nlohmann::json;
 auto command=[&](const char* name,const std::string& expected){
  const auto path=out/name;if(!fs::exists(path))return std::string();
  if(fs::file_size(path)>4096)throw std::runtime_error("Camera handoff command too large");
  std::ifstream file(path);Json q;file>>q;auto token=q.at("token").get<std::string>();
  if(q.at("pid")!=getpid()||q.at("boot_id")!=boot||token.size()!=32||
     token.find_first_not_of("0123456789abcdef")!=std::string::npos||(!expected.empty()&&token!=expected))
   throw std::runtime_error("Invalid camera handoff command");
  fs::remove(path);return token;
 };
 status("starting");
 try{
 for(;;){
  std::string pause_token;
  auto device=icraft::xrt::Device::Open("axi://zg330aiu?npu=0x40000000&dma=0x80000000");
  {
  auto fpai=device.cast<fpai::FPAIDevice>();auto regs=fpai.defaultRegRegion();constexpr uint64_t base=0x40080000;
  auto read=[&](uint32_t offset){return static_cast<uint32_t>(regs.read(base+offset));};
  if(read(0x0c)!=0x20230218||read(4)||read(8)||read(0x44)||read(0x70))throw std::runtime_error("camera version/busy state mismatch");
  auto chunk=fpai.getMemRegion("udma").malloc(960*540*2,false);
  auto address=chunk->begin.addr();if(address%8||address<0x30100000||address+960*540*2>0x38100000)throw std::runtime_error("unverified UDMA allocation");
  fpai::GenericSDICamera camera(0,fpai,1920,1080,camera_fmt::RGB565,960,540,camera_fmt::RGB565,crop_position::center,640,352,crop_position::center,base,source=="vtc");
  configured=true;regs.write(base+0x44,0);regs.write(base+8,0);
  if((read(0xb4)&1)!=(source=="vtc"))throw std::runtime_error("source selection readback mismatch");
  std::vector<unsigned char> raw(960*540*2),nv12;cv::Mat bgr,i420;
  auto publish=[&](int wait){
   std::vector<unsigned char> jpeg;if(!encoder->take(jpeg,wait))return false;
   if(queue.empty())throw std::runtime_error("VPU output has no source frame identity");
   auto frame=queue.front();queue.pop_front();++encoded;
   if(encoded==1){auto decoded=cv::imdecode(jpeg,cv::IMREAD_COLOR);if(decoded.cols!=960||decoded.rows!=540)throw std::runtime_error("VPU JPEG decode check failed");}
   auto info=metadata("ready",frame.id,frame.captured_at);uint32_t len=info.size();
   std::ofstream f(out/"latest.tmp",std::ios::binary);f.write(reinterpret_cast<char*>(&len),4);f.write(info.data(),info.size());f.write(reinterpret_cast<char*>(jpeg.data()),jpeg.size());f.close();
   if(!f)throw std::runtime_error("frame packet write failed");fs::rename(out/"latest.tmp",out/"latest.frame");status("ready");return true;
  };
  while(!stop_requested&&(!limit||captured<static_cast<unsigned>(limit))){
   // The vendor encoder starts after two input buffers. A photo request may
   // arrive during warm-up; finish that minimum before admitting a pause.
   if(warm&&(!encoder||encoder->streamon_flag_.load())){
    pause_token=command("pause.request","");if(!pause_token.empty())break;
   }
   if(source=="camera"&&!factory_input){
    auto diag=wcis::read_sdi_diagnostics([&](uint64_t address){return static_cast<uint32_t>(regs.read(address));},base);
    if(diag.state!=wcis::SdiReadState::Ready)throw std::runtime_error("SDI2 input monitor unavailable; capture not requested");
    if((diag.words[2]&3)!=3||!(diag.words[6]&1)){
     status("waiting_for_sdi_lock");std::this_thread::sleep_for(std::chrono::milliseconds(200));continue;
    }
    if(diag.words[11]!=((1080u<<16)|1920u)){
     status("input_format_mismatch");std::this_thread::sleep_for(std::chrono::milliseconds(200));continue;
    }
   }
   if(stop_requested)break;
   double start=now();pending=true;
   wcis::CaptureResult result;
   try {
    camera.take(chunk);
    // Once take() issues a DMA request, drain it even if SIGTERM arrives.
    // The outer loop stops admission; a real timeout still quarantines hardware.
    result=wcis::wait_capture([&]{return read(0x58);},[]{return false;},2000,true);
   }catch(...){status("capture_failed_requires_reboot");std::_Exit(3);}
   if(result.state!=wcis::CaptureState::Done){status("capture_failed_requires_reboot");std::cerr<<"CAPTURE_FAILED status="<<result.status<<" captured="<<captured<<"; no retry\n"<<std::flush;std::_Exit(3);}
   pending=false;++captured;Frame frame{captured,now()};chunk.read(reinterpret_cast<char*>(raw.data()),0,raw.size());
   cv::Mat input(540,960,CV_8UC2,raw.data());cv::cvtColor(input,bgr,cv::COLOR_BGR5652BGR);cv::cvtColor(bgr,i420,cv::COLOR_BGR2YUV_I420);
   if(!encoder){encoder=std::make_unique<JpegEncoder>();size_t size=encoder->inputBytes();if(size<960*540*3/2||size>16*1024*1024)throw std::runtime_error("VPU input buffer size mismatch");nv12.resize(size);}
   constexpr size_t y=960*540;size_t uv=encoder->uvOffset();
   if(uv<y||uv+y/2>nv12.size())throw std::runtime_error("VPU NV12 plane bounds mismatch");
   std::memcpy(nv12.data(),i420.data,y);
   for(size_t i=0;i<y/4;++i){nv12[uv+2*i]=i420.data[y+i];nv12[uv+2*i+1]=i420.data[y+y/4+i];}
   if(queue.size()>=6)throw std::runtime_error("VPU output stalled");queue.push_back(frame);encoder->enqueueDataPtr(reinterpret_cast<char*>(nv12.data()));
   if(encoder->streamon_flag_.load())publish(1500);
   while(encoder->streamon_flag_.load()&&publish(0)){}
   while(!stop_requested&&now()-start<.2)std::this_thread::sleep_for(std::chrono::milliseconds(5));
  }
  if(encoder){while(!queue.empty()&&publish(1500)){}encoder->streamOff();encoder.reset();}
  regs.write(base+0xb4,0);regs.write(base+0x18,0);status("stopped");
  }
  // Destroy camera, allocator chunks and register handles before closing the
  // shared SDK device. Publish a pause receipt only after releasing its lock.
  icraft::xrt::Device::Close(device);
  if(!pause_token.empty()&&!stop_requested){
   if(!queue.empty())throw std::runtime_error("Camera has undrained VPU outputs");
   fs::remove(out/"latest.frame");status("paused");
   const int lock_fd=atoi(getenv("WCIS_NPU_LOCK_FD"));
   if(flock(lock_fd,LOCK_UN))throw std::runtime_error("Camera hardware unlock failed");
   {
    std::ofstream receipt(out/"paused.tmp");
    receipt<<Json{{"boot_id",boot},{"pid",getpid()},{"token",pause_token},{"device_closed",true},{"frame_id",captured}};
    receipt.close();if(!receipt)throw std::runtime_error("Camera pause receipt write failed");
    fs::rename(out/"paused.tmp",out/"paused.json");
   }
   bool resumed=false;
   while(!stop_requested){
    if(!command("resume.request",pause_token).empty()){
     const fs::path marker="/root/wcis-face/hardware-review-required.json";
     if(fs::exists(marker)){std::ifstream f(marker);Json q;f>>q;if(q.value("boot_id","")==boot)throw std::runtime_error("Camera hardware is quarantined");}
     if(flock(lock_fd,LOCK_EX|LOCK_NB))throw std::runtime_error("Camera hardware still owned during resume");
     fs::remove(out/"paused.json");status("starting");resumed=true;break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(5));
   }
   if(resumed)continue;
  }
  std::cout<<"RESULT source="<<source<<" captured="<<captured<<" encoded="<<encoded<<"\n"<<std::flush;
  return (encoded||stop_requested)&&queue.empty()?0:4;
 }
 }catch(const std::exception& e){
  status(pending?"capture_failed_requires_reboot":(configured?"hardware_error_requires_review":"startup_failed"));std::cerr<<e.what()<<"\n"<<std::flush;
  if(encoder){try{encoder->streamOff();}catch(...){}encoder.reset();}
  // If capture may still be active, avoid freeing a DMA buffer in stack unwinding.
  std::_Exit(2);
 }
}
