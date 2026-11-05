// One SDK owner. A fixed camera worker never calls the SDK or its allocator.
// Camera frames are selected from one latest slot; model work never queues video.
#include "wcis_owner_kernels.hpp"
#include "wcis_owner_vpu.hpp"
#include "wcis_owner_h264.hpp"
#include "pipeline/io/input/sdicamera.hpp"
#include "wcis_capture_wait.hpp"
#include "wcis_sdi_diagnostics.hpp"
#include "wcis_camera_mmio.hpp"
#include "wcis_prepared_input.hpp"
#include <atomic>
#include <mutex>
#include <sys/file.h>
#include <csignal>
#include <deque>
#include <fcntl.h>
#include <unistd.h>
#include <limits>
#include <cstdlib>
#include <opencv2/imgcodecs.hpp>
#include <arm_neon.h>
using namespace icraft::xrt;
using Json=nlohmann::json;namespace fs=std::filesystem;
static volatile std::sig_atomic_t stopping=0;
static thread_local std::string phase="startup";
static void stop(int){stopping=1;}
static double now(){return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();}
static void emit(const Json& q){std::cout<<"\nWCIS_OWNER_RESULT "<<q.dump()<<std::endl;}
static void write_file(const fs::path& p,const char* data,size_t bytes){std::ofstream f(p,std::ios::binary);f.write(data,bytes);f.close();if(!f)throw std::runtime_error("Owner output write failed");}
#include "wcis_direct_capture.hpp"
struct Captured {uint32_t id;double pts;std::vector<unsigned char> raw,jpeg;double completed_at=0;};
struct OwnedFrame {
 frame_lease::Lease lease;MemChunk chunk;
 void check()const{
  std::array<char,64> head{},tail{};chunk.read(head.data(),0,64);chunk.read(tail.data(),lease.guard_offset,64);
  if(head!=lease.guard()||tail!=lease.guard(true))throw std::runtime_error("Owned frame guard mismatch");
  for(const auto& other:chunk->region.memManager().getAllMemChunk()){
   const auto base=other->begin.addr(),bytes=other->byte_size;
   if(base==lease.base&&bytes==lease.bytes)continue;
   if(base<lease.base+lease.bytes&&lease.base<base+bytes)throw std::runtime_error("Owner allocation overlaps retained frame");
  }
 }
};
class Owner {
 fs::path root,marker;std::string boot;Json config;
 owner_npu::Models models;std::optional<owner_pl::State> frame;
 std::optional<Device> sdk;std::optional<MemChunk> frame_memory;bool camera_enabled,external_preview,cache_sessions=true;
 std::unique_ptr<JpegEncoder> encoder;std::deque<Captured> encoding;
 int raw_fd=-1;uint64_t raw_index=0;std::ofstream raw_journal;
 bool raw_mode=false,raw_packed=false;
 bool h264=false;std::unique_ptr<H264Encoder> h264_encoder;std::thread h264_output,h264_input;
 bool h264_nv12=false,h264_sdk_pause=true,h264_sdk_hooks=false;
 std::atomic<bool> h264_stop{false};std::mutex h264_mutex;std::deque<Captured> h264_pending;
 std::atomic<bool> h264_started{false};std::atomic<unsigned> h264_mapping_frames{0};
 std::atomic<bool> h264_input_stop{false};std::atomic<uint64_t> h264_submitted{0};
 std::atomic<bool> h264_pause{false},h264_input_idle{false};
 std::atomic<unsigned> h264_warm_received{0};
 std::atomic<double> h264_encoded_at{0},h264_origin{0};std::atomic<uint64_t> h264_bytes{0};
 std::shared_ptr<const Captured> latest;std::mutex latest_mutex;
 std::atomic<uint32_t> captured{0},encoded{0};std::atomic<uint64_t> commands{0};double capture_due=0;
 std::vector<MemChunk> camera_memory;std::optional<unsigned> pending_camera;
 double camera_requested_at=0;std::atomic<uint64_t> camera_requests{0};std::atomic<uint32_t> camera_drained{0};unsigned camera_fps=30;
 std::atomic<bool> camera_pending{false},camera_stop{false};std::thread camera_thread;
 std::unique_ptr<CameraMmio> camera_io;std::array<const char*,2> camera_pointers{};std::array<uint32_t,2> camera_addresses{};
 std::unique_ptr<DirectCamera> direct_camera;
 bool mapping_verified=false;std::array<bool,2> mapping_checked{};
 unsigned preview_w=960,preview_h=540;
 size_t CAMERA_BYTES=960*540*2;
 static constexpr uint64_t CAM=0x40080000;
 [[noreturn]] void fault(const std::string& message){
  const Json record={{"boot_id",boot},{"source","camera_single_owner"},{"phase",phase},{"message",message},{"automatic_retry",false}};
  std::ofstream f(marker);f<<record.dump(2);f.close();std::ofstream detail(root/"fault.json");detail<<record.dump(2);detail.close();
  std::ofstream persistent(fs::canonical("/proc/self/exe").parent_path()/(std::to_string(getpid())+"-owner-fault.json"));persistent<<record.dump(2);persistent.close();
  emit({{"status","error"},{"message",message}});std::_Exit(3);
 }
 void guard(){
  if(frame_lease::boot_id()!=boot)throw std::runtime_error("Owner boot changed");
  if(fs::exists(marker)){std::ifstream f(marker);Json q;f>>q;if(q.value("boot_id","")==boot)throw std::runtime_error("Hardware quarantined");}
 }
 Json meta(const char* state,uint32_t id,double pts,double completed=0){return {{"source","camera"},{"state",state},{"boot_id",boot},{"pid",getpid()},
  {"frame_id",id},{"captured",captured.load()},{"encoded",encoded.load()},{"commands",commands.load()},{"width",preview_w},{"height",preview_h},{"fps_limit",camera_fps},
  {"source_view",h264&&preview_w==1920?"full_view_1920x1080":preview_w==1280?"center_crop_1280x720_from_1920x1080":"full_view_960x540"},
  {"codec",raw_mode?(h264_nv12&&!raw_packed?"raw_nv12_external_test":"raw_uyvy_external_test"):h264?"h264":"mjpeg"},{"h264_encoded_at",h264_encoded_at.load()},{"h264_origin",h264_origin.load()},{"h264_bytes",h264_bytes.load()},{"raw_frames_submitted",h264_submitted.load()},{"native_h264_encoding",!raw_mode&&h264},
  {"captured_at",pts},{"capture_completion_observed_at",completed},{"timestamp_basis","capture_request_lower_bound"},
  {"capture_mode","preallocated_ping_pong"},{"capture_scheduler",external_preview?"on_demand":"independent_worker"},{"sdk_calls_on_capture_thread",false},
  {"preview_mode",external_preview?"external_pl":"continuous_vpu"},{"vpu_enabled",!external_preview&&camera_enabled},
  {"camera_mapping_verified",mapping_verified},{"camera_buffers",direct_camera?2:camera_memory.size()},{"camera_pending",camera_pending.load()},
  {"camera_requests",camera_requests.load()},{"camera_drained",camera_drained.load()},{"updated_at",now()},{"owner_protocol",1}};}
 std::shared_ptr<const Captured> snapshot(){std::lock_guard<std::mutex> lock(latest_mutex);return latest;}
 double last_status_at=-1;std::string last_status_state;
 void status(const char* s){
  const double at=now();
  if(last_status_state==s&&last_status_at>=0&&at-last_status_at<1.0)return;
  const auto image=snapshot();std::ofstream f(root/"status.tmp");f<<meta(s,image?image->id:0,image?image->pts:0,image?image->completed_at:0);f.close();
  if(!f)throw std::runtime_error("Owner status write failed");
  fs::rename(root/"status.tmp",root/"status.json");last_status_at=at;last_status_state=s;
 }
 bool publish(int timeout){
  std::vector<unsigned char> jpeg;if(!encoder->take(jpeg,timeout))return false;
  if(encoding.empty())throw std::runtime_error("JPEG lacks captured frame identity");
  Captured image=std::move(encoding.front());encoding.pop_front();image.jpeg=std::move(jpeg);++encoded;
  const auto text=meta("ready",image.id,image.pts,image.completed_at).dump();uint32_t length=text.size();
  std::ofstream f(root/"latest.tmp",std::ios::binary);f.write(reinterpret_cast<const char*>(&length),4);f.write(text.data(),text.size());f.write(reinterpret_cast<const char*>(image.jpeg.data()),image.jpeg.size());f.close();
  if(!f)throw std::runtime_error("Preview packet write failed");fs::rename(root/"latest.tmp",root/"latest.frame");
  {std::lock_guard<std::mutex> lock(latest_mutex);latest=std::make_shared<const Captured>(std::move(image));}status("ready");return true;
 }
 void raw_write(const unsigned char* data,size_t bytes,uint32_t frame_id,double pts){
  if(raw_fd<0||bytes!=size_t(preview_w)*preview_h*(h264_nv12&&!raw_packed?3u:4u)/2u)throw std::runtime_error("External raw sink geometry/state mismatch");
  const double deadline=now()+3;size_t sent=0;
  while(sent<bytes){
   if(now()>deadline)throw std::runtime_error("External raw sink write deadline");
   pollfd p{raw_fd,POLLOUT,0};int ready=poll(&p,1,100);
   if(ready<0&&errno==EINTR)continue;
   if(ready<0||(p.revents&(POLLERR|POLLHUP|POLLNVAL)))throw std::runtime_error("External encoder pipe closed");
   if(!ready)continue;
   const auto n=::write(raw_fd,data+sent,bytes-sent);
   if(n<0&&(errno==EINTR||errno==EAGAIN))continue;
   if(n<=0)throw std::runtime_error("External raw sink write failed");sent+=n;
  }
  raw_journal<<Json{{"input_index",raw_index++},{"frame_id",frame_id},{"captured_at",pts},{"synthetic",frame_id==0}}.dump()<<"\n";raw_journal.flush();
  if(!raw_journal)throw std::runtime_error("External raw journal failed");
  if(raw_index%1800==0){raw_journal.close();fs::rename(root/"raw-inputs.jsonl",root/"raw-inputs.previous.jsonl");raw_journal.open(root/"raw-inputs.jsonl");if(!raw_journal)throw std::runtime_error("External raw journal rotation failed");}
 }
 void start_h264(){
  if(raw_mode){
   if(raw_fd>=0)return;
   const fs::path path=getenv("WCIS_RAW_SINK");if(!fs::is_fifo(path))throw std::runtime_error("External raw sink must be an existing FIFO");
   std::signal(SIGPIPE,SIG_IGN);raw_fd=::open(path.c_str(),O_WRONLY|O_NONBLOCK);
   if(raw_fd<0)throw std::runtime_error("External encoder FIFO reader not ready");
   raw_journal.open(root/"raw-inputs.jsonl");if(!raw_journal)throw std::runtime_error("External raw journal open failed");
   std::cout<<"EXTERNAL_RAW_SINK_OPEN"<<std::endl;return;
  }

  h264_encoder=std::make_unique<H264Encoder>(camera_fps,h264_nv12?V4L2_PIX_FMT_NV12:V4L2_PIX_FMT_UYVY,preview_w,preview_h);
  h264_output=std::thread([this]{try{
   std::vector<unsigned char> parameters;std::unique_ptr<H264SegmentPublisher> mux;double last_output=now();
   const bool raw_only=getenv("WCIS_H264_RAW_ONLY")&&std::string(getenv("WCIS_H264_RAW_ONLY"))=="1";
   std::ofstream probe;if(raw_only)probe.open(root/"probe.h264",std::ios::binary);
   while(!h264_stop){
    if(!h264_encoder->streamon_flag_.load()){std::this_thread::sleep_for(std::chrono::milliseconds(1));continue;}
    std::vector<unsigned char> data;
    if(!h264_encoder->take(data,100)){if(h264_pause)last_output=now();else if(now()-last_output>3)throw std::runtime_error("H264 output stopped advancing");continue;}
    last_output=now();const auto nal=h264_nals(data);
    if(raw_only){probe.write(reinterpret_cast<const char*>(data.data()),data.size());if(!probe)throw std::runtime_error("H264 raw probe write failed");}
    if(!nal.parameters.empty())parameters=nal.parameters;
    if(!nal.vcl)continue;
    Captured image;
    {std::lock_guard<std::mutex> lock(h264_mutex);if(h264_pending.empty())throw std::runtime_error("H264 lacks captured frame identity");image=std::move(h264_pending.front());h264_pending.pop_front();}
    if(image.id==0){++h264_warm_received;continue;}
    if(!encoded.load()){if(!nal.idr)throw std::runtime_error("H264 first frame is not an IDR");h264_origin=image.pts;if(!raw_only)mux=std::make_unique<H264SegmentPublisher>(root/"h264",parameters,image.pts,camera_fps);}
    if(mux)mux->write(data,image.pts,nal.idr,camera_fps);++encoded;h264_encoded_at=image.pts;h264_bytes+=data.size();
    // Runtime's first-output sentinel; H264 media is published as complete HLS fragments.
    if(encoded.load()==1){std::ofstream f(root/"latest.frame");f<<"H264_HLS";}
   }
   if(mux)mux->finish();
  }catch(const std::exception& e){phase="h264_output";fault(e.what());}});
 }
 void prime_h264_before_sdk(){
  if(raw_mode){
   if(sdk)throw std::runtime_error("SDK was opened before external encoder priming");
   start_h264();std::vector<unsigned char> gray(size_t(preview_w)*preview_h*(h264_nv12&&!raw_packed?3:4)/2);
   if(h264_nv12&&!raw_packed){std::fill(gray.begin(),gray.end(),128);std::fill(gray.begin(),gray.begin()+size_t(preview_w)*preview_h,16);}
   else for(size_t i=0;i<gray.size();i+=2){gray[i]=128;gray[i+1]=16;}
   const unsigned warmup=getenv("WCIS_RAW_PRIME_FRAMES")?std::stoul(getenv("WCIS_RAW_PRIME_FRAMES")):30;
   if(warmup!=30&&warmup!=60)throw std::runtime_error("Invalid bounded priming count");
   for(unsigned i=0;i<warmup;++i){raw_write(gray.data(),gray.size(),0,now());std::this_thread::sleep_for(std::chrono::milliseconds(33));}
   const fs::path output=getenv("WCIS_RAW_FIRST_OUTPUT");const double deadline=now()+4;
   while(!fs::exists(output)||fs::file_size(output)==0){if(now()>deadline)throw std::runtime_error("External VPU first output deadline");std::this_thread::sleep_for(std::chrono::milliseconds(20));}
   h264_pause=true;std::cout<<"EXTERNAL_VPU_PRIMED_BEFORE_SDK"<<std::endl;return;
  }

  if(preview_w!=1920||preview_h!=1080||h264_nv12)throw std::runtime_error("VPU-first trial requires 1080p UYVY");
  if(sdk)throw std::runtime_error("SDK was opened before VPU-first priming");
  start_h264();std::vector<unsigned char> gray(CAMERA_BYTES);for(size_t i=0;i<gray.size();i+=2){gray[i]=128;gray[i+1]=16;}
  const double start=now();
  for(unsigned i=0;i<30;++i){
   {std::lock_guard<std::mutex> lock(h264_mutex);h264_pending.push_back(Captured{0,now(),{},{},0});}
   h264_encoder->enqueueDataPtr(reinterpret_cast<char*>(gray.data()));
   std::this_thread::sleep_until(std::chrono::steady_clock::time_point(std::chrono::duration_cast<std::chrono::steady_clock::duration>(std::chrono::duration<double>(start+(i+1)/30.0))));
  }
  const double deadline=now()+3;while(h264_warm_received<30){if(now()>deadline)throw std::runtime_error("VPU-first synthetic priming did not drain");std::this_thread::sleep_for(std::chrono::milliseconds(1));}
  h264_pause=true;
  std::cout<<"VPU_FIRST_PRIMED "<<Json{{"frames",h264_warm_received.load()},{"source","synthetic_gray_not_camera"},{"sdk_opened",bool(sdk)}}.dump()<<std::endl;
 }
 void stop_h264(){
  if(raw_mode){if(raw_fd>=0){::close(raw_fd);raw_fd=-1;}raw_journal.close();return;}

  if(!h264_encoder)return;
  const double deadline=now()+3;
  for(;;){bool empty;{std::lock_guard<std::mutex> lock(h264_mutex);empty=h264_pending.empty();}if(empty)break;if(now()>deadline)throw std::runtime_error("H264 shutdown did not drain");std::this_thread::sleep_for(std::chrono::milliseconds(10));}
  h264_stop=true;if(h264_output.joinable())h264_output.join();h264_encoder->streamOff();h264_encoder.reset();
 }
 void pause_h264_camera_for_command(){
  if(!h264||h264_pause)return;
  h264_pause=true;direct_camera->pause();camera_pending=false;
  const double deadline=now()+3;
  while(!h264_input_idle){if(now()>deadline)throw std::runtime_error("H264 input failed to pause at command boundary");std::this_thread::sleep_for(std::chrono::milliseconds(1));}
 }
 void pause_h264_for_sdk(){
  if(!h264||h264_pause)return;h264_pause=true;if(direct_camera){direct_camera->pause();camera_pending=false;}const double deadline=now()+3;
  while(!h264_input_idle||encoded.load()<h264_submitted.load()){
   if(now()>deadline)throw std::runtime_error("H264 did not quiesce before SDK command: idle="+std::to_string(h264_input_idle.load())+" encoded="+std::to_string(encoded.load())+" submitted="+std::to_string(h264_submitted.load()));std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
 }
 Device open(){guard();if(!sdk)sdk=Device::Open("axi://zg330aiu?npu=0x40000000&dma=0x80000000");return *sdk;}
 std::optional<OwnedFrame> reserve(const Device&){
  std::optional<OwnedFrame> held;if(frame){if(!frame_memory)throw std::runtime_error("Owner frame allocation missing");held=OwnedFrame{frame->lease,*frame_memory};held->check();}return held;
 }
 void owned_path(const Json& q,const char* key){
  const fs::path p=q.at(key).get<std::string>();const auto canonical=fs::weakly_canonical(p),base=fs::weakly_canonical(root);
  const auto relative=canonical.lexically_relative(base);
  if(relative.empty()||relative.is_absolute()||*relative.begin()=="..")throw std::runtime_error("Command path outside owner workspace");
 }
 void fused_forward(Json& result,Device device,const Json& q,const std::vector<char>& pixels){
  if(!q.contains("forward_role"))return;
  const std::string role=q.at("forward_role").get<std::string>();
  if(role!="yunet"&&role!="mobilefacenet")throw std::runtime_error("Unsupported fused model role");
  const auto size=role=="yunet"?640u:112u;
  if(q.at("canvas_w")!=size||q.at("canvas_h")!=size||pixels.size()!=size*size*4)throw std::runtime_error("Fused geometry/model mismatch");
  const auto geometry=device.cast<ZG330Device>().getRowsCols();if(config.at("rows")!=geometry.first||config.at("cols")!=geometry.second)throw std::runtime_error("Fused owner MPE geometry mismatch");
  owned_path(q,"forward_output_directory");
  const std::string token=q.at("forward_token").get<std::string>();if(!frame_lease::valid_token(token))throw std::runtime_error("Invalid fused input token");
  const auto start=now();auto values=wcis_prepare_input(pixels,role=="mobilefacenet");
  if(q.contains("verify_input_f32")){owned_path(q,"verify_input_f32");write_file(q.at("verify_input_f32").get<std::string>(),reinterpret_cast<const char*>(values.data()),values.size()*sizeof(float));}
  const auto dtype=models.at(role)->network.inputs()[0].tensorType();auto host=HostDevice::MemRegion().malloc(values.size()*sizeof(float));
  host.write(0,reinterpret_cast<char*>(values.data()),values.size()*sizeof(float));Tensor tensor(dtype,host);
  Json request={{"role",role},{"output_directory",q.at("forward_output_directory")},{"profile",q.value("profile",false)}};auto held=reserve(device);
  auto reply=owner_npu::forward(*models.at(role),device,request,&*held,&tensor);held->check();
  reply["frame_id"]=frame->lease.id;reply["frame_token"]=frame->lease.token;reply["frame_preserved"]=true;reply["worker_pid"]=getpid();
  reply["single_owner"]=true;reply["device_closed"]=false;reply["forward_token"]=token;reply["input_transport"]="native_host_memory";
  reply["input_tensor_bytes"]=values.size()*sizeof(float);reply["prepared_forward_ms"]=(now()-start)*1000;
  result["forward_result"]=std::move(reply);result["pixels_materialized"]=q.value("write_output",true);
 }
public:
 Owner(fs::path r,fs::path manifest,std::string b,bool camera,bool external=false):root(std::move(r)),marker("/root/wcis-face/hardware-review-required.json"),boot(std::move(b)),camera_enabled(camera),external_preview(external){
  if(const char* value=getenv("WCIS_PREVIEW_CODEC")){const std::string codec=value;if(codec=="h264")h264=true;else if(codec!="mjpeg")throw std::runtime_error("Unsupported preview codec");}
  if(const char* value=getenv("WCIS_H264_INPUT")){const std::string format=value;if(format=="nv12")h264_nv12=true;else if(format!="uyvy")throw std::runtime_error("Unsupported H264 input");}
  raw_mode=getenv("WCIS_RAW_SINK")&&getenv("WCIS_RAW_FIRST_OUTPUT");raw_packed=raw_mode&&getenv("WCIS_RAW_PACKED_UYVY")&&std::string(getenv("WCIS_RAW_PACKED_UYVY"))=="1";if(raw_mode&&!h264)throw std::runtime_error("External raw test requires UYVY H264 route");
  if(const char* value=getenv("WCIS_H264_SDK_PAUSE")){const std::string flag=value;if(flag!="0"&&flag!="1"&&flag!="hooks")throw std::runtime_error("Invalid H264 SDK pause flag");h264_sdk_pause=flag=="1";h264_sdk_hooks=flag=="hooks";}
  if(const char* value=getenv("WCIS_PREVIEW_SIZE")){
   const std::string size=value;
   if(size=="1080"&&h264){preview_w=1920;preview_h=1080;CAMERA_BYTES=size_t(preview_w)*preview_h*2;}
   else if(size=="720"){preview_w=1280;preview_h=720;CAMERA_BYTES=size_t(preview_w)*preview_h*2;}
   else if(size!="540")throw std::runtime_error("Preview size must be 540 or 720");
  }
  if(h264&&external_preview)throw std::runtime_error("H264 requires the VPU preview route");
  if(h264&&preview_w==960){if(!h264_nv12||h264_sdk_hooks)throw std::runtime_error("540p H264 uses the existing NV12 path");h264_sdk_pause=false;}
  else if(h264&&preview_w!=1920)throw std::runtime_error("Direct H264 route requires full-view 1080p");
  if(h264&&h264_sdk_hooks){owner_npu::before_exclusive=[this]{pause_h264_for_sdk();};owner_npu::after_exclusive=[this]{if(h264_pause){direct_camera->resume();camera_pending=true;h264_pause=false;}};}
  if(external_preview&&preview_w!=960)throw std::runtime_error("720p crop requires the VPU preview route");
  if(const char* value=getenv("WCIS_OPENCV_THREADS")){
   const int threads=std::stoi(value);if(threads<1||threads>4)throw std::runtime_error("OpenCV thread count outside 1..4");
   cv::setNumThreads(threads);
  }else cv::setNumThreads(2);
  if(const char* value=getenv("WCIS_CAMERA_FPS")){const int fps=std::stoi(value);if(fps<1||fps>30)throw std::runtime_error("Camera FPS outside 1..30");camera_fps=fps;}
  guard();std::ifstream f(manifest);f>>config;
  if(config.at("schema_version")!=1||config.at("generated")!=true)throw std::runtime_error("Unvalidated model manifest");
  if(const char* value=getenv("WCIS_OWNER_SESSION_CACHE")){
   const std::string policy=value;if(policy!="0"&&policy!="1")throw std::runtime_error("Invalid owner session cache policy");
   cache_sessions=policy=="1";
  }
  // Sessions are lazy and remain on this same device; no concurrent SDK calls.
  for(const std::string role:{"yunet","mobilefacenet"}){
   const auto& record=config.at("models").at(role);auto m=std::make_unique<owner_npu::Model>();m->cache_session=cache_sessions;
   m->network=icraft::xir::Network::CreateFromJsonFile((manifest.parent_path()/record.at("json").get<std::string>()).string());
   m->network.lazyLoadParamsFromFile((manifest.parent_path()/record.at("raw").get<std::string>()).string());
   const int size=role=="yunet"?640:112;const auto inputs=m->network.inputs(),outputs=m->network.outputs();
   if(inputs.size()!=1||!inputs[0].tensorType()->element_dtype.isFP32()||inputs[0].tensorType().numElements()!=size*size*3)throw std::runtime_error("Owner model input contract");
   const auto shape=inputs[0].tensorType()->shape;if(shape.size()!=4||shape[0]!=1||shape[1]!=size||shape[2]!=size||shape[3]!=3)throw std::runtime_error("Owner model NHWC contract");
   for(const auto& op:m->network->ops)if(op.is<icraft::xir::HardOp>())++m->hard_ops;
   if(!m->hard_ops||outputs.size()!=(role=="yunet"?12:1))throw std::runtime_error("Owner model hardware/output contract");
   for(const auto& output:outputs)if(!output.tensorType()->element_dtype.isFP32())throw std::runtime_error("Owner output dtype contract");
   models.emplace(role,std::move(m));
  }
  bool pad_loaded=false;
  if(const char* value=getenv("WCIS_OWNER_PAD_MANIFEST")){
   const fs::path pad_manifest=value;std::ifstream source(pad_manifest);Json pad;source>>pad;
   if(pad.at("generated")!=true||pad.at("upstream_commit")!="b6d5f04ad78778917853b25c778acef6d5626d15"||
      pad.at("rows")!=config.at("rows")||pad.at("cols")!=config.at("cols"))throw std::runtime_error("PAD bundle geometry/version mismatch");
   const auto base=fs::canonical(pad_manifest.parent_path());
   for(const std::string role:{"MiniFASNetV2","MiniFASNetV1SE"}){
    const auto& record=pad.at("models").at(role);auto path=[&](const char* key){
     const auto p=fs::canonical(base/record.at(key).get<std::string>());const auto relative=p.lexically_relative(base);
     if(relative.empty()||relative.is_absolute()||*relative.begin()=="..")throw std::runtime_error("PAD model path outside bundle");return p.string();};
    auto m=std::make_unique<owner_npu::Model>();m->cache_session=cache_sessions;m->network=icraft::xir::Network::CreateFromJsonFile(path("json"));m->network.lazyLoadParamsFromFile(path("raw"));
    const auto inputs=m->network.inputs(),outputs=m->network.outputs();
    if(inputs.size()!=1||outputs.size()!=1||!inputs[0].tensorType()->element_dtype.isFP32()||
       !outputs[0].tensorType()->element_dtype.isFP32()||outputs[0].tensorType().numElements()!=3)throw std::runtime_error("PAD model tensor contract");
    const auto shape=inputs[0].tensorType()->shape;
    if(shape.size()!=4||shape[0]!=1||shape[1]!=80||shape[2]!=80||shape[3]!=3)throw std::runtime_error("PAD model NHWC contract");
    for(const auto& op:m->network->ops)if(op.is<icraft::xir::HardOp>())++m->hard_ops;
    if(!m->hard_ops)throw std::runtime_error("PAD model has no NPU operation");models.emplace(role,std::move(m));
   }
   pad_loaded=true;
  }
  fs::create_directories(root);status("starting");emit({{"status","ready"},{"boot_id",boot},{"pid",getpid()},{"device_opened",false},{"protocol",2},{"single_sdk_owner",true},{"fused_prepared_inputs",true},{"external_pl_preview",external_preview},{"pad_models_loaded",pad_loaded},{"session_cache_enabled",cache_sessions},{"session_cache_scope","camera_960x540_rgb565"}});
 }
 void configure_camera(const Device& device){
   if(!camera_memory.empty())return;
   auto fpai=device.cast<fpai::FPAIDevice>();auto regs=fpai.defaultRegRegion();
   auto read=[&](uint32_t off){return static_cast<uint32_t>(regs.read(CAM+off));};
   if(read(0x0c)!=0x20230218||read(4)||read(8)||read(0x44)||read(0x70))throw std::runtime_error("Owner camera firmware/busy mismatch");
   for(unsigned index=0;index<2;++index){
    auto memory=fpai.getMemRegion("udma").malloc(CAMERA_BYTES,true,64);const auto address=memory->begin.addr();
    if(address%64||address<0x30100000||address+CAMERA_BYTES>0x38100000)throw std::runtime_error("Owner UDMA allocation outside verified window");
    for(const auto& other:camera_memory)if(address<other->begin.addr()+CAMERA_BYTES&&other->begin.addr()<address+CAMERA_BYTES)throw std::runtime_error("Camera buffers overlap");
    camera_memory.push_back(memory);
   }
   // The vendor constructor also enables its legacy PL->ImageMake branch
   // (hardResizePL writes CAM+0x18=1). This path consumes our retained FAC1
   // frame instead, so configure only the documented resizePS registers.
   const std::vector<std::pair<uint32_t,uint32_t>> setup={
    {0x18,0},{0x44,0},{0x08,0},{0xb4,0},
    {0x5c,preview_w==1280?(320u<<16)|1599u:1919u},{0x60,preview_w==1280?(180u<<16)|899u:1079u},
    {0x64,(1920u<<16)|1080u},{0x68,preview_w==960?0x22u:0x11u},{0x78,h264&&preview_w==1920?1u:0u},{0x6c,uint32_t(CAMERA_BYTES/8)}};
   for(const auto& word:setup)regs.write(CAM+word.first,word.second);
   for(const auto& word:setup)if(read(word.first)!=word.second)throw std::runtime_error("Owner PS capture configuration mismatch");
   if(h264){regs.write(CAM+0x7c,preview_w);if(read(0x7c)!=preview_w)throw std::runtime_error("1080p UYVY row width mismatch");}
 }
 void arm_camera(unsigned index){
   if(pending_camera||index>=camera_memory.size())throw std::runtime_error("Camera buffer is already owned by DMA");
   auto& regs=*camera_io;
   if(regs.read(4)||regs.read(8)||regs.read(0x18)||regs.read(0x44)||regs.read(0x70))throw std::runtime_error("Camera request would overlap a busy branch");
   auto diag=wcis::read_sdi_diagnostics([&](uint64_t a){return regs.read(a-CAM);},CAM);
   if(diag.state!=wcis::SdiReadState::Ready||(diag.words[2]&3)!=3||!(diag.words[6]&1)||diag.words[11]!=((1080u<<16)|1920u))throw std::runtime_error("Owner SDI input not locked at 1080p");
   camera_requested_at=now();pending_camera=index;camera_pending=true;++camera_requests;phase="capture_arm";
   regs.write(0x50,camera_addresses[index]>>3);regs.write(4,1);
   // Observe this request clearing DONE now; a later model call may span its
   // entire transfer. Never mistake a previous request's DONE for completion.
   const double deadline=now()+.01;
   while(regs.read(0x58)&1)if(now()>deadline)fault("Camera request did not clear stale completion");
 }
 void drain_camera(){
   if(!pending_camera)return;
   phase="capture_dma";auto& regs=*camera_io;
   if(now()-camera_requested_at>2)fault("Pending camera request exceeded its lifetime");
   auto result=wcis::wait_capture([&]{return regs.read(0x58);},[]{return false;},2000,false);
   if(result.state!=wcis::CaptureState::Done)fault("Owner camera DMA failed; no retry");
   pending_camera.reset();camera_pending=false;
 }
 void capture(bool verify_mapping=false){
  guard();phase="capture_before";const double started=now();std::vector<unsigned char> raw(CAMERA_BYTES);
  if(!pending_camera)arm_camera(external_preview?captured.load()%2:0);
  const unsigned index=*pending_camera;const double pts=camera_requested_at;drain_camera();const double completed=now();
  // The other DMA buffer can fill while PS copies/encodes this completed one.
  // Only after this read finishes can a subsequent call reuse this buffer.
  if(!external_preview)arm_camera(1-index);
  CameraMmio::before_copy();std::memcpy(raw.data(),camera_pointers[index],raw.size());
  // Only the SDK main thread performs this startup check. The worker uses the
  // same stable mapped UDMA pointers as the vendor's PS/VPU actors.
  if(verify_mapping||(external_preview&&!mapping_checked[index])){
   std::vector<unsigned char> reference(CAMERA_BYTES);camera_memory[index].read(reinterpret_cast<char*>(reference.data()),0,reference.size());
   if(reference!=raw)throw std::runtime_error("Mapped camera bytes differ from SDK readback");mapping_checked[index]=true;mapping_verified=mapping_checked[0]&&mapping_checked[1];
  }
  ++captured;Captured source{captured.load(),pts,std::move(raw),{},completed};
  if(h264){
   auto image=std::make_shared<const Captured>(std::move(source));
   if(!h264_started.load())++h264_mapping_frames;
   {std::lock_guard<std::mutex> lock(latest_mutex);latest=image;}
   status((encoded.load()||(raw_mode&&h264_submitted.load()))?"ready":"starting");capture_due=started+1.0/camera_fps;return;
  }
  cv::Mat input(preview_h,preview_w,CV_8UC2,source.raw.data()),bgr,i420;cv::cvtColor(input,bgr,cv::COLOR_BGR5652BGR);
  if(external_preview){
   // One result thumbnail per recognition request. Continuous full-HD preview
   // runs independently in PL; this branch never opens the VPU or arms ahead.
   if(!cv::imencode(".jpg",bgr,source.jpeg,{cv::IMWRITE_JPEG_QUALITY,80})||source.jpeg.empty()||source.jpeg.size()>2*1024*1024)
    throw std::runtime_error("On-demand result JPEG failed");
   ++encoded;{std::lock_guard<std::mutex> lock(latest_mutex);latest=std::make_shared<const Captured>(std::move(source));}
   status("ready");return;
  }
  cv::cvtColor(bgr,i420,cv::COLOR_BGR2YUV_I420);
  if(!encoder)encoder=std::make_unique<JpegEncoder>(camera_fps,preview_w,preview_h);
  const size_t size=encoder->inputBytes(),uv=encoder->uvOffset(),y=size_t(preview_w)*preview_h;
  if(size<y*3/2||size>16*1024*1024||uv<y||uv+y/2>size)throw std::runtime_error("Owner VPU NV12 bounds mismatch");
  std::vector<unsigned char> nv12(size);std::memcpy(nv12.data(),i420.data,y);
  for(size_t i=0;i<y/4;++i){nv12[uv+2*i]=i420.data[y+i];nv12[uv+2*i+1]=i420.data[y+y/4+i];}
  if(encoding.size()>=6)throw std::runtime_error("Owner VPU stalled");encoding.push_back(std::move(source));encoder->enqueueDataPtr(reinterpret_cast<char*>(nv12.data()));
  if(encoder->streamon_flag_.load())publish(1500);
  while(encoder->streamon_flag_.load()&&publish(0)){}
  capture_due=started+1.0/camera_fps;
 }
 void start_camera(){
  if(h264&&preview_w==1920){
   auto device=open();direct_camera=std::make_unique<DirectCamera>(device,[this](const std::string& e){fault(e);});mapping_verified=true;
   if(!h264_encoder)start_h264();h264_started=true;h264_pause=false;
   h264_input=std::thread([this]{try{uint32_t last=0;while(!h264_input_stop){
    if(h264_pause){h264_input_idle=true;std::this_thread::sleep_for(std::chrono::milliseconds(1));continue;}h264_input_idle=false;
    const auto source=direct_camera->peek();if(!source||source->id<=last){std::this_thread::sleep_for(std::chrono::milliseconds(1));continue;}auto image=std::make_shared<const Captured>(Captured{source->id,source->requested,source->raw,{},source->completed});
    if(h264_pause)continue;
    captured=direct_camera->captured.load();camera_requests=direct_camera->requests.load();camera_pending=true;
    if(raw_mode){
     {std::lock_guard<std::mutex> lock(latest_mutex);latest=image;}
     raw_write(image->raw.data(),image->raw.size(),image->id,image->pts);++h264_submitted;last=image->id;
     if(h264_submitted==1){std::ofstream f(root/"latest.frame");f<<"EXTERNAL_RAW_PUMP";}
     status("ready");continue;
    }

    if(!raw_mode){std::lock_guard<std::mutex> lock(h264_mutex);if(h264_pending.size()>=24)throw std::runtime_error("H264 input queue exceeded bound");h264_pending.push_back(Captured{image->id,image->pts,{},{},image->completed_at});}
    {std::lock_guard<std::mutex> lock(latest_mutex);latest=image;}
    if(h264_nv12){
     std::vector<unsigned char> packed(h264_encoder->inputBytes());const auto uv=h264_encoder->uvOffset();
     if(uv<1920*1080||uv+1920*540>packed.size())throw std::runtime_error("NV12 chroma bounds mismatch");
     for(size_t y=0;y<1080;y+=2)for(size_t x=0;x<1920;x+=16){const auto a=vld2q_u8(image->raw.data()+(y*1920+x)*2),b=vld2q_u8(image->raw.data()+((y+1)*1920+x)*2);vst1q_u8(packed.data()+y*1920+x,a.val[1]);vst1q_u8(packed.data()+(y+1)*1920+x,b.val[1]);vst1q_u8(packed.data()+uv+y/2*1920+x,vrhaddq_u8(a.val[0],b.val[0]));}
     h264_encoder->enqueueDataPtr(reinterpret_cast<char*>(packed.data()));
    }else h264_encoder->enqueueDataPtr(reinterpret_cast<char*>(const_cast<unsigned char*>(image->raw.data())));
    ++h264_submitted;last=image->id;status("ready");
   }}catch(const std::exception& e){phase="h264_input";fault(e.what());}});return;
  }
  auto device=open();configure_camera(device);camera_io=std::make_unique<CameraMmio>();
  // Check both access paths before allowing any direct camera write.
  for(uint32_t offset:{0x0cu,0x18u,0x44u,0x50u,0x5cu,0x60u,0x64u,0x68u,0x6cu,0x70u,0x100u,0x104u})
   if(camera_io->read(offset)!=static_cast<uint32_t>(device.defaultRegRegion().read(CAM+offset)))throw std::runtime_error("Camera MMIO differs from admitted SDK mapping");
  for(unsigned i=0;i<2;++i){camera_pointers[i]=camera_memory[i]->begin.cptr();camera_addresses[i]=camera_memory[i]->begin.addr();if(!camera_pointers[i])throw std::runtime_error("Camera UDMA has no CPU mapping");}
  if(external_preview){status("waiting_for_request");return;}
  capture(true);capture(true); // Check the SDK/CPU mapping of both DMA buffers.
  camera_thread=std::thread([this]{
   try{
    while(!camera_stop.load()&&!stopping){
     if(now()>=capture_due)capture();
     else std::this_thread::sleep_for(std::chrono::microseconds(250));
    }
   }catch(const std::exception& e){fault(e.what());}
  });
  if(h264){if(!h264_encoder)start_h264();h264_started=true;h264_pause=false;
   // Keep capture progressing while the vendor API waits for an input buffer.
   // The encoder selects the newest immutable frame; it never queues capture.
   h264_input=std::thread([this]{try{uint32_t last=0;
    // Thread-owned scratch survives frames. raw_write consumes the complete
    // frame before returning; enqueueDataPtr copies into the vendor buffers.
    cv::Mat bgr,i420;
    const size_t y=size_t(preview_w)*preview_h,uv=raw_mode?y:h264_encoder->uvOffset();
    std::vector<unsigned char> packed(raw_mode?(raw_packed?y*2:y*3/2):h264_encoder->inputBytes());
    while(!h264_input_stop){
    const auto image=snapshot();if(!image||image->id<=last){std::this_thread::sleep_for(std::chrono::milliseconds(1));continue;}
    if(!raw_mode){std::lock_guard<std::mutex> lock(h264_mutex);if(h264_pending.size()>=24)throw std::runtime_error("H264 input queue exceeded bound");h264_pending.push_back(Captured{image->id,image->pts,{},{},image->completed_at});}
    cv::Mat input(preview_h,preview_w,CV_8UC2,const_cast<unsigned char*>(image->raw.data()));cv::cvtColor(input,bgr,cv::COLOR_BGR5652BGR);cv::cvtColor(bgr,i420,cv::COLOR_BGR2YUV_I420);
    if(raw_mode&&raw_packed){
     if(preview_w%16||preview_h%2)throw std::runtime_error("Packed UYVY alignment mismatch");
     for(size_t row=0;row<preview_h;++row)for(size_t x=0;x<preview_w;x+=16){
      const auto luma=vld2_u8(i420.data+row*preview_w+x);uint8x8x4_t out;
      out.val[0]=vld1_u8(i420.data+y+(row/2)*(preview_w/2)+x/2);out.val[1]=luma.val[0];
      out.val[2]=vld1_u8(i420.data+y+y/4+(row/2)*(preview_w/2)+x/2);out.val[3]=luma.val[1];
      vst4_u8(packed.data()+(row*preview_w+x)*2,out);
     }
    }else{
     if(uv<y||uv+y/2>packed.size())throw std::runtime_error("540p NV12 chroma bounds mismatch");std::memcpy(packed.data(),i420.data,y);
     for(size_t i=0;i<y/4;++i){packed[uv+2*i]=i420.data[y+i];packed[uv+2*i+1]=i420.data[y+y/4+i];}
    }
    if(raw_mode){raw_write(packed.data(),packed.size(),image->id,image->pts);if(!h264_submitted.load()){std::ofstream f(root/"latest.frame");f<<"EXTERNAL_RAW_PUMP";}}
    else h264_encoder->enqueueDataPtr(reinterpret_cast<char*>(packed.data()));++h264_submitted;last=image->id;
   }}catch(const std::exception& e){phase="h264_input";fault(e.what());}});
  }
 }
 void stop_camera(){camera_stop=true;if(camera_thread.joinable())camera_thread.join();h264_input_stop=true;if(h264_input.joinable())h264_input.join();if(direct_camera){direct_camera->pause();captured=direct_camera->captured.load();camera_requests=direct_camera->requests.load();camera_drained=direct_camera->drained;camera_pending=false;}}
 Json command(const Json& q){
  guard();++commands;const std::string op=q.at("op");phase="command_"+op;
  if(op=="latest"){
   if(external_preview){if(!camera_enabled)throw std::runtime_error("Camera input is disabled");capture();}
   const auto image=snapshot();owned_path(q,"output_directory");if(!image||now()-image->pts>1.5)throw std::runtime_error("No fresh captured frame");
   const fs::path out=q.at("output_directory").get<std::string>();if(fs::exists(out))throw std::runtime_error("Snapshot output already exists");fs::create_directories(out);
   Json frame_meta=meta("ready",image->id,image->pts,image->completed_at);
   if(preview_w==1280||h264){
    cv::Mat packed(preview_h,preview_w,CV_8UC2,const_cast<unsigned char*>(image->raw.data())),bgr,small,repacked;
    cv::cvtColor(packed,bgr,h264&&preview_w==1920?cv::COLOR_YUV2BGR_UYVY:cv::COLOR_BGR5652BGR);cv::resize(bgr,small,cv::Size(960,540),0,0,cv::INTER_AREA);
    cv::cvtColor(small,repacked,cv::COLOR_BGR2BGR565);std::vector<unsigned char> jpeg;
    if(!cv::imencode(".jpg",small,jpeg,{cv::IMWRITE_JPEG_QUALITY,80}))throw std::runtime_error("720p detection snapshot JPEG failed");
    write_file(out/"source.rgb565",reinterpret_cast<const char*>(repacked.data),960*540*2);
    write_file(out/"preview.jpg",reinterpret_cast<const char*>(jpeg.data()),jpeg.size());
    frame_meta["width"]=960;frame_meta["height"]=540;frame_meta["preview_width"]=preview_w;frame_meta["preview_height"]=preview_h;
   }else{
    write_file(out/"source.rgb565",reinterpret_cast<const char*>(image->raw.data()),image->raw.size());
    write_file(out/"preview.jpg",reinterpret_cast<const char*>(image->jpeg.data()),image->jpeg.size());
   }
   return {{"status","snapshot"},{"frame",frame_meta},{"raw_file",(out/"source.rgb565").string()},{"jpeg_file",(out/"preview.jpg").string()},{"sdk_opened",false}};
  }
  if(op=="release"){
   if(!frame||q.at("frame_id")!=frame->lease.id||q.at("frame_token")!=frame->lease.token)throw std::runtime_error("Owner frame release mismatch");
   Json result={{"status","released"},{"frame_id",frame->lease.id},{"frame_token",frame->lease.token},{"source_uploads",1},{"device_opened",true},{"single_owner",true}};frame_memory.reset();frame.reset();return result;
  }
  if(op=="begin"){
   if(frame)throw std::runtime_error("Owner previous frame still leased");owned_path(q,"input_rgbx");owned_path(q,"output_rgbx");
   owner_pl::State fresh{};fresh.input=q.at("input_rgbx").get<std::string>();fresh.marker=marker;
   const auto w=frame_lease::number(q,"src_w"),h=frame_lease::number(q,"src_h"),pitch=frame_lease::number(q,"pitch_bytes");const bool rgb565=q.value("rgb565",false);
   if(!w||!h||w>8192||h>8192||pitch%8||pitch<w*(rgb565?2:4)||pitch>65536)throw std::runtime_error("Owner source geometry invalid");
   const auto bytes=pitch*h,total=128+frame_lease::aligned(bytes)+frame_lease::OUTPUT_CAPACITY;
   if(total>frame_lease::MAX_BYTES||fs::file_size(fresh.input)!=bytes)throw std::runtime_error("Owner source allocation invalid");
   std::vector<char> data(total,static_cast<char>(0xa5));std::ifstream input(fresh.input,std::ios::binary);input.read(data.data()+64,bytes);if(!input)throw std::runtime_error("Owner source read failed");
   auto device=open();owner_pl::checked_firmware(device);Json result;std::vector<char> pixels;
   // The measured camera working set fits its current window. Keep larger
   // photo leases on the old one-session-at-a-time memory budget: release
   // camera caches BEFORE allocating their source and don't cache that frame.
   const bool cache_frame=cache_sessions&&rgb565&&w==960&&h==540&&pitch==1920;
   if(!cache_frame)owner_npu::release_sessions(models);
   for(auto& item:models)item.second->cache_session=cache_frame;
   {
    const auto allocation_start=now();auto memory=device.defaultMemRegion().malloc(total,true,64);const double allocation_ms=(now()-allocation_start)*1000;
    fresh.lease=frame_lease::Lease::parse({{"schema_version",1},{"allocation_base",memory->begin.addr()},{"allocation_bytes",total},{"src_w",w},{"src_h",h},{"pitch_bytes",pitch},{"frame_id",q.at("frame_id")},{"frame_token",q.at("frame_token")},{"boot_id",boot},{"rgb565",rgb565}});
    const auto head=fresh.lease.guard(),tail=fresh.lease.guard(true);std::copy(head.begin(),head.end(),data.begin());std::copy(tail.begin(),tail.end(),data.begin()+fresh.lease.guard_offset);
    const auto upload_start=now();memory.write(0,data.data(),total);const double upload_ms=(now()-upload_start)*1000;frame=std::move(fresh);frame_memory=memory;
    auto held=reserve(device);phase="begin_transform";result=owner_pl::run_transform(*frame,device,memory,q,true,q.contains("forward_role")?&pixels:nullptr);phase="begin_guard";held->check();
    result["source_allocation_ms"]=allocation_ms;result["source_write_ms"]=upload_ms;result["allocation_upload_bytes"]=total;
   }
   fused_forward(result,device,q,pixels);
   result["device_closed"]=false;result["single_owner"]=true;return result;
  }
  if(!frame||q.at("frame_id")!=frame->lease.id||q.at("frame_token")!=frame->lease.token)throw std::runtime_error("Owner command frame mismatch");
  if(op!="transform"&&op!="verify"&&op!="forward")throw std::runtime_error("Unknown owner command");
  if(op=="transform")owned_path(q,"output_rgbx");
  if(op=="forward"){owned_path(q,"input_f32");owned_path(q,"output_directory");}
  auto device=open();Json result;std::vector<char> pixels;
  {
   auto held=reserve(device);
   if(op=="transform"){owner_pl::checked_firmware(device);result=owner_pl::run_transform(*frame,device,held->chunk,q,false,q.contains("forward_role")?&pixels:nullptr);}
   if(op=="verify"){
    std::vector<char> expected(frame->lease.source_bytes),actual(expected.size());std::ifstream f(frame->input,std::ios::binary);f.read(expected.data(),expected.size());if(!f)throw std::runtime_error("Owner verification source read failed");
    held->chunk.read(actual.data(),64,actual.size());if(expected!=actual)fault("Owner full source changed after capture/model handoff");
    result={{"status","verified"},{"full_source_equal",true},{"frame_id",frame->lease.id},{"frame_token",frame->lease.token}};
   }
   if(op=="forward"){
    const auto geometry=device.cast<ZG330Device>().getRowsCols();if(config.at("rows")!=geometry.first||config.at("cols")!=geometry.second)throw std::runtime_error("Owner MPE geometry mismatch");
    result=owner_npu::forward(*models.at(q.at("role").get<std::string>()),device,q,&*held);
    result["frame_id"]=frame->lease.id;result["frame_token"]=frame->lease.token;result["frame_preserved"]=true;result["worker_pid"]=getpid();
   }
   held->check();
  }
  if(op=="transform")fused_forward(result,device,q,pixels);
  result["device_closed"]=false;result["single_owner"]=true;return result;
 }
 int run(double seconds){
  const double deadline=seconds>0?now()+seconds:std::numeric_limits<double>::infinity();
  try{
   if(h264&&getenv("WCIS_H264_VPU_FIRST")&&std::string(getenv("WCIS_H264_VPU_FIRST"))=="1")prime_h264_before_sdk();
   if(h264&&getenv("WCIS_H264_WARMUP")&&std::string(getenv("WCIS_H264_WARMUP"))=="1"){
    if(!cache_sessions)throw std::runtime_error("H264 warmup requires resident model sessions");
    auto device=open();
    for(auto& item:models){
     const auto dtype=item.second->network.inputs()[0].tensorType();std::vector<float> zeros(dtype.numElements(),0.f);
     auto memory=HostDevice::MemRegion().malloc(zeros.size()*sizeof(float));memory.write(0,reinterpret_cast<char*>(zeros.data()),zeros.size()*sizeof(float));Tensor tensor(dtype,memory);
     const fs::path out=root/("startup-zero-warmup-"+item.first);fs::create_directories(out);
     owner_npu::forward<OwnedFrame>(*item.second,device,Json{{"role",item.first},{"output_directory",out.string()},{"profile",false}},nullptr,&tensor);
    }
    std::cout<<"H264_MODEL_WARMUP "<<Json{{"source","synthetic_zero_tensors_not_camera"},{"models",models.size()}}.dump()<<std::endl;
   }
   if(camera_enabled)start_camera();
   while(!stopping&&now()<deadline){
    pollfd in{STDIN_FILENO,POLLIN,0};const int ready=poll(&in,1,50);if(ready<0&&errno==EINTR)continue;if(ready<0)throw std::runtime_error("Owner command poll failed");
    if(ready&&(in.revents&POLLIN)){std::string line;if(!std::getline(std::cin,line))break;if(line.size()>65536)throw std::runtime_error("Owner command too large");const auto request=Json::parse(line);const std::string op=request.at("op");const bool command_pause=h264&&getenv("WCIS_H264_COMMAND_PAUSE")&&std::string(getenv("WCIS_H264_COMMAND_PAUSE"))=="1"&&op!="latest";if(command_pause)pause_h264_camera_for_command();else if(h264&&h264_sdk_pause&&op!="latest")pause_h264_for_sdk();emit(command(request));if(command_pause||(h264&&h264_sdk_pause&&op=="release")){direct_camera->resume();camera_pending=true;h264_pause=false;}}
    else if(ready&&(in.revents&(POLLHUP|POLLERR)))break;
   }
   stop_camera();
   stop_h264();
   if(direct_camera){direct_camera->close();direct_camera.reset();}
   if(sdk&&pending_camera){drain_camera();++camera_drained;}
   camera_io.reset();camera_memory.clear();
   if(encoder){while(!encoding.empty()&&publish(1500)){}encoder->streamOff();encoder.reset();}
   if(!encoding.empty())throw std::runtime_error("Owner stopped with undrained VPU frames");
   owner_npu::release_sessions(models);frame_memory.reset();frame.reset();
   if(sdk){Device::Close(*sdk);sdk.reset();}status("stopped");
   emit({{"status","stopped"},{"captured",captured.load()},{"encoded",encoded.load()},{"h264_submitted",h264_submitted.load()},{"h264_mapping_frames",h264_mapping_frames.load()},{"commands",commands.load()},{"camera_requests",camera_requests.load()},{"camera_drained",camera_drained.load()},{"camera_pending",false},{"sessions_released",true},{"sdk_closed",true}});return 0;
  }catch(const std::exception& e){fault(e.what());}
 }
};
int main(int argc,char** argv){
 if(argc!=5&&argc!=6)return 2;
 try{
  const std::string boot=argv[2];if(boot!=frame_lease::boot_id())return 2;
  const fs::path root=argv[3];if(root.parent_path()!=fs::path("/dev/shm")||root.filename().string().find("wcis-owner-")!=0)return 2;
  const int seconds=std::stoi(argv[4]);if(seconds<0||(seconds>0&&seconds<5)||seconds>3600)return 2;
  for(const char* name:{"WCIS_NPU_LOCK_FD","WCIS_CAMERA_LOCK_FD"}){const char* value=getenv(name);if(!value)return 2;const int fd=atoi(value);if(fd<3||fcntl(fd,F_GETFD)<0||flock(fd,LOCK_EX|LOCK_NB))return 2;}
  const std::string mode=argc==6?argv[5]:"vpu";
  if(mode!="vpu"&&mode!="no-camera"&&mode!="pl-preview")return 2;
  std::signal(SIGTERM,stop);std::signal(SIGINT,stop);Owner owner(root,fs::absolute(argv[1]),boot,mode!="no-camera",mode=="pl-preview");return owner.run(seconds);
 }catch(const std::exception& e){emit({{"status","error"},{"message",e.what()}});return 2;}
}
