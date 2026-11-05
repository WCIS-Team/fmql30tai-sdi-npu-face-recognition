#pragma once
#include <cstdint>
#include <stdexcept>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

// Fixed camera aperture of the admitted SDI2 design. This is not a general
// register tool: no NPU/FAC1 addresses, resets, or allocator calls are exposed.
class CameraMmio {
 static constexpr uint64_t BASE=0x40080000;
 void* mapping_=MAP_FAILED;
 static void barrier(){asm volatile("dmb sy" ::: "memory");}
public:
 CameraMmio(){
  const int fd=::open("/dev/mem",O_RDWR|O_SYNC|O_CLOEXEC);
  if(fd<0)throw std::runtime_error("Cannot map admitted camera registers");
  mapping_=mmap(nullptr,4096,PROT_READ|PROT_WRITE,MAP_SHARED,fd,BASE);
  ::close(fd);
  if(mapping_==MAP_FAILED)throw std::runtime_error("Camera register mapping failed");
 }
 CameraMmio(const CameraMmio&)=delete;
 CameraMmio& operator=(const CameraMmio&)=delete;
 ~CameraMmio(){if(mapping_!=MAP_FAILED)munmap(mapping_,4096);}
 uint32_t read(uint32_t offset)const{
  if(offset%4||offset>0x130)throw std::runtime_error("Camera register read outside contract");
  barrier();const auto value=static_cast<volatile uint32_t*>(mapping_)[offset/4];barrier();return value;
 }
 void write(uint32_t offset,uint32_t value){
  if(offset!=4&&offset!=0x50)throw std::runtime_error("Camera worker write outside contract");
  barrier();static_cast<volatile uint32_t*>(mapping_)[offset/4]=value;barrier();
 }
 static void before_copy(){barrier();}
};
