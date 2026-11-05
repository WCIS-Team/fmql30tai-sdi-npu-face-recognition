#pragma once
// Identical VPU encoder/format checks to the deployed SDI viewer.
#include "pipeline/vpu/vpu.h"
#include <poll.h>
class JpegEncoder:public vpu::Encoder {
 uint32_t width_,height_;
public:
 JpegEncoder(uint32_t fps=30,uint32_t width=960,uint32_t height=540,int quality=80):Encoder("/dev/video0",height,width,V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE,V4L2_PIX_FMT_NV12,V4L2_BUF_TYPE_VIDEO_CAPTURE,V4L2_PIX_FMT_JPEG,2),width_(width),height_(height){
  if((width!=960||height!=540)&&(width!=1280||height!=720)&&(width!=1920||height!=1080))throw std::runtime_error("Unsupported bounded VPU dimensions");
  if(quality<1||quality>95)throw std::runtime_error("VPU quality outside contract");
  setFrameRate(fps);
  v4l2_control c{};c.id=0x009d0903;c.value=quality;
  if(ioctl(fd_,VIDIOC_S_CTRL,&c))throw std::runtime_error("VPU JPEG quality rejected");
  auto& f=input_format_.fmt.pix_mp;
  if(f.width!=width||f.height!=height||(f.num_planes!=1&&f.num_planes!=2)||f.plane_fmt[0].bytesperline!=width||
     (f.num_planes==2&&f.plane_fmt[1].bytesperline!=width))
   throw std::runtime_error("VPU NV12 geometry/stride contract mismatch");
 }
 size_t inputBytes(){size_t n=0;for(auto x:input_buffers.at(0)->byte_per_planes_)n+=x;return n;}
 size_t uvOffset(){return input_format_.fmt.pix_mp.num_planes==2?input_buffers.at(0)->byte_per_planes_.at(0):width_*height_;}
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
