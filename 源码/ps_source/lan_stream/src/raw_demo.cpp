#include "wcis_raw_publisher.hpp"
#include <iostream>
int main(int argc, char** argv) {
    try {
        if (argc != 4) throw std::invalid_argument("raw_demo IPv4 PORT SECONDS");
        int seconds = std::stoi(argv[3]);
        if (seconds < 1 || seconds > 30) throw std::invalid_argument("Seconds outside 1..30");
        wcis::LatestRawPublisher publisher({argv[1], std::stoi(argv[2]), 300});
        auto end = std::chrono::steady_clock::now()+std::chrono::seconds(seconds);
        uint64_t seq = 0;
        const std::string stream_id = "cpp-demo-" + std::to_string(getpid());
        while (std::chrono::steady_clock::now() < end) {
            std::vector<unsigned char> pixels(64*36*2);
            for (size_t n=0; n<pixels.size(); n+=2) { pixels[n]=0; pixels[n+1]=0xf8; }
            uint64_t ts = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
            publisher.publish({stream_id, "demo", ++seq, ts, 64, 36, 128}, std::move(pixels));
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
        publisher.stop(); auto s=publisher.stats();
        std::cout << "accepted=" << s.accepted << " sent=" << s.sent << " failed=" << s.failed << " replaced=" << s.replaced << '\n';
        return 0;
    } catch(const std::exception& e) { std::cerr << e.what() << '\n'; return 2; }
}
