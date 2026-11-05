#pragma once
// Reuses the admitted 1080p capture worker from the validated H264 probe.
#include <functional>
struct DirectFrame{uint32_t id;double requested,completed;std::vector<unsigned char> raw;};
class DirectCamera {
 static constexpr uint64_t CAM=0x40080000;
 static constexpr size_t WIDTH=1920,HEIGHT=1080,RAW=WIDTH*HEIGHT*2;
 std::function<void(const std::string&)> fault;
 std::vector<MemChunk> buffers;std::array<const char*,2> pointers{};std::array<uint32_t,2> addresses{};
 CameraMmio regs;std::optional<unsigned> pending;double requested=0;
 std::shared_ptr<const DirectFrame> latest;std::mutex mutex;std::thread thread;std::atomic<bool> halt{false};
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
  auto image=std::make_shared<const DirectFrame>(DirectFrame{++captured,pts,completed,std::move(raw)});
  std::lock_guard<std::mutex> lock(mutex);latest=std::move(image);
 }
public:
 std::atomic<uint32_t> captured{0};std::atomic<uint64_t> requests{0};unsigned drained=0;
 explicit DirectCamera(const Device& dev,std::function<void(const std::string&)> failure,bool start=true):fault(std::move(failure)){
  auto r=dev.defaultRegRegion();
  if(r.read(CAM+12)!=0x20230218||r.read(CAM+4)||r.read(CAM+8)||r.read(CAM+0x44)||r.read(CAM+0x70))throw std::runtime_error("Trial camera firmware/busy mismatch");
  for(unsigned i=0;i<2;++i){
   auto b=dev.getMemRegion("udma").malloc(RAW,true,64);const auto addr=b->begin.addr();
   if(addr%64||addr<0x30100000||addr+RAW>0x38100000)throw std::runtime_error("Trial camera allocation outside admitted UDMA range");
   for(const auto& old:buffers)if(addr<old->begin.addr()+RAW&&old->begin.addr()<addr+RAW)throw std::runtime_error("Trial camera allocations overlap");
   pointers[i]=b->begin.cptr();addresses[i]=addr;buffers.push_back(b);
  }
  // Configure only the PS branch, preserving the FAC1/ImageMake route disabled.
  for(const auto& w:std::vector<std::pair<uint32_t,uint32_t>>{{0x18,0},{0x44,0},{8,0},{0xb4,0},{0x5c,1919},{0x60,1079},{0x64,(1920u<<16)|1080u},{0x68,0x11},{0x7c,WIDTH},{0x78,1},{0x6c,RAW/8}}){r.write(CAM+w.first,w.second);if(r.read(CAM+w.first)!=w.second||regs.read(w.first)!=w.second)throw std::runtime_error("Trial camera setup readback mismatch");}
  if(regs.read(12)!=r.read(CAM+12)||regs.read(0x100)!=0x53444932)throw std::runtime_error("Trial camera direct mapping not admitted");
  if(!start)return;
  grab(true);grab(true);
  thread=std::thread([this]{try{while(!halt&&!halt)grab();}catch(const std::exception& e){fault(e.what());}});
 }
 std::shared_ptr<const DirectFrame> next(uint32_t after){
  const double deadline=now()+2;
  for(;;){{std::lock_guard<std::mutex> lock(mutex);if(latest&&latest->id>after)return latest;}
   if(now()>deadline)throw std::runtime_error("Trial source did not advance");std::this_thread::sleep_for(std::chrono::milliseconds(1));}
 }
 void pause(){halt=true;if(thread.joinable())thread.join();if(pending){drain();++drained;}}
 std::shared_ptr<const DirectFrame> peek(){std::lock_guard<std::mutex> lock(mutex);return latest;}
 void resume(){if(thread.joinable()||pending)throw std::runtime_error("Direct capture is not quiescent");halt=false;thread=std::thread([this]{try{while(!halt)grab();}catch(const std::exception& e){fault(e.what());}});}
 std::shared_ptr<const DirectFrame> pull_paused(){if(thread.joinable()||pending)throw std::runtime_error("Camera is not quiescent");grab();if(pending){drain();++drained;}return next(0);}
 void close(){pause();buffers.clear();}
 ~DirectCamera(){if(thread.joinable())fault("Trial camera must be explicitly drained before destruction");}
};
