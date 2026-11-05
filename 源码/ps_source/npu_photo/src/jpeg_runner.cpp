// Persistent SDK client for JPG1. Pixel upload, PL encoding, readback and file
// I/O are timed separately. No CPU JPEG encoder and no NPU model/session.
#include <icraft-xrt/dev/zg330_device.h>
#include <nlohmann/json.hpp>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#include <fcntl.h>
#include <unistd.h>
using namespace icraft::xrt;
using Json=nlohmann::json;
namespace fs=std::filesystem;
using Clock=std::chrono::steady_clock;
static constexpr uint32_t REG=0x400c2100,ID=0x4a504731;
static constexpr uint64_t SOURCE_CAPACITY=1920ull*1080*4,OUTPUT_CAPACITY=8ull*1024*1024;
static constexpr uint64_t SOURCE_OFFSET=64,OUTPUT_OFFSET=SOURCE_OFFSET+SOURCE_CAPACITY+64;
static constexpr uint64_t TOTAL=OUTPUT_OFFSET+OUTPUT_CAPACITY+64;
static double ms(Clock::time_point t){return std::chrono::duration<double,std::milli>(Clock::now()-t).count();}
static std::string boot_id(){std::ifstream f("/proc/sys/kernel/random/boot_id");std::string s;std::getline(f,s);return s;}
static void emit(const Json& q){std::cout<<"\nWCIS_JPEG_RESULT "<<q.dump()<<std::endl;}
[[noreturn]] static void fault(const fs::path& path,const std::string& message){
    std::ofstream f(path);f<<Json{{"boot_id",boot_id()},{"source","JPG1"},{"message",message},{"automatic_retry",false}}.dump(2)<<std::endl;
    std::cerr<<message<<std::endl;std::_Exit(3);
}
static void write_all(int fd,const char* p,size_t bytes){
    while(bytes){const auto n=::write(fd,p,bytes);if(n<=0)throw std::runtime_error("record write failed");p+=n;bytes-=static_cast<size_t>(n);}
}
// SDK-only control experiment. Never issues a CustomOp command or probes an
// arbitrary address: every transfer stays in one SDK-managed allocation.
static int memory_probe(){
    auto device=Device::Open("axi://zg330aiu?npu=0x40000000&dma=0x80000000");
    Json results=Json::array();
    {
        auto memory=device.defaultMemRegion().malloc(TOTAL,true,64);
        if(memory->begin.addr()%64 || memory->begin.addr()+TOTAL>0x08000000)
            throw std::runtime_error("Probe allocation outside verified 128 MiB window");
        std::vector<char> expected(SOURCE_CAPACITY+64),actual(expected.size()),again(expected.size());
        uint32_t random=0x194516u;
        for(auto& b:expected){random^=random<<13;random^=random>>17;random^=random<<5;b=static_cast<char>(random);}
        for(uint64_t offset:std::vector<uint64_t>{0,64}){
            const uint64_t bytes=1920ull*1080*2;
            for(uint64_t chunk:std::vector<uint64_t>{bytes,65536}){
                const auto start=Clock::now();
                for(uint64_t i=0;i<bytes;i+=chunk)memory.write(offset+i,expected.data()+i,std::min(chunk,bytes-i));
                const double write_ms=ms(start);auto t=Clock::now();
                memory.read(actual.data(),offset,bytes);const double read_ms=ms(t);
                std::this_thread::sleep_for(std::chrono::milliseconds(2));
                memory.read(again.data(),offset,bytes);
                uint64_t errors=0,second_errors=0,changed=0,first=bytes;
                std::vector<uint64_t> bits(8),lanes(64);
                for(uint64_t i=0;i<bytes;++i){
                    const unsigned delta=static_cast<unsigned char>(expected[i]^actual[i]);
                    if(delta){++errors;first=std::min(first,i);++lanes[i%64];for(unsigned bit=0;bit<8;++bit)if(delta&(1u<<bit))++bits[bit];}
                    if(again[i]!=expected[i])++second_errors;
                    if(again[i]!=actual[i])++changed;
                }
                results.push_back({{"offset",offset},{"chunk",chunk},{"bytes",bytes},{"mismatches",errors},
                    {"second_read_mismatches",second_errors},{"changed_between_reads",changed},{"first_mismatch",first},
                    {"bit_errors",bits},{"lane_errors",lanes},{"write_ms",write_ms},{"read_ms",read_ms}});
            }
        }
        emit({{"status","memory_probe"},{"allocation_base",memory->begin.addr()},{"results",results},{"customop_started",false}});
    }
    Device::Close(device);return 0;
}
int main(int argc,char** argv){
    if(argc==2&&std::string(argv[1])=="--memory-probe")return memory_probe();
    if(argc==2&&std::string(argv[1])=="--help"){
        std::cout<<"wcis_jpeg --serve CONFIG.json; persistent, bounded JPG1 hardware test; exclusive device ownership required\n";return 0;
    }
    if(argc!=3||std::string(argv[1])!="--serve")return 2;
    int record_fd=-1;
    try{
        std::ifstream config_file(argv[2]);Json cfg;config_file>>cfg;
        const fs::path marker=cfg.at("fault_marker").get<std::string>();
        if(fs::exists(marker)){std::ifstream f(marker);Json old;f>>old;if(old.value("boot_id","")==boot_id())throw std::runtime_error("Current boot is quarantined");}
        const fs::path record=cfg.at("record_path").get<std::string>();
        record_fd=::open(record.c_str(),O_WRONLY|O_CREAT|O_EXCL,0600);
        if(record_fd<0)throw std::runtime_error("Record path already exists or cannot be created");
        const auto open_start=Clock::now();
        auto device=Device::Open("axi://zg330aiu?npu=0x40000000&dma=0x80000000");
        const double device_open_ms=ms(open_start);
        {
            auto regs=device.defaultRegRegion();
            if(regs.read(REG,false)!=ID || regs.read(REG+4,false)&1)throw std::runtime_error("JPG1 firmware absent or busy; no DMA started");
            if(regs.read(REG+36,false)!=1920 || regs.read(REG+40,false)!=1080)throw std::runtime_error("Unexpected JPEG resolution");
            const uint32_t quality=regs.read(REG+44,false);
            auto memory=device.defaultMemRegion().malloc(TOTAL,true,64);
            const uint64_t base=memory->begin.addr();
            if(base%64 || base+TOTAL>0x08000000)throw std::runtime_error("SDK allocation outside verified 128 MiB window");
            std::vector<char> guard(64,static_cast<char>(0xa5));
            memory.write(0,guard.data(),64);
            memory.write(OUTPUT_OFFSET-64,guard.data(),64);
            memory.write(TOTAL-64,guard.data(),64);
            emit({{"status","ready"},{"backend","JPG1_FPGA"},{"width",1920},{"height",1080},{"quality",quality},
                  {"clock_hz",100000000},{"device_open_ms",device_open_ms},{"allocation_bytes",TOTAL},{"boot_id",boot_id()}});
            uint64_t frame_count=0,record_bytes=0;
            bool resident=false;uint32_t last_format=0,last_sequence=0;
            std::string line;
            while(std::getline(std::cin,line)){
                if(line.size()>65536)throw std::runtime_error("Command too large");
                const Json q=Json::parse(line);
                const auto op=q.at("op").get<std::string>();
                if(op=="finish")break;
                if(op=="flush"){
                    const auto t=Clock::now();
                    if(::fsync(record_fd)!=0)throw std::runtime_error("Recording sync failed");
                    emit({{"status","flushed"},{"fsync_ms",ms(t)},{"record_bytes",record_bytes}});
                    continue;
                }
                if(op!="frame"&&op!="replay")throw std::runtime_error("Unknown JPEG command");
                const bool replay=op=="replay";
                const bool readback=q.value("readback",true),save=q.value("record",true);
                const uint32_t repetitions=replay?q.value("repeat",1u):1u;
                if(!repetitions || repetitions>300 || (save&&!readback))throw std::runtime_error("Invalid bounded replay");
                double input_read_ms=0,upload_ms=0,source_verification_ms=0;
                bool source_verified=false;
                if(!replay){
                    const auto format=q.at("pixel_format").get<std::string>();
                    if(format!="RGB565LE"&&format!="BGRX8")throw std::runtime_error("Unsupported pixel format");
                    last_format=format=="BGRX8"?1:0;
                    last_sequence=q.at("sequence").get<uint32_t>();
                    if(!last_sequence)throw std::runtime_error("Zero frame ID");
                    const uint64_t bytes=1920ull*1080*(last_format?4:2);
                    const fs::path input=q.at("input").get<std::string>();
                    if(fs::file_size(input)!=bytes)throw std::runtime_error("Input size mismatch");
                    std::vector<char> pixels(bytes);
                    auto t=Clock::now();std::ifstream f(input,std::ios::binary);f.read(pixels.data(),pixels.size());
                    if(!f)throw std::runtime_error("Incomplete raw input");
                    input_read_ms=ms(t);
                    t=Clock::now();memory.write(SOURCE_OFFSET,pixels.data(),bytes);upload_ms=ms(t);
                    if(q.value("verify_source",false)){
                        const auto verify_started=Clock::now();
                        std::vector<char> actual(bytes);memory.read(actual.data(),SOURCE_OFFSET,bytes);
                        if(actual!=pixels){
                            uint64_t count=0,first=bytes,last=0;
                            for(uint64_t i=0;i<bytes;++i)if(actual[i]!=pixels[i]){++count;first=std::min(first,i);last=i;}
                            std::cerr<<Json{{"source_mismatch_bytes",count},{"first_offset",first},{"last_offset",last},
                                {"allocation_base",base},{"source_bytes",bytes},{"expected_first",static_cast<unsigned char>(pixels[first])},
                                {"actual_first",static_cast<unsigned char>(actual[first])}}.dump()<<std::endl;
                            fault(marker,"Full source verification mismatch");
                        }
                        source_verified=true;source_verification_ms=ms(verify_started);
                    }
                    resident=true;
                }else if(!resident)throw std::runtime_error("Replay without uploaded pixels");
                Json results=Json::array();
                const auto batch_start=Clock::now();
                for(uint32_t repeat=0;repeat<repetitions;++repeat){
                    const auto started=Clock::now();
                    const uint32_t seq=replay?++last_sequence:last_sequence;
                    const std::vector<uint32_t> words={seq,static_cast<uint32_t>(base+SOURCE_OFFSET),
                        static_cast<uint32_t>(base+OUTPUT_OFFSET),static_cast<uint32_t>(OUTPUT_CAPACITY),last_format};
                    for(size_t i=0;i<words.size();++i)regs.write(REG+16+i*4,words[i],false);
                    for(size_t i=0;i<words.size();++i)if(regs.read(REG+16+i*4,false)!=words[i])throw std::runtime_error("JPEG descriptor readback mismatch");
                    const double descriptor_ms=ms(started);
                    auto t=Clock::now();
                    try{
                        regs.write(REG,1,false);uint32_t status=0;
                        do{
                            status=regs.read(REG+4,false);
                            if(ms(t)>10000)fault(marker,"JPEG DMA deadline exceeded");
                            if(!(status&2))std::this_thread::sleep_for(std::chrono::microseconds(100));
                        }while(!(status&2));
                        if(status&1 || ((status>>4)&15) || status&8 || regs.read(REG+8,false)!=seq)
                            fault(marker,"Invalid JPEG completion status/frame ID");
                    }catch(const std::exception& e){fault(marker,e.what());}
                    const double pl_poll_ms=ms(t);
                    const uint32_t bytes=regs.read(REG+12,false),cycles=regs.read(REG+48,false),core_cycles=regs.read(REG+52,false);
                    if(bytes<100 || bytes>OUTPUT_CAPACITY || !cycles)fault(marker,"Invalid JPEG size/cycle count");
                    Json result={{"frame_id",seq},{"source_uploaded",!replay},{"input_read_ms",input_read_ms},{"upload_ms",upload_ms},
                        {"source_verified",!replay&&source_verified},{"source_verification_ms",source_verification_ms},
                        {"descriptor_ms",descriptor_ms},{"pl_poll_ms",pl_poll_ms},{"hw_cycles",cycles},{"encoder_cycles",core_cycles},
                        {"hardware_ms",cycles/100000.0},{"input_wait_cycles",regs.read(REG+56,false)},
                        {"output_wait_cycles",regs.read(REG+60,false)},{"read_blocks",regs.read(REG+64,false)},
                        {"write_blocks",regs.read(REG+68,false)},{"jpeg_bytes",bytes},{"record_offset",record_bytes}};
                    double readback_ms=0,record_ms=0;
                    if(readback){
                        // Keep SDK transfers on native DDR beat boundaries;
                        // write only the real JPEG bytes to the recording.
                        std::vector<char> jpeg((static_cast<uint64_t>(bytes)+63)&~63ull);
                        t=Clock::now();memory.read(jpeg.data(),OUTPUT_OFFSET,jpeg.size());readback_ms=ms(t);
                        if(static_cast<unsigned char>(jpeg[0])!=255 || static_cast<unsigned char>(jpeg[1])!=216 ||
                           static_cast<unsigned char>(jpeg[bytes-2])!=255 || static_cast<unsigned char>(jpeg[bytes-1])!=217)
                            fault(marker,"JPEG SOI/EOI missing after DDR readback");
                        if(save){
                            if(record_bytes+bytes>256ull*1024*1024)throw std::runtime_error("Bounded recording reached 256 MiB");
                            t=Clock::now();write_all(record_fd,jpeg.data(),bytes);record_ms=ms(t);record_bytes+=bytes;
                        }
                    }
                    // Allocation guards are cheap and independent of image content.
                    std::vector<char> actual(64);
                    for(uint64_t offset:std::vector<uint64_t>{0,OUTPUT_OFFSET-64,TOTAL-64}){
                        memory.read(actual.data(),offset,64);if(actual!=guard)fault(marker,"JPEG allocation guard changed");
                    }
                    result["readback_ms"]=readback_ms;result["record_ms"]=record_ms;
                    result["worker_ms"]=ms(started);results.push_back(result);++frame_count;
                }
                double sync_ms=0;
                if(save && q.value("sync",false)){
                    const auto t=Clock::now();
                    if(::fsync(record_fd)!=0)throw std::runtime_error("Replay recording sync failed");
                    sync_ms=ms(t);
                }
                const double batch_ms=ms(batch_start);
                emit({{"status",replay?"replayed":"compressed"},{"backend","JPG1_FPGA"},{"source",replay?"resident_DDR_replay":"new_SSH_frame"},
                    {"iterations",repetitions},{"results",results},{"batch_ms",batch_ms},{"record_bytes",record_bytes},
                    {"batch_fps",1000.0*repetitions/batch_ms},{"readback",readback},{"record",save},{"fsync_ms",sync_ms}});
            }
            const auto t=Clock::now();if(::fsync(record_fd)!=0)throw std::runtime_error("Recording sync failed");
            ::close(record_fd);record_fd=-1;
            emit({{"status","closed"},{"frames",frame_count},{"record_bytes",record_bytes},{"fsync_ms",ms(t)},{"device_closed",false}});
        }
        Device::Close(device);
        return 0;
    }catch(const std::exception& e){
        if(record_fd>=0)::close(record_fd);
        emit({{"status","error"},{"message",e.what()}});return 2;
    }
}
