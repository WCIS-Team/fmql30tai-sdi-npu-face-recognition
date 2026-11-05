// File-tensor NPU runner. Opens no camera and preserves device clock settings.
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
using Json=nlohmann::json;
namespace fs=std::filesystem;
using namespace icraft::xrt;
struct Model {icraft::xir::Network network;Session session;int hard_ops=0;};
Json read_json(const fs::path& path){std::ifstream f(path);if(!f)throw std::runtime_error("Cannot read model manifest");Json j;f>>j;return j;}
void emit(const Json& j){std::cout<<"\nWCIS_RESULT "<<j.dump()<<std::endl;}
int main(int argc,char** argv){
    if(argc==2&&std::string(argv[1])=="--inspect-adder"){
        try{
            auto device=Device::Open("axi://zg330aiu?npu=0x40000000&dma=0x80000000");
            const auto version=device.defaultRegRegion().read(0x400C00C0,false);
            const auto rowscols=device.cast<ZG330Device>().getRowsCols();
            emit({{"status","adder_inspected"},{"version",version},{"rows",rowscols.first},{"cols",rowscols.second},{"read_path","same SDK RegRegion API as tutorial source"},{"operation_started",false}});
            Device::Close(device);return 0;
        }catch(const std::exception& e){emit({{"status","error"},{"message",e.what()}});return 2;}
    }
    if(argc==2&&std::string(argv[1])=="--help"){
        std::cout<<"wcis_face_npu --describe MANIFEST | --run MANIFEST\nDescribe loads models only; run requires reviewed firmware and exclusive NPU ownership.\nJSON requests: role, input_f32, output_directory. Input is FP32 NHWC, preprocessed by PS. No camera or clock writes.\n";return 0;
    }
    if(argc!=3||(std::string(argv[1])!="--describe"&&std::string(argv[1])!="--run"))return 2;
    try{
        fs::path manifest_path=fs::absolute(argv[2]);auto config=read_json(manifest_path);
        if(config.at("schema_version")!=1||config.at("generated")!=true)throw std::runtime_error("Only generated, checked model packages are accepted");
        std::map<std::string,std::unique_ptr<Model>> models;Json contracts=Json::object();
        for(auto it=config.at("models").begin();it!=config.at("models").end();++it){
            auto m=std::make_unique<Model>();fs::path jp=manifest_path.parent_path()/it.value().at("json").get<std::string>();fs::path rp=manifest_path.parent_path()/it.value().at("raw").get<std::string>();
            m->network=icraft::xir::Network::CreateFromJsonFile(jp.string());m->network.lazyLoadParamsFromFile(rp.string());
            for(const auto& op:m->network->ops)if(op.is<icraft::xir::HardOp>())++m->hard_ops;
            if(m->hard_ops==0)throw std::runtime_error("Model contains no generated HardOp; refusing hardware run");
            auto inputs=m->network.inputs();auto outputs=m->network.outputs();
            if(inputs.size()!=1||!inputs[0].tensorType()->element_dtype.isFP32())throw std::runtime_error("Expected one software FP32 input");
            const size_t size=it.key()=="yunet"?640:it.key()=="mobilefacenet"?112:0;
            if(!size||inputs[0].tensorType().numElements()!=size*size*3)throw std::runtime_error("Unexpected input element count");
            const auto input_shape=inputs[0].tensorType()->shape;
            if(input_shape.size()!=4||input_shape[0]!=1||input_shape[1]!=static_cast<int64_t>(size)||input_shape[2]!=static_cast<int64_t>(size)||input_shape[3]!=3)throw std::runtime_error("Input must be batch-one NHWC");
            if(outputs.size()!=(it.key()=="yunet"?12:1))throw std::runtime_error("Unexpected output count");
            for(const auto& v:outputs)if(!v.tensorType()->element_dtype.isFP32())throw std::runtime_error("Expected software FP32 outputs");
            contracts[it.key()]={{"hard_ops",m->hard_ops},{"input_elements",inputs[0].tensorType().numElements()},{"output_count",outputs.size()}};
            models[it.key()]=std::move(m);
        }
        if(models.size()!=2)throw std::runtime_error("Expected both detector and recognizer");
        if(std::string(argv[1])=="--describe"){emit({{"status","described"},{"contracts",contracts},{"device_opened",false}});return 0;}
        std::cerr<<"STAGE device_open\n"<<std::flush;
        auto device=Device::Open("axi://zg330aiu?npu=0x40000000&dma=0x80000000");
        std::cerr<<"STAGE device_returned\n"<<std::flush;
        const auto geometry=device.cast<ZG330Device>().getRowsCols();
        if(config.at("rows")!=geometry.first||config.at("cols")!=geometry.second)
            throw std::runtime_error("Compiled MPE rows/cols do not match measured device geometry");
        emit({{"status","ready"},{"backend","zg330_npu_and_host"},{"contracts",contracts}});
        std::string line;
        while(std::getline(std::cin,line)){
            auto q=Json::parse(line);auto role=q.at("role").get<std::string>();auto& m=*models.at(role);
            auto start=std::chrono::steady_clock::now();
            if(!m.session.defined()){
                std::cerr<<"STAGE session "<<role<<"\n"<<std::flush;
                m.session=Session::Create<icraft::xrt::zg330::ZG330Backend,HostBackend>(m.network,{device,HostDevice::Default()});
                // Match the factory example's baseline before tuning throughput.
                auto backend=m.session->backends[0].cast<icraft::xrt::zg330::ZG330Backend>();
                backend.disableMergeHardOp();
                backend.disableEtmOptimize();
                backend.ocmOptimize(icraft::xrt::zg330::OcmOpt::None);
                m.session.setPreCallBack([](const Session&,const icraft::xir::Operation& op,const Backend&,std::vector<Tensor>&){
                    std::cerr<<"OP start "<<op->op_id<<" "<<op->typeKey()<<"\n"<<std::flush;
                });
                m.session.setPostCallBack([](const Session&,const icraft::xir::Operation& op,const Backend&,std::vector<Tensor>&){
                    std::cerr<<"OP returned "<<op->op_id<<"\n"<<std::flush;
                });
                m.session.apply();
                m.session.enableTimeProfile(false);
            }
            const auto dtype=m.network.inputs()[0].tensorType();const size_t bytes=dtype.numElements()*sizeof(float);
            fs::path input=q.at("input_f32").get<std::string>();if(fs::file_size(input)!=bytes)throw std::runtime_error("Input tensor byte length mismatch");
            std::vector<float> data(bytes/sizeof(float));std::ifstream f(input,std::ios::binary);f.read(reinterpret_cast<char*>(data.data()),bytes);
            if(!f)throw std::runtime_error("Tensor file read failed");
            for(float v:data)if(!std::isfinite(v))throw std::runtime_error("Non-finite input tensor");
            auto chunk=HostDevice::MemRegion().malloc(bytes);chunk.write(0,reinterpret_cast<char*>(data.data()),bytes);Tensor tensor(dtype,chunk);
            std::cerr<<"STAGE forward "<<role<<"\n"<<std::flush;
            auto result=m.session.forward({tensor});fs::path directory=q.at("output_directory").get<std::string>();fs::create_directories(directory);Json records=Json::array();
            if(result.size()!=m.network.outputs().size())throw std::runtime_error("Runtime output count mismatch");
            for(size_t i=0;i<result.size();++i){
                std::cerr<<"STAGE wait_output "<<role<<" "<<i<<"\n"<<std::flush;
                if(!result[i].waitForReady(std::chrono::microseconds(10000000),std::chrono::microseconds(50)))
                    throw std::runtime_error("NPU output did not become ready within the SDK deadline");
                std::cerr<<"STAGE output_ready "<<role<<" "<<i<<"\n"<<std::flush;
                auto count=m.network.outputs()[i].tensorType().numElements();if(!result[i].dtype()->element_dtype.isFP32()||result[i].dtype().numElements()!=count)throw std::runtime_error("Runtime output dtype/shape mismatch");
                fs::path path=directory/(std::to_string(i)+".f32");
                std::ofstream stream(path,std::ios::binary);
                // Export software order and FP32 through the documented SDK API;
                // raw device storage may contain padding or merged distributions.
                result[i].dump(stream,"SFB");stream.close();
                if(!stream||fs::file_size(path)!=count*sizeof(float))throw std::runtime_error("Software output byte count mismatch");
                std::vector<float> values(count);std::ifstream check(path,std::ios::binary);check.read(reinterpret_cast<char*>(values.data()),count*sizeof(float));
                if(!check)throw std::runtime_error("Output validation read failed");
                for(float value:values)if(!std::isfinite(value))throw std::runtime_error("Non-finite NPU output");
                records.push_back({{"index",i},{"elements",count},{"file",path.string()}});
            }
            int executed_npu=0;for(const auto& item:m.session.backendBindings())if(item.second.is<icraft::xrt::zg330::ZG330Backend>())++executed_npu;
            if(executed_npu==0)throw std::runtime_error("No operation bound to ZG330 backend");
            // Standalone execution passes while two resident sessions fail on
            // this board/runtime pair. Keep only one session alive at a time.
            result.clear();
            m.session=Session();
            emit({{"status","forwarded"},{"role",role},{"backend","zg330_npu_and_host"},{"npu_bound_ops",executed_npu},{"profile_enabled",false},{"sdk_hard_time_ms",nullptr},{"outputs",records},{"elapsed_ms",std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count()}});
        }
        Device::Close(device);
        return 0;
    }catch(const std::exception& e){emit({{"status","error"},{"message",e.what()}});return 2;}
}
