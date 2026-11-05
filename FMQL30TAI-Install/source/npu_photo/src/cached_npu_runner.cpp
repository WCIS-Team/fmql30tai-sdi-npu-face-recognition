// One CPU-resident model per process. Open/close the device per request.
#include <icraft-xrt/core/session.h>
#include <icraft-xrt/dev/host_device.h>
#include <icraft-xrt/dev/zg330_device.h>
#include <icraft-backends/hostbackend/backend.h>
#include <icraft-backends/zg330backend/zg330backend.h>
#include <icraft-xir/ops/hard_op.h>
#include <nlohmann/json.hpp>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <stdexcept>
#include <unistd.h>
#include <optional>
#include "frame_lease.h"

using Json=nlohmann::json;
namespace fs=std::filesystem;
using namespace icraft::xrt;
using Clock=std::chrono::steady_clock;
struct Model {icraft::xir::Network network;int hard_ops=0;};
using Models=std::map<std::string,std::unique_ptr<Model>>;
double milliseconds(Clock::time_point t){return std::chrono::duration<double,std::milli>(Clock::now()-t).count();}
void emit(const Json& j){std::cout<<"\nWCIS_RESULT "<<j.dump()<<std::endl;}

Json forward(Model& m,Device device,const Json& q,frame_lease::Reservation* frame=nullptr){
    const auto start=Clock::now();const auto role=q.at("role").get<std::string>();
    const auto session_start=Clock::now();
    auto session=Session::Create<icraft::xrt::zg330::ZG330Backend,HostBackend>(m.network,{device,HostDevice::Default()});
    // Preserve the factory example's validated graph and device settings.
    auto backend=session->backends[0].cast<icraft::xrt::zg330::ZG330Backend>();
    backend.disableMergeHardOp();backend.disableEtmOptimize();
    backend.ocmOptimize(icraft::xrt::zg330::OcmOpt::None);
    session.apply();session.enableTimeProfile(false);
    if(frame)frame->check();
    const double session_ms=milliseconds(session_start);const auto input_start=Clock::now();
    const auto dtype=m.network.inputs()[0].tensorType();const size_t bytes=dtype.numElements()*sizeof(float);
    fs::path input=q.at("input_f32").get<std::string>();
    if(fs::file_size(input)!=bytes)throw std::runtime_error("Input tensor byte length mismatch");
    std::vector<float> data(bytes/sizeof(float));std::ifstream f(input,std::ios::binary);
    f.read(reinterpret_cast<char*>(data.data()),bytes);if(!f)throw std::runtime_error("Tensor file read failed");
    for(float v:data)if(!std::isfinite(v))throw std::runtime_error("Non-finite input tensor");
    auto chunk=HostDevice::MemRegion().malloc(bytes);
    chunk.write(0,reinterpret_cast<char*>(data.data()),bytes);Tensor tensor(dtype,chunk);
    const double input_ms=milliseconds(input_start);const auto compute_start=Clock::now();
    auto result=session.forward({tensor});
    if(result.size()!=m.network.outputs().size())throw std::runtime_error("Runtime output count mismatch");
    for(auto& value:result)if(!value.waitForReady(std::chrono::microseconds(10000000),std::chrono::microseconds(50)))
        throw std::runtime_error("NPU output did not become ready within the SDK deadline");
    const double compute_ms=milliseconds(compute_start);const auto output_start=Clock::now();
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
    return {{"status","forwarded"},{"role",role},{"backend","zg330_npu_and_host"},{"npu_bound_ops",executed_npu},
        {"profile_enabled",false},{"sdk_hard_time_ms",nullptr},{"outputs",records},{"elapsed_ms",milliseconds(start)},
        {"phases_ms",{{"session",session_ms},{"input",input_ms},{"forward_and_wait",compute_ms},{"output",output_ms}}}};
}

Json device_request(Model& model,const Json& config,const Json& q){
    std::optional<frame_lease::Lease> lease;
    if(q.contains("retained_frame"))lease=frame_lease::Lease::parse(q.at("retained_frame"));
    const auto start=Clock::now();
    auto device=Device::Open("axi://zg330aiu?npu=0x40000000&dma=0x80000000");
    const auto geometry=device.cast<ZG330Device>().getRowsCols();
    if(config.at("rows")!=geometry.first||config.at("cols")!=geometry.second)
        throw std::runtime_error("Compiled MPE rows/cols do not match measured device geometry");
    const double open_ms=milliseconds(start);
    // All tensor/session temporaries are destroyed before closing the device.
    Json response;
    {
        std::optional<frame_lease::Reservation> held;
        if(lease)held.emplace(device,*lease);
        response=forward(model,device,q,held ? &*held : nullptr);
        if(held){
            held->check();response["frame_preserved"]=true;
            response["frame_id"]=held->lease.id;response["frame_token"]=held->lease.token;
            response["frame_reservation_bytes"]=held->lease.bytes;
        }
    }
    Device::Close(device);
    response["device_open_ms"]=open_ms;response["worker_wall_ms"]=milliseconds(start);
    response["worker_pid"]=getpid();response["device_closed"]=true;
    response["session_lifecycle"]="resident_process_per_model";
    return response;
}

int main(int argc,char** argv){
    if(argc==2&&std::string(argv[1])=="--help"){
        std::cout<<"wcis_face_cached --serve MANIFEST ROLE | --describe MANIFEST ROLE\n"
          "CPU-only model cache. JSON: role, input_f32, output_directory.\n"
          "One resident CPU model per process; hardware is closed before replying.\n";return 0;
    }
    if(argc!=4)return 2;
    const std::string mode=argv[1];if(mode!="--describe"&&mode!="--serve")return 2;
    const std::string role=argv[3];if(role!="yunet"&&role!="mobilefacenet")return 2;
    try{
        const auto startup=Clock::now();fs::path manifest_path=fs::absolute(argv[2]);
        std::ifstream manifest(manifest_path);Json config;manifest>>config;
        if(config.at("schema_version")!=1||config.at("generated")!=true)throw std::runtime_error("Only generated, checked model packages are accepted");
        Models models;Json contracts=Json::object(),parse_ms=Json::object();
        for(auto it=config.at("models").begin();it!=config.at("models").end();++it){
            if(it.key()!=role)continue;
            const auto start=Clock::now();auto m=std::make_unique<Model>();
            fs::path jp=manifest_path.parent_path()/it.value().at("json").get<std::string>();
            fs::path rp=manifest_path.parent_path()/it.value().at("raw").get<std::string>();
            m->network=icraft::xir::Network::CreateFromJsonFile(jp.string());m->network.lazyLoadParamsFromFile(rp.string());
            for(const auto& op:m->network->ops)if(op.is<icraft::xir::HardOp>())++m->hard_ops;
            if(m->hard_ops==0)throw std::runtime_error("Model contains no generated HardOp; refusing hardware run");
            auto inputs=m->network.inputs();auto outputs=m->network.outputs();
            if(inputs.size()!=1||!inputs[0].tensorType()->element_dtype.isFP32())throw std::runtime_error("Expected one software FP32 input");
            const size_t size=it.key()=="yunet"?640:it.key()=="mobilefacenet"?112:0;
            if(!size||inputs[0].tensorType().numElements()!=size*size*3)throw std::runtime_error("Unexpected input element count");
            const auto shape=inputs[0].tensorType()->shape;
            if(shape.size()!=4||shape[0]!=1||shape[1]!=static_cast<int64_t>(size)||shape[2]!=static_cast<int64_t>(size)||shape[3]!=3)
                throw std::runtime_error("Input must be batch-one NHWC");
            if(outputs.size()!=(it.key()=="yunet"?12:1))throw std::runtime_error("Unexpected output count");
            for(const auto& v:outputs)if(!v.tensorType()->element_dtype.isFP32())throw std::runtime_error("Expected software FP32 outputs");
            contracts[it.key()]={{"hard_ops",m->hard_ops},{"input_elements",inputs[0].tensorType().numElements()},{"output_count",outputs.size()}};
            models[it.key()]=std::move(m);parse_ms[it.key()]=milliseconds(start);
        }
        if(models.size()!=1)throw std::runtime_error("Expected exactly the selected model");
        emit({{"status",mode=="--describe"?"described":"ready"},{"backend","zg330_npu_and_host"},
            {"contracts",contracts},{"model_parse_ms",parse_ms},{"startup_ms",milliseconds(startup)},
            {"cache_pid",getpid()},{"role",role},{"device_opened",false},{"session_lifecycle","resident_process_per_model"},
            {"retained_frame_supported",true}});
        if(mode=="--describe")return 0;
        std::string line;
        while(std::getline(std::cin,line)){
            auto q=Json::parse(line);
            if(q.at("role")!=role)throw std::runtime_error("Request belongs to another model process");
            emit(device_request(*models.at(role),config,q));
        }
        return 0;
    }catch(const std::exception& e){emit({{"status","error"},{"message",e.what()}});return 2;}
}
