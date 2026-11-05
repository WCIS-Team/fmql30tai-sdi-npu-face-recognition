#pragma once
// Uses the board's vendor VPU API for encoding and libavformat for packaging.
#include "pipeline/vpu/vpu.h"
#include <poll.h>
struct H264Nals { bool vcl=false,idr=false;std::vector<unsigned char> parameters; };
inline H264Nals h264_nals(const std::vector<unsigned char>& data){
 H264Nals result;std::vector<std::pair<size_t,size_t>> starts;
 for(size_t i=0;i+3<data.size();++i){size_t n=0;if(data[i]==0&&data[i+1]==0){if(data[i+2]==1)n=3;else if(i+4<data.size()&&data[i+2]==0&&data[i+3]==1)n=4;}if(n){starts.emplace_back(i,i+n);i+=n-1;}}
 if(starts.empty()&&!data.empty())throw std::runtime_error("H264 Annex-B start code missing");
 for(size_t i=0;i<starts.size();++i){const auto h=starts[i].second,end=i+1<starts.size()?starts[i+1].first:data.size();unsigned type=data[h]&31;
  result.vcl|=type==1||type==5;result.idr|=type==5;
  if(type==7||type==8)result.parameters.insert(result.parameters.end(),data.begin()+starts[i].first,data.begin()+end);
 }return result;
}
class H264Encoder:public vpu::Encoder {
 unsigned w_,h_;
 void control(uint32_t id,int value){v4l2_control c{};c.id=id;c.value=value;if(ioctl(fd_,VIDIOC_S_CTRL,&c))throw std::runtime_error("H264 control rejected: "+std::to_string(id));}
public:
 H264Encoder(unsigned fps=30,uint32_t format=V4L2_PIX_FMT_UYVY,unsigned width=1920,unsigned height=1080):Encoder("/dev/video0",height,width,V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE,format,V4L2_BUF_TYPE_VIDEO_CAPTURE,V4L2_PIX_FMT_H264,6),w_(width),h_(height){
  if((width!=1920||height!=1080)&&(width!=960||height!=540))throw std::runtime_error("Unsupported bounded H264 dimensions");
  setFrameRate(fps);control(V4L2_CID_MPEG_VIDEO_H264_PROFILE,V4L2_MPEG_VIDEO_H264_PROFILE_MAIN);control(V4L2_CID_MPEG_VIDEO_H264_LEVEL,V4L2_MPEG_VIDEO_H264_LEVEL_4_1);
  control(V4L2_CID_MPEG_VIDEO_B_FRAMES,0);control(V4L2_CID_MVE_VIDEO_FRAME_REORDERING,0);control(V4L2_CID_MVE_VIDEO_P_FRAMES,fps-1);
  control(V4L2_CID_MPEG_VIDEO_H264_I_FRAME_QP,26);control(V4L2_CID_MPEG_VIDEO_H264_P_FRAME_QP,28);
  const unsigned bitrate=width==1920?4000000:2000000;
  control(V4L2_CID_MPEG_VIDEO_BITRATE,bitrate);control(V4L2_CID_MPEG_VIDEO_FRAME_RC_ENABLE,1);
  v4l2_rate_control rate{};rate.rc_type=V4L2_OPT_RATE_CONTROL_MODE_CONSTANT;rate.target_bitrate=bitrate;rate.maximum_bitrate=bitrate;
  if(ioctl(fd_,VIDIOC_S_MVX_RATE_CONTROL,&rate))throw std::runtime_error("VPU private rate-control API unavailable");
  const auto& f=input_format_.fmt.pix_mp;size_t bytes=0;for(auto n:input_buffers.at(0)->byte_per_planes_)bytes+=n;
  if(f.width!=width||f.height!=height||f.pixelformat!=format)throw std::runtime_error("VPU H264 input geometry mismatch");
  if(format==V4L2_PIX_FMT_UYVY){if(f.num_planes!=1||f.plane_fmt[0].bytesperline!=width*2||bytes!=size_t(width)*height*2)throw std::runtime_error("VPU H264 UYVY layout mismatch");}
  else if(format==V4L2_PIX_FMT_NV12){if((f.num_planes!=1&&f.num_planes!=2)||f.plane_fmt[0].bytesperline!=width||bytes<size_t(width)*height*3/2||bytes>16*1024*1024)throw std::runtime_error("VPU H264 NV12 layout mismatch");}
  else throw std::runtime_error("Unsupported H264 raw format");
  const auto& out=output_format_.fmt.pix;if(out.width!=width||out.height!=height||out.pixelformat!=V4L2_PIX_FMT_H264)throw std::runtime_error("VPU H264 output contract mismatch");
 }
 size_t inputBytes(){size_t n=0;for(auto x:input_buffers.at(0)->byte_per_planes_)n+=x;return n;}
 size_t uvOffset(){return input_format_.fmt.pix_mp.num_planes==2?input_buffers.at(0)->byte_per_planes_.at(0):size_t(w_)*h_;}
 bool take(std::vector<unsigned char>& data,int timeout){
  pollfd p{fd_,POLLIN,0};int n;do{n=poll(&p,1,timeout);}while(n<0&&errno==EINTR);
  if(!n)return false;if(n<0||!(p.revents&POLLIN))throw std::runtime_error("H264 output poll failed");
  v4l2_buffer b{};b.type=V4L2_BUF_TYPE_VIDEO_CAPTURE;b.memory=V4L2_MEMORY_MMAP;if(ioctl(fd_,VIDIOC_DQBUF,&b))throw std::runtime_error("H264 output dequeue failed");
  auto it=output_buffers.find(b.index);if(it==output_buffers.end())throw std::runtime_error("H264 output index invalid");
  const size_t offset=b.m.offset&4095,capacity=it->second->byte_per_planes_.at(0);
  if(offset>capacity||b.bytesused>capacity-offset||b.bytesused>5*1024*1024||(b.flags&V4L2_BUF_FLAG_ERROR))throw std::runtime_error("H264 output bounds/flags invalid");
  auto ptr=static_cast<unsigned char*>(it->second->ptr_[0])+offset;data.assign(ptr,ptr+b.bytesused);
  if(ioctl(fd_,VIDIOC_QBUF,&b))throw std::runtime_error("H264 output requeue failed");return true;
 }
};
#include "wcis_h264_segments.hpp"
