#pragma once
#include <fstream>
#include <iomanip>
#include <sstream>
// Publishes complete IDR-led Annex-B GOPs. Packaging runs outside the SDK owner.
class H264SegmentPublisher {
 std::filesystem::path root;std::vector<unsigned char> parameters;std::ofstream output;
 uint64_t sequence=0;unsigned count=0,fps;double origin,start,last=0;
 std::filesystem::path file(const char* extension,uint64_t number){std::ostringstream n;n<<"raw-"<<std::setw(9)<<std::setfill('0')<<number<<extension;return root/n.str();}
 void begin(){output.open(file(".h264.pending",sequence),std::ios::binary);output.write(reinterpret_cast<const char*>(parameters.data()),parameters.size());if(!output)throw std::runtime_error("H264 GOP open failed");}
 void publish(double end){
  if(!count)return;output.close();if(!output)throw std::runtime_error("H264 GOP write failed");
  std::filesystem::rename(file(".h264.pending",sequence),file(".h264",sequence));
  std::ofstream meta(file(".json.pending",sequence));meta<<nlohmann::json{{"sequence",sequence},{"start",start},{"end",end},{"origin",origin},{"frames",count},{"fps",fps}};meta.close();if(!meta)throw std::runtime_error("H264 GOP metadata write failed");
  std::filesystem::rename(file(".json.pending",sequence),file(".json",sequence));
  if(sequence>=16){std::filesystem::remove(file(".h264",sequence-16));std::filesystem::remove(file(".json",sequence-16));}
  ++sequence;count=0;
 }
public:
 H264SegmentPublisher(const std::filesystem::path& directory,const std::vector<unsigned char>& config,double timestamp,unsigned rate):root(directory),parameters(config),fps(rate),origin(timestamp),start(timestamp){
  if(config.empty()||config.size()>65536)throw std::runtime_error("H264 parameter set missing");std::filesystem::create_directories(root);begin();
 }
 void write(const std::vector<unsigned char>& data,double captured,bool key,unsigned){
  if(count&&captured<=last)throw std::runtime_error("H264 capture timestamps are not increasing");
  if(key&&count){publish(captured);start=captured;begin();}
  if(count>=300)throw std::runtime_error("H264 IDR interval exceeded bound");
  output.write(reinterpret_cast<const char*>(data.data()),data.size());if(!output)throw std::runtime_error("H264 GOP write failed");++count;last=captured;
 }
 void finish(){publish(last+1.0/fps);}
};
