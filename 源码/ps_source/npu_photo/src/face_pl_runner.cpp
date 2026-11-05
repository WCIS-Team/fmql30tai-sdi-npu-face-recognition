// File input ModelBackend harness. Reuses the tutorial's RegRegion/MemRegion
// APIs and native CustomOp memory path; no camera, clock or NPU graph changes.
#include <icraft-xrt/dev/zg330_device.h>
#include <nlohmann/json.hpp>
#include <chrono>
#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <thread>
#include <vector>
using namespace icraft::xrt;
using Json=nlohmann::json;
namespace fs=std::filesystem;
static constexpr uint32_t REG=0x400c2000,ID=0x46414331;
static uint64_t round64(uint64_t n){return (n+63)&~uint64_t(63);}
static void fault(const fs::path& marker,const std::string& message){
    std::ifstream boot("/proc/sys/kernel/random/boot_id");std::string id;std::getline(boot,id);
    std::ofstream file(marker);file<<Json{{"boot_id",id},{"source","face_pl_backend"},
        {"message",message},{"automatic_retry",false}}.dump(2)<<std::endl;
    std::cerr<<message<<std::endl;
    // Do not run SDK memory destructors after a potentially outstanding DMA.
    // The boot-scoped fault marker quarantines subsequent application requests.
    std::_Exit(3);
}
int main(int argc,char** argv){
    if(argc==2 && std::string(argv[1])=="--help"){
        std::cout<<"wcis_face_pl --run JOB.json | --check JOB.json\n"
          "Requires FAC1 firmware and exclusive device ownership. No camera or clock writes.\n";return 0;
    }
    if(argc!=3 || (std::string(argv[1])!="--run" && std::string(argv[1])!="--check"))return 2;
    try{
        std::ifstream manifest(argv[2]);Json q;manifest>>q;
        const uint64_t w=q.at("src_w"),h=q.at("src_h"),pitch=q.at("pitch_bytes");
        const uint64_t cw=q.at("content_w"),ch=q.at("content_h"),dw=q.at("canvas_w"),dh=q.at("canvas_h");
        const bool rgb565=q.value("rgb565",false),replicate=q.value("replicate",false);
        if(!w||!h||w>8192||h>8192||!cw||!ch||cw>dw||ch>dh||dw>640||dh>640||
           pitch%8 || pitch<w*(rgb565?2:4) || pitch>65536)
            throw std::runtime_error("Invalid preprocessing dimensions/pitch");
        const uint64_t input_bytes=pitch*h,output_bytes=dw*dh*4;
        const uint64_t output_offset=round64(input_bytes),total=output_offset+round64(output_bytes);
        if(total>64*1024*1024)throw std::runtime_error("Prototype allocation exceeds 64 MiB");
        const fs::path input=q.at("input_rgbx").get<std::string>(),output=q.at("output_rgbx").get<std::string>();
        const fs::path marker=q.at("fault_marker").get<std::string>();
        if(fs::file_size(input)!=input_bytes || fs::exists(output))throw std::runtime_error("Input size or output exclusivity mismatch");
        if(q.at("inverse_q16").size()!=6)throw std::runtime_error("Six inverse matrix coefficients required");
        std::vector<int32_t> matrix;
        for(const auto& v:q.at("inverse_q16")){
            if(!v.is_number_integer())throw std::runtime_error("Q16.16 coefficients must be integers");
            const auto n=v.get<int64_t>();if(n<INT32_MIN||n>INT32_MAX)throw std::runtime_error("Q16.16 coefficient overflow");
            matrix.push_back(static_cast<int32_t>(n));
        }
        if(std::string(argv[1])=="--check"){
            std::cout<<Json{{"status","validated"},{"device_opened",false},{"input_bytes",input_bytes},{"output_bytes",output_bytes}}<<std::endl;return 0;
        }
        if(fs::exists(marker)){
            std::ifstream boot("/proc/sys/kernel/random/boot_id");std::string id;std::getline(boot,id);
            std::ifstream f(marker);Json previous;f>>previous;
            if(previous.value("boot_id","")==id)throw std::runtime_error("Hardware quarantined in this boot; inspect before retry");
        }
        std::vector<char> storage(total,0);
        std::ifstream f(input,std::ios::binary);f.read(storage.data(),input_bytes);
        if(!f)throw std::runtime_error("Input read failed");
        // Output X bytes must all become zero. A nonzero canary detects a
        // dropped/unfinished write even when legitimate RGB pixels are black.
        std::fill(storage.begin()+output_offset,storage.end(),static_cast<char>(0xa5));
        auto device=Device::Open("axi://zg330aiu?npu=0x40000000&dma=0x80000000");
        auto registers=device.defaultRegRegion();
        if(registers.read(REG,false)!=ID){Device::Close(device);throw std::runtime_error("FAC1 bitstream is absent; no start register was written");}
        if(registers.read(REG+4,false)&1){Device::Close(device);throw std::runtime_error("Preprocessor already busy");}
        auto memory=device.defaultMemRegion().malloc(total,0,64);
        const uint64_t base=memory->begin.addr();
        if(base%64 || base+total>0x08000000){Device::Close(device);throw std::runtime_error("Allocation outside conservative CustomOp address window");}
        memory.write(0,storage.data(),total);
        auto wr=[&](uint32_t offset,uint32_t value){registers.write(REG+offset,value,false);};
        const uint32_t frame=q.at("frame_id");
        std::vector<uint32_t> words={frame,static_cast<uint32_t>(base),static_cast<uint32_t>(pitch),
            static_cast<uint32_t>(base+output_offset),static_cast<uint32_t>((h<<16)|w),
            static_cast<uint32_t>((ch<<16)|cw),static_cast<uint32_t>((dh<<16)|dw),
            static_cast<uint32_t>((rgb565?2:0)|(replicate?1:0)),q.value("border",0u)};
        for(const auto v:matrix)words.push_back(static_cast<uint32_t>(v));
        for(size_t i=0;i<words.size();i++)wr(0x10+i*4,words[i]);
        for(size_t i=0;i<words.size();i++)if(registers.read(REG+0x10+i*4,false)!=words[i])
            throw std::runtime_error("Descriptor readback mismatch");
        const auto started=std::chrono::steady_clock::now();
        // From this point, every failure is boot-quarantined before exiting.
        try{
            wr(0,1);uint32_t status=0;
            do{
                status=registers.read(REG+4,false);
                if(std::chrono::steady_clock::now()-started>std::chrono::seconds(10))
                    fault(marker,"PL preprocessing timeout; do not reuse buffers before hardware reset");
                if(!(status&2))std::this_thread::sleep_for(std::chrono::microseconds(100));
            }while(!(status&2));
            if((status&1)||((status>>4)&15)||(status&8))throw std::runtime_error("PL rejected/failed preprocessing job");
            if(registers.read(REG+8,false)!=frame||registers.read(REG+12,false)!=dw*dh)
                throw std::runtime_error("PL completed frame/pixel count mismatch");
            memory.read(storage.data(),output_offset,output_bytes);
            for(size_t i=3;i<output_bytes;i+=4)if(storage[i]!=0)
                throw std::runtime_error("PL output write canary remains; tensor is incomplete");
            std::ofstream result(output,std::ios::binary);result.write(storage.data(),output_bytes);result.close();
            if(!result)throw std::runtime_error("Output write failed");
        }catch(const std::exception& e){fault(marker,e.what());}
        const double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-started).count();
        Device::Close(device);
        std::cout<<"\nWCIS_PL_RESULT "<<Json{{"status","preprocessed"},{"frame_id",frame},{"pixels",dw*dh},{"pl_and_readback_ms",ms},
            {"backend","FAC1_customop_PL"},{"normalization_in_PL",false},{"camera_opened",false}}<<std::endl;
        return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<std::endl;return 2;}
}
