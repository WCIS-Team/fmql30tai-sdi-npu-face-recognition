// Deterministic 1080p30 source; real Verilated RTL, no board SDK.
#include "Vwcis_sdi_jpeg_stream.h"
#include "verilated.h"
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>

int main(int argc,char** argv) {
    Verilated::commandArgs(argc,argv);
    Vwcis_sdi_jpeg_stream top;
    const bool noisy=argc>1 && std::string(argv[1])=="noise";
    uint64_t next_logic=3333,next_cam=6734,time=0;
    uint64_t completed_times[8]={};unsigned complete=0,cycles=0,x=0,y=0,source_frames=0;
    uint32_t random=0x5739ac81;
    bool started=false;FILE* output=nullptr;unsigned output_frame=0,active_frames=0;
    top.clk=0;top.cam_clk=0;top.reset=0;top.enable=1;top.cam_locked=1;
    top.cam_vsync=0;top.cam_de=0;top.cam_rgb=0;top.m_ready=1;top.downstream_idle=1;
    top.eval();
    const uint64_t end=160000000000ULL; // 160 ms simulated time
    while(time<end && !Verilated::gotFinish()) {
        time=next_logic<next_cam?next_logic:next_cam;
        top.reset=time>=20000&&time<200000;
        bool logic_edge=time==next_logic,cam_edge=time==next_cam;
        if(logic_edge && top.clk==0 && !top.reset && top.m_valid && top.m_ready) {
            if(top.m_sof) {
                if(output) {std::fclose(output);output=nullptr;}
                output_frame=top.m_frame_id;
                std::string name="rtl-"+std::string(noisy?"noise":"gradient")+"-"+std::to_string(output_frame)+".jpg";
                output=std::fopen(name.c_str(),"wb");if(!output)return 2;
            }
            if(output)std::fputc(top.m_data,output);
            if(top.m_last) {
                if(!output||top.cam_vsync)return 3;
                std::fclose(output);output=nullptr;
                completed_times[complete++]=time;
                std::printf("FRAME id=%u time_ps=%llu\n",output_frame,(unsigned long long)time);std::fflush(stdout);
            }
        }
        if(logic_edge) {top.clk=!top.clk;next_logic+=3333;}
        if(cam_edge) {
            top.cam_clk=!top.cam_clk;next_cam+=6734;
            if(top.cam_clk==0 && !top.reset) {
                if(!started && time>300000 && top.idle)started=true;
                if(started && source_frames<3) {
                    if(x==0&&y==0)++active_frames;
                    top.cam_vsync=y<1080;
                    top.cam_de=y<1080&&x<1920;
                    if(top.cam_de) {
                        random^=random<<13;random^=random>>17;random^=random<<5;
                        top.cam_rgb=noisy?(random&0xffffff):
                            (((x*255/1919)<<16)|((y*255/1079)<<8)|(((x/32+y/32)&1)?255:0));
                    }
                    if(++x==2200) {x=0;if(++y==1125) {y=0;++source_frames;}}
                } else {top.cam_vsync=0;top.cam_de=0;}
            }
        }
        top.eval();
        if(logic_edge && top.clk && top.abort_frame && output) {std::fclose(output);output=nullptr;}
        if(complete>=3)break;
        if(++cycles==0)return 4;
    }
    if(output)std::fclose(output);
    const double fps=complete>1?1e12*(complete-1)/(completed_times[complete-1]-completed_times[0]):0;
    std::printf("SUMMARY pattern=%s completed=%u rejected=%u active_frames=%u full_input_periods=%u interval_fps=%.6f simulated_ms=%.6f\n",
        noisy?"noise":"gradient",complete,top.frames_rejected,active_frames,source_frames,fps,time/1e9);
    top.final();return complete==0?5:0;
}
