#include "wcis_jpeg_publisher.hpp"
#include <filesystem>
#include <iostream>

static cv::Mat test_frame(int index) {
    cv::Mat frame(360,640,CV_8UC3,cv::Scalar(27,19,12));
    const cv::Scalar colors[] = {{25,35,240},{35,190,35},{230,75,30},{210,200,30},{140,50,160},{180,180,180}};
    for(int n=0;n<6;++n) cv::rectangle(frame,cv::Rect(n*106,120,106,145),colors[n],cv::FILLED);
    cv::putText(frame,"DEMO / NO CAMERA",{30,50},cv::FONT_HERSHEY_SIMPLEX,1,{230,230,230},2);
    cv::putText(frame,"test frame "+std::to_string(index),{30,91},cv::FONT_HERSHEY_SIMPLEX,.6,{170,170,170},1);
    cv::circle(frame,{35+(index%10)*60,300},16,{210,255,100},cv::FILLED);
    return frame;
}
int main(int argc,char** argv) {
    try {
        if(argc==3 && std::string(argv[1])=="--export") {
            std::filesystem::create_directories(argv[2]);
            for(int n=0;n<10;++n) {
                auto path=std::filesystem::path(argv[2])/("demo-"+std::to_string(n)+".jpg");
                if(!cv::imwrite(path.string(),test_frame(n),{cv::IMWRITE_JPEG_QUALITY,75})) throw std::runtime_error("JPEG export failed");
            }
            std::cout<<"Exported 10 labelled test images; no hardware was opened.\n";return 0;
        }
        if(argc<4) {std::cout<<"Usage: wcis_stream_demo IPv4 PORT SECONDS [rgb565]\n       wcis_stream_demo --export DIR\n";return 2;}
        wcis::StreamOptions options;options.host=argv[1];options.port=std::stoi(argv[2]);options.source="demo";
        int seconds=std::stoi(argv[3]);if(seconds<1||seconds>300)throw std::invalid_argument("seconds must be 1..300");
        wcis::LatestJpegPublisher publisher(options);
        auto start=std::chrono::steady_clock::now();
        uint64_t sequence=0;
        while(std::chrono::steady_clock::now()-start<std::chrono::seconds(seconds)) {
            cv::Mat frame=test_frame(static_cast<int>(sequence));
            if(argc==5 && std::string(argv[4])=="rgb565") {
                cv::Mat packed;cv::cvtColor(frame,packed,cv::COLOR_BGR2BGR565);
                publisher.publishRgb565(packed,sequence++);
            }else publisher.publishBgr(frame,sequence++);
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(200));publisher.stop();
        auto s=publisher.stats();
        std::cout<<"{\"sent\":"<<s.sent<<",\"failed\":"<<s.failed<<",\"accepted\":"<<s.accepted
            <<",\"replaced\":"<<s.replaced<<",\"rate_limited\":"<<s.rate_limited<<",\"jpeg_bytes\":"<<s.last_jpeg_bytes<<"}\n";
        return s.sent>0&&s.failed==0?0:1;
    }catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}
}
