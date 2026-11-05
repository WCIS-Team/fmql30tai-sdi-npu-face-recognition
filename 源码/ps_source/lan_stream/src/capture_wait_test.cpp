#include "wcis_capture_wait.hpp"
#include <iostream>
#include <stdexcept>
int main() {
    using wcis::CaptureState;
    auto check=[](bool value) { if(!value) throw std::runtime_error("Capture state check failed"); };
    check(wcis::wait_capture([]{return 1u;}, []{return false;}, 20).state == CaptureState::Done);
    check(wcis::wait_capture([]{return 5u;}, []{return false;}, 20).state == CaptureState::Error);
    check(wcis::wait_capture([]{return 0u;}, []{return true;}, 20).state == CaptureState::Interrupted);
    auto start=std::chrono::steady_clock::now();
    check(wcis::wait_capture([]{return 0u;}, []{return false;}, 20).state == CaptureState::Timeout);
    check(std::chrono::steady_clock::now()-start < std::chrono::milliseconds(200));
    check(wcis::wait_capture([]{return 1u;}, []{return false;}, 5, true).state == CaptureState::Timeout);
    unsigned reads=0;
    check(wcis::wait_capture([&]{ ++reads; return reads == 2 ? 0u : 1u; }, []{return false;}, 20, true).state == CaptureState::Done);
    check(reads==3);
    check(wcis::wait_capture([]{return 5u;}, []{return false;}, 20, true).state == CaptureState::Error);
    std::cout << "PASS done/error priority/interrupt/bounded timeout/stale completion rejection/new completion; no hardware\n";
}
