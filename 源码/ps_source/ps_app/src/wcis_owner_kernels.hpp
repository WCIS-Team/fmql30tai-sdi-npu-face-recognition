#pragma once
// Reuse the validated NPU and FAC1 command kernels without changing arithmetic.
// A single owner retains the allocator and serializes all SDK operations.
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
#include <memory>
#include <optional>
#include <thread>
#include <vector>
#include <unistd.h>
#include <functional>

namespace owner_npu {
inline std::function<void()> before_exclusive,after_exclusive;
using namespace icraft::xrt;using Json=nlohmann::json;namespace fs=std::filesystem;using Clock=std::chrono::steady_clock;
struct Model {
    icraft::xir::Network network;int hard_ops=0;
    bool cache_session=true;std::optional<Session> session;
    uint64_t session_creations=0,forwards=0;
};
using Models=std::map<std::string,std::unique_ptr<Model>>;
inline void release_sessions(Models& models){for(auto& item:models)item.second->session.reset();}
double milliseconds(Clock::time_point t){return std::chrono::duration<double,std::milli>(Clock::now()-t).count();}
void emit(const Json& j){std::cout<<"\nWCIS_RESULT "<<j.dump()<<std::endl;}

template<class Held> Json forward(Model& m,Device device,const Json& q,Held* frame,const Tensor* prepared=nullptr){
    const auto start=Clock::now();const auto role=q.at("role").get<std::string>();
    const auto session_start=Clock::now();
    // Vendor multinets_npu_actor keeps separately applied sessions across
    // network switches and reset(1). They share this owner's device/allocator.
    std::optional<Session> temporary;
    auto& storage=m.cache_session?m.session:temporary;
    const bool reused=storage.has_value();
    double session_create_ms=0,configure_ms=0,apply_ms=0;
    if(!reused){
        if(before_exclusive)before_exclusive();
        storage.emplace(Session::Create<icraft::xrt::zg330::ZG330Backend,HostBackend>(m.network,{device,HostDevice::Default()}));
        session_create_ms=milliseconds(session_start);const auto configure_start=Clock::now();
        auto backend=(*storage)->backends[0].cast<icraft::xrt::zg330::ZG330Backend>();
        backend.disableMergeHardOp();backend.disableEtmOptimize();
        backend.ocmOptimize(icraft::xrt::zg330::OcmOpt::None);
        configure_ms=milliseconds(configure_start);const auto apply_start=Clock::now();
        storage->apply();apply_ms=milliseconds(apply_start);++m.session_creations;
        if(after_exclusive)after_exclusive();
    }
    auto& session=*storage;
    const bool profile=q.value("profile",false);session.enableTimeProfile(profile);
    if(frame)frame->check();
    const double session_ms=milliseconds(session_start);const auto input_start=Clock::now();
    const auto dtype=m.network.inputs()[0].tensorType();const size_t bytes=dtype.numElements()*sizeof(float);
    Tensor tensor;
    if(prepared){
        if(prepared->dtype().numElements()!=dtype.numElements()||!prepared->dtype()->element_dtype.isFP32())throw std::runtime_error("Prepared tensor contract mismatch");
        tensor=*prepared;
    }else{
        fs::path input=q.at("input_f32").get<std::string>();
        if(fs::file_size(input)!=bytes)throw std::runtime_error("Input tensor byte length mismatch");
        std::vector<float> data(bytes/sizeof(float));std::ifstream f(input,std::ios::binary);
        f.read(reinterpret_cast<char*>(data.data()),bytes);if(!f)throw std::runtime_error("Tensor file read failed");
        for(float v:data)if(!std::isfinite(v))throw std::runtime_error("Non-finite input tensor");
        auto chunk=HostDevice::MemRegion().malloc(bytes);
        chunk.write(0,reinterpret_cast<char*>(data.data()),bytes);tensor=Tensor(dtype,chunk);
    }
    const double input_ms=milliseconds(input_start);const auto compute_start=Clock::now();
    auto result=session.forward({tensor});
    const double dispatch_ms=milliseconds(compute_start);const auto wait_start=Clock::now();
    if(result.size()!=m.network.outputs().size())throw std::runtime_error("Runtime output count mismatch");
    for(auto& value:result)if(!value.waitForReady(std::chrono::microseconds(10000000),std::chrono::microseconds(50)))
        throw std::runtime_error("NPU output did not become ready within the SDK deadline");
    const double wait_ms=milliseconds(wait_start),compute_ms=milliseconds(compute_start);
    // Reuse the vendor icraft_utils.hpp timeProfileResults/getForwards contract.
    // SDK sums are attribution counters in ms, not occupancy or independent
    // pipeline wall times. Never add them to host phases as extra elapsed time.
    const auto profile_start=Clock::now();Json profile_rows=Json::array();
    double sdk_total=0,sdk_copy=0,sdk_hard=0,sdk_other=0;
    if(profile){
        std::map<int,Json> labels;
        for(auto& [op,a,b,c,d]:session.getForwards())
            labels[op->op_id]={{"type",op->typeKey()},{"name",op->name}};
        for(const auto& item:session.timeProfileResults()){
            const auto& [total,copy,hard,other]=item.second;
            if(!std::isfinite(total)||!std::isfinite(copy)||!std::isfinite(hard)||!std::isfinite(other))
                throw std::runtime_error("Non-finite SDK profile counter");
            Json row={{"op_id",item.first},{"total_ms",total},{"memcpy_ms",copy},{"hard_ms",hard},{"other_ms",other}};
            if(labels.count(item.first))row.update(labels.at(item.first));
            profile_rows.push_back(std::move(row));sdk_total+=total;sdk_copy+=copy;sdk_hard+=hard;sdk_other+=other;
        }
    }
    const double profile_ms=milliseconds(profile_start);const auto output_start=Clock::now();
    fs::path directory=q.at("output_directory").get<std::string>();fs::create_directories(directory);
    Json records=Json::array();
    for(size_t i=0;i<result.size();++i){
        auto count=m.network.outputs()[i].tensorType().numElements();
        if(!result[i].dtype()->element_dtype.isFP32()||result[i].dtype().numElements()!=count)
            throw std::runtime_error("Runtime output dtype/shape mismatch");
        fs::path path=directory/(std::to_string(i)+".f32");std::ofstream stream(path,std::ios::binary);
        result[i].dump(stream,"SFB");stream.close();
        if(!stream||fs::file_size(path)!=count*sizeof(float))throw std::runtime_error("Software output byte count mismatch");
        std::vector<float> values(count);std::ifstream check(path,std::ios::binary);
        check.read(reinterpret_cast<char*>(values.data()),count*sizeof(float));if(!check)throw std::runtime_error("Output validation read failed");
        for(float value:values)if(!std::isfinite(value))throw std::runtime_error("Non-finite NPU output");
        records.push_back({{"index",i},{"elements",count},{"file",path.string()}});
    }
    int executed_npu=0;for(const auto& item:session.backendBindings())
        if(item.second.is<icraft::xrt::zg330::ZG330Backend>())++executed_npu;
    if(executed_npu==0)throw std::runtime_error("No operation bound to ZG330 backend");
    if(frame)frame->check();
    const double output_ms=milliseconds(output_start);
    // Vendor ai_example/{multinets,yolov5}_npu_actor.hpp resets level 1
    // after all output tensors are ready. A resident device must clear the
    // previous network's execution/synchronization state before the next one.
    if(before_exclusive)before_exclusive();
    const auto reset_start=Clock::now();device.reset(1);const double reset_ms=milliseconds(reset_start);
    if(after_exclusive)after_exclusive();
    if(frame)frame->check();
    ++m.forwards;
    uint64_t live_bytes=0,live_chunks=0;
    for(const auto& chunk:device.defaultMemRegion().memManager().getAllMemChunk()){
        live_bytes+=chunk->byte_size;++live_chunks;
    }
    return {{"status","forwarded"},{"role",role},{"backend","zg330_npu_and_host"},{"npu_bound_ops",executed_npu},
        {"profile_enabled",profile},{"sdk_hard_time_ms",profile?Json(sdk_hard):Json(nullptr)},
        {"sdk_profile",profile?Json({{"unit","ms"},{"total",sdk_total},{"memcpy",sdk_copy},{"hard",sdk_hard},{"other",sdk_other},{"ops",profile_rows}}):Json(nullptr)},
        {"outputs",records},{"elapsed_ms",milliseconds(start)},
        {"completion_reset_level",1},{"reset_after_outputs_ready",true},
        {"session_cached",m.cache_session},{"session_reused",reused},{"session_creations",m.session_creations},
        {"model_forwards",m.forwards},{"device_memory_live_bytes",live_bytes},{"device_memory_live_chunks",live_chunks},
        {"phases_ms",{{"session",session_ms},{"session_create",session_create_ms},{"backend_configure",configure_ms},{"session_apply",apply_ms},
            {"input",input_ms},{"forward_and_wait",compute_ms},{"forward_dispatch",dispatch_ms},{"output_wait",wait_ms},
            {"profile_collection",profile_ms},{"output",output_ms},{"completion_reset",reset_ms}}}};
}

}
namespace owner_pl {
using namespace icraft::xrt;using Json=nlohmann::json;namespace fs=std::filesystem;using Clock=std::chrono::steady_clock;
static constexpr uint32_t REG=0x400c2000,ID=0x46414331;
static double ms(Clock::time_point t){return std::chrono::duration<double,std::milli>(Clock::now()-t).count();}
static void emit(const Json& value){std::cout<<"\nWCIS_PL_RESULT "<<value.dump()<<std::endl;}
[[noreturn]] static void fault(const fs::path& path,const std::string& message){
 const Json record={{"boot_id",frame_lease::boot_id()},{"source","retained_frame"},{"message",message},{"automatic_retry",false}};
 std::ofstream file(path);file<<record.dump(2)<<std::endl;file.close();
 std::ofstream detail(fs::canonical("/proc/self/exe").parent_path()/(std::to_string(getpid())+"-pl-fault.json"));detail<<record.dump(2);detail.close();
 std::cerr<<message<<std::endl;std::_Exit(3);
}
struct State {frame_lease::Lease lease;fs::path input,marker;uint64_t runs=0;};
static void checked_firmware(const Device& device){auto regs=device.defaultRegRegion();if(regs.read(REG,false)!=ID||(regs.read(REG+4,false)&1))throw std::runtime_error("FAC1 absent or busy");}
static void quarantine_check(const fs::path& marker){
 if(fs::exists(marker)){std::ifstream f(marker);Json old;f>>old;if(old.value("boot_id","")==frame_lease::boot_id())throw std::runtime_error("Hardware quarantined in current boot");}
}
static Json run_transform(State& state,const Device& device,const MemChunk& memory,const Json& q,bool uploaded,std::vector<char>* retained=nullptr){
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
 const auto init_write_start=Clock::now();
 if(!uploaded)memory.write(lease.output_offset,pixels.data(),pixels.size());
 const double init_write_ms=ms(init_write_start);
 // FAC1's native write port has no DDR write response. Establish a fresh
 // output epoch before START; observing DONE alone is not a readback fence.
 // No accelerator is running while this initial pattern is checked.
 unsigned initialization_reads=0,completion_reads=0;size_t first_partial_pixels=0;
 const auto initialization=Clock::now();std::vector<char> initialized(output_bytes);
 do{
  memory.read(initialized.data(),lease.output_offset,output_bytes);++initialization_reads;
  if(std::all_of(initialized.begin(),initialized.end(),[](char c){return c==static_cast<char>(0xa5);}))break;
  if(ms(initialization)>2000)fault(state.marker,"Retained output initialization did not become visible");
  std::this_thread::sleep_for(std::chrono::microseconds(100));
 }while(true);
 const double init_verify_ms=ms(initialization);const auto descriptor_start=Clock::now();
 auto regs=device.defaultRegRegion();for(size_t i=0;i<words.size();i++)regs.write(REG+0x10+i*4,words[i],false);
 for(size_t i=0;i<words.size();i++)if(regs.read(REG+0x10+i*4,false)!=words[i])throw std::runtime_error("Descriptor readback mismatch");
 const double descriptor_ms=ms(descriptor_start);const auto execution=Clock::now();
 double pl_wait_ms=0,readback_ms=0,file_ms=0;
 try{
  regs.write(REG,1,false);uint32_t status=0;
  do{status=regs.read(REG+4,false);if(ms(execution)>10000)fault(state.marker,"Retained frame PL deadline exceeded");if(!(status&2))std::this_thread::sleep_for(std::chrono::microseconds(100));}while(!(status&2));
  if((status&1)||((status>>4)&15)||(status&8)||regs.read(REG+8,false)!=lease.id||regs.read(REG+12,false)!=dw*dh)throw std::runtime_error("Invalid retained frame completion");
  // Only PL writes zero alpha words after the verified A5 initialization.
  // Wait for those words to be readable, without resubmitting the operation.
  // A stuck/invalid result still quarantines the device; no partial result is
  // accepted and no threshold or model arithmetic changes.
  pl_wait_ms=ms(execution);const auto readback=Clock::now();
  do{
   memory.read(pixels.data(),lease.output_offset,output_bytes);++completion_reads;
   size_t partial=0;for(size_t i=3;i<output_bytes;i+=4)if(pixels[i]!=0)++partial;
   if(completion_reads==1)first_partial_pixels=partial;
   if(!partial)break;
   if(ms(readback)>2000)throw std::runtime_error("Retained frame output did not become readable; incomplete pixels="+std::to_string(partial));
   std::this_thread::sleep_for(std::chrono::microseconds(100));
  }while(true);
  readback_ms=ms(readback);const auto file_start=Clock::now();
  if(q.value("write_output",true)){std::ofstream f(output,std::ios::binary);f.write(pixels.data(),pixels.size());f.close();if(!f)throw std::runtime_error("Cannot write retained output");}
  file_ms=ms(file_start);
 }catch(const std::exception& e){fault(state.marker,e.what());}
 ++state.runs;
 if(retained)*retained=std::move(pixels);
 return {{"status","preprocessed"},{"frame_id",lease.id},{"frame_token",lease.token},{"frame_lease",lease.json()},
  {"pixels",dw*dh},{"source_uploads",1},{"source_upload_bytes",lease.source_bytes},{"source_uploaded_this_command",uploaded},
  {"ddr_frame_reused",!uploaded},{"pl_and_readback_ms",ms(execution)},{"transform_ms",ms(start)},
  {"phases_ms",{{"output_init_write",init_write_ms},{"output_init_verify",init_verify_ms},{"descriptor_io",descriptor_ms},
      {"pl_done_wait",pl_wait_ms},{"output_readback_validate",readback_ms},{"output_file",file_ms}}},
  {"output_initialization_verified",true},{"output_initialization_reads",initialization_reads},{"output_completion_reads",completion_reads},{"first_partial_pixels",first_partial_pixels},
  {"backend","FAC1_customop_PL"},{"normalization_in_PL",false},{"device_closed",false}};
}
}
