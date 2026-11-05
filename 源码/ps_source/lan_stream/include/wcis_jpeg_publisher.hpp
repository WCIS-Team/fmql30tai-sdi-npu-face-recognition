#pragma once
// Linux PS/host component. Does not open iCraft, camera, VPU or NPU devices.
#include <opencv2/core.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include <arpa/inet.h>
#include <fcntl.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>
#include <atomic>
#include <algorithm>
#include <cerrno>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace wcis {
struct StreamOptions {
    std::string host; // Numeric IPv4 address of receiver; avoids unbounded DNS.
    int port = 8088;
    int max_width = 640, max_height = 360, fps = 10, quality = 75;
    int network_timeout_ms = 1500;
    std::string source = "unverified";
};
struct StreamStats {
    uint64_t accepted, sent, failed, replaced, rate_limited;
    uint64_t last_jpeg_bytes, last_encode_us;
};

class LatestJpegPublisher {
    using Clock = std::chrono::steady_clock;
    struct Frame { cv::Mat owned; uint64_t sequence; bool rgb565; };
    StreamOptions options_;
    sockaddr_in endpoint_{};
    std::mutex mutex_;
    std::condition_variable condition_;
    Frame pending_;
    bool available_ = false, stopping_ = false;
    Clock::time_point next_accept_{};
    std::thread worker_;
    std::atomic<uint64_t> accepted_{0}, sent_{0}, failed_{0}, replaced_{0}, rate_limited_{0};
    std::atomic<uint64_t> jpeg_bytes_{0}, encode_us_{0};

    bool wait_socket(int fd, short events, Clock::time_point deadline) const {
        while (true) {
            int ms = static_cast<int>(std::chrono::duration_cast<std::chrono::milliseconds>(deadline - Clock::now()).count());
            if (ms <= 0) return false;
            pollfd p{fd, events, 0};
            int result = poll(&p, 1, ms);
            if (result > 0) return (p.revents & events) != 0;
            if (result == 0 || errno != EINTR) return false;
        }
    }
    bool post(const std::vector<unsigned char>& jpeg, uint64_t sequence) const {
        int fd = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
        if (fd < 0) return false;
        struct Close { int fd; ~Close() { ::close(fd); } } close{fd};
        int flags = fcntl(fd, F_GETFL, 0);
        if (flags < 0 || fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0) return false;
        auto deadline = Clock::now() + std::chrono::milliseconds(options_.network_timeout_ms);
        if (connect(fd, reinterpret_cast<const sockaddr*>(&endpoint_), sizeof(endpoint_)) < 0 && errno != EINPROGRESS) return false;
        if (!wait_socket(fd, POLLOUT, deadline)) return false;
        int error = 0; socklen_t size = sizeof(error);
        if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &size) < 0 || error != 0) return false;
        std::string headers = "POST /ingest HTTP/1.1\r\nHost: " + options_.host + ":" + std::to_string(options_.port) +
            "\r\nContent-Type: image/jpeg\r\nConnection: close\r\nX-Frame-Source: " + options_.source +
            "\r\nX-Frame-Sequence: " + std::to_string(sequence) + "\r\nContent-Length: " + std::to_string(jpeg.size()) + "\r\n\r\n";
        auto send_all = [&](const void* bytes, size_t length) {
            const char* current = static_cast<const char*>(bytes);
            while (length) {
                if (!wait_socket(fd, POLLOUT, deadline)) return false;
                ssize_t count = send(fd, current, length, MSG_NOSIGNAL);
                if (count < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
                if (count <= 0) return false;
                current += count; length -= static_cast<size_t>(count);
            }
            return true;
        };
        if (!send_all(headers.data(), headers.size()) || !send_all(jpeg.data(), jpeg.size())) return false;
        std::string response;
        while (response.size() < 4096) {
            if (!wait_socket(fd, POLLIN, deadline)) return false;
            char buffer[512];
            ssize_t count = recv(fd, buffer, sizeof(buffer), 0);
            if (count < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
            if (count <= 0) return false;
            response.append(buffer, static_cast<size_t>(count));
            if (response.find("\r\n\r\n") != std::string::npos)
                return response.rfind("HTTP/1.1 204 ", 0) == 0 || response.rfind("HTTP/1.0 204 ", 0) == 0;
        }
        return false;
    }
    bool submit(const cv::Mat& frame, uint64_t sequence, bool rgb565) {
        if (frame.empty() || frame.type() != (rgb565 ? CV_8UC2 : CV_8UC3) || frame.cols > 4096 || frame.rows > 4096)
            throw std::invalid_argument("Expected bounded packed RGB565 or BGR8 frame");
        std::lock_guard<std::mutex> lock(mutex_);
        if (stopping_) return false;
        auto now = Clock::now();
        if (now < next_accept_) { ++rate_limited_; return false; }
        next_accept_ = now + std::chrono::microseconds(1000000 / options_.fps);
        // Deep-copy before the capture owner releases/reuses its DMA buffer.
        if (available_) ++replaced_;
        pending_ = Frame{frame.clone(), sequence, rgb565};
        available_ = true; ++accepted_;
        condition_.notify_one();
        return true;
    }
    void loop() {
        while (true) {
            Frame frame;
            {
                std::unique_lock<std::mutex> lock(mutex_);
                condition_.wait(lock, [&] { return stopping_ || available_; });
                if (stopping_) break;
                frame = std::move(pending_); available_ = false;
            }
            try {
                auto start = Clock::now();
                cv::Mat bgr;
                if (frame.rgb565) cv::cvtColor(frame.owned, bgr, cv::COLOR_BGR5652BGR);
                else bgr = frame.owned;
                double scale = std::min(1.0, std::min(double(options_.max_width) / bgr.cols, double(options_.max_height) / bgr.rows));
                cv::Mat resized;
                if (scale < 1) cv::resize(bgr, resized, cv::Size(std::max(1, int(bgr.cols * scale)), std::max(1, int(bgr.rows * scale))), 0, 0, cv::INTER_AREA);
                else resized = bgr;
                std::vector<unsigned char> jpeg;
                if (!cv::imencode(".jpg", resized, jpeg, {cv::IMWRITE_JPEG_QUALITY, options_.quality})) {
                    ++failed_; continue;
                }
                jpeg_bytes_ = jpeg.size();
                encode_us_ = std::chrono::duration_cast<std::chrono::microseconds>(Clock::now() - start).count();
                if (post(jpeg, frame.sequence)) ++sent_; else ++failed_;
            } catch (...) { ++failed_; }
        }
    }
public:
    explicit LatestJpegPublisher(StreamOptions options) : options_(std::move(options)) {
        if (options_.port < 1 || options_.port > 65535 || options_.fps < 1 || options_.fps > 30 ||
            options_.quality < 1 || options_.quality > 95 || options_.max_width < 1 || options_.max_width > 1920 ||
            options_.max_height < 1 || options_.max_height > 1080 || options_.network_timeout_ms < 100 || options_.network_timeout_ms > 5000 ||
            (options_.source != "demo" && options_.source != "camera" && options_.source != "unverified"))
            throw std::invalid_argument("Invalid LAN stream options");
        endpoint_.sin_family = AF_INET;
        endpoint_.sin_port = htons(static_cast<uint16_t>(options_.port));
        if (inet_pton(AF_INET, options_.host.c_str(), &endpoint_.sin_addr) != 1)
            throw std::invalid_argument("Receiver must be a numeric IPv4 address");
        worker_ = std::thread(&LatestJpegPublisher::loop, this);
    }
    ~LatestJpegPublisher() { stop(); }
    LatestJpegPublisher(const LatestJpegPublisher&) = delete;
    LatestJpegPublisher& operator=(const LatestJpegPublisher&) = delete;
    bool publishBgr(const cv::Mat& bgr, uint64_t frame_sequence) { return submit(bgr, frame_sequence, false); }
    // Packed little-endian: R[15:11], G[10:5], B[4:0]. Verify board byte order.
    bool publishRgb565(const cv::Mat& rgb565, uint64_t frame_sequence) { return submit(rgb565, frame_sequence, true); }
    StreamStats stats() const { return {accepted_, sent_, failed_, replaced_, rate_limited_, jpeg_bytes_, encode_us_}; }
    void stop() {
        { std::lock_guard<std::mutex> lock(mutex_); stopping_ = true; available_ = false; pending_.owned.release(); }
        condition_.notify_all();
        if (worker_.joinable()) worker_.join();
    }
};
}
