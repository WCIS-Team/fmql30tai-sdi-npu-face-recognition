#pragma once
// Linux transport only: no codec, OpenCV, camera, model or device session.
#include <arpa/inet.h>
#include <fcntl.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>
#include <algorithm>
#include <atomic>
#include <cerrno>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace wcis {
struct RawFrameInfo {
    std::string stream_id, source = "camera";
    uint64_t frame_id = 0, timestamp_us = 0;
    int width = 0, height = 0, stride_bytes = 0;
};
struct RawStreamStats { uint64_t accepted, sent, failed, replaced, last_send_us, last_payload_bytes; };
struct RawStreamOptions { std::string host; int port = 8088, timeout_ms = 1000; };

inline std::string raw_metadata(const RawFrameInfo& f) {
    if (f.stream_id.empty() || f.stream_id.size() > 80 ||
        f.stream_id.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-") != std::string::npos ||
        (f.source != "camera" && f.source != "demo" && f.source != "unverified") ||
        f.width < 1 || f.width > 4096 || f.height < 1 || f.height > 4096 ||
        f.stride_bytes < f.width * 2 || f.stride_bytes > f.width * 2 + 4096 ||
        uint64_t(f.stride_bytes) * f.height > 8 * 1024 * 1024)
        throw std::invalid_argument("Invalid raw frame descriptor");
    return "{\"schema_version\":1,\"stream_id\":\"" + f.stream_id + "\",\"frame_id\":\"" +
        std::to_string(f.frame_id) + "\",\"timestamp_us\":\"" + std::to_string(f.timestamp_us) +
        "\",\"timestamp_basis\":\"ps_dma_done_monotonic\",\"source\":\"" + f.source +
        "\",\"pixel_format\":\"RGB565LE\",\"width\":" + std::to_string(f.width) +
        ",\"height\":" + std::to_string(f.height) + ",\"stride_bytes\":" + std::to_string(f.stride_bytes) + "}";
}

class LatestRawPublisher {
    using Clock = std::chrono::steady_clock;
    struct Packet { std::string metadata; std::vector<unsigned char> pixels; };
    RawStreamOptions options_;
    sockaddr_in endpoint_{};
    int fd_ = -1; // Only the network worker accesses it; close after joining.
    std::mutex mutex_;
    std::condition_variable condition_;
    Packet pending_;
    bool available_ = false, stopping_ = false;
    std::thread worker_;
    std::atomic<uint64_t> accepted_{0}, sent_{0}, failed_{0}, replaced_{0}, send_us_{0}, bytes_{0};

    bool wait_socket(int fd, short events, Clock::time_point deadline) {
        while (true) {
            auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(deadline-Clock::now()).count();
            if (ms <= 0) return false;
            pollfd p{fd, events, 0};
            int n = poll(&p, 1, static_cast<int>(ms));
            if (n > 0) return (p.revents & events) != 0;
            if (n == 0 || errno != EINTR) return false;
        }
    }
    bool post(const Packet& packet) {
        auto deadline = Clock::now() + std::chrono::milliseconds(options_.timeout_ms);
        if (fd_ < 0) {
            fd_ = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
            if (fd_ < 0) return false;
            int flags = fcntl(fd_, F_GETFL, 0);
            if (flags < 0 || fcntl(fd_, F_SETFL, flags | O_NONBLOCK) < 0) return false;
            if (connect(fd_, reinterpret_cast<const sockaddr*>(&endpoint_), sizeof(endpoint_)) < 0 && errno != EINPROGRESS) return false;
            if (!wait_socket(fd_, POLLOUT, deadline)) return false;
            int error = 0; socklen_t size = sizeof(error);
            if (getsockopt(fd_, SOL_SOCKET, SO_ERROR, &error, &size) < 0 || error) return false;
        }
        const int fd = fd_;
        auto send_all = [&](const void* bytes, size_t length) {
            const char* data = static_cast<const char*>(bytes);
            while (length) {
                if (!wait_socket(fd, POLLOUT, deadline)) return false;
                ssize_t n = send(fd, data, length, MSG_NOSIGNAL);
                if (n < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
                if (n <= 0) return false;
                data += n; length -= static_cast<size_t>(n);
            }
            return true;
        };
        const std::string header = "POST /api/frame HTTP/1.1\r\nHost: " + options_.host + ":" + std::to_string(options_.port) +
            "\r\nConnection: keep-alive\r\nContent-Type: application/octet-stream\r\nContent-Length: " +
            std::to_string(4 + packet.metadata.size() + packet.pixels.size()) + "\r\n\r\n";
        uint32_t length = htonl(static_cast<uint32_t>(packet.metadata.size()));
        if (!send_all(header.data(), header.size()) || !send_all(&length, 4) ||
            !send_all(packet.metadata.data(), packet.metadata.size()) || !send_all(packet.pixels.data(), packet.pixels.size())) return false;
        std::string response;
        while (response.size() < 4096) {
            if (!wait_socket(fd, POLLIN, deadline)) return false;
            char buf[512]; ssize_t n = recv(fd, buf, sizeof(buf), 0);
            if (n < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
            if (n <= 0) return false;
            response.append(buf, static_cast<size_t>(n));
            if (response.find("\r\n\r\n") != std::string::npos)
                return response.rfind("HTTP/1.1 204 ", 0) == 0 || response.rfind("HTTP/1.0 204 ", 0) == 0;
        }
        return false;
    }
    void loop() {
        while (true) {
            Packet packet;
            {
                std::unique_lock<std::mutex> lock(mutex_);
                condition_.wait(lock, [&] { return stopping_ || available_; });
                if (stopping_) return;
                packet = std::move(pending_); available_ = false;
            }
            auto start = Clock::now();
            bool sent = false;
            try { sent = post(packet); } catch (...) { sent = false; }
            if (sent) ++sent_;
            else { ++failed_; if (fd_ >= 0) { ::close(fd_); fd_ = -1; } }
            send_us_ = std::chrono::duration_cast<std::chrono::microseconds>(Clock::now()-start).count();
            bytes_ = packet.pixels.size();
        }
    }
public:
    explicit LatestRawPublisher(RawStreamOptions options) : options_(std::move(options)) {
        if (options_.port < 1 || options_.port > 65535 || options_.timeout_ms < 100 || options_.timeout_ms > 5000 ||
            inet_pton(AF_INET, options_.host.c_str(), &endpoint_.sin_addr) != 1)
            throw std::invalid_argument("Expected numeric receiver IPv4, port and bounded timeout");
        endpoint_.sin_family = AF_INET; endpoint_.sin_port = htons(static_cast<uint16_t>(options_.port));
        worker_ = std::thread(&LatestRawPublisher::loop, this);
    }
    LatestRawPublisher(const LatestRawPublisher&) = delete;
    LatestRawPublisher& operator=(const LatestRawPublisher&) = delete;
    ~LatestRawPublisher() { stop(); }
    bool publish(const RawFrameInfo& info, std::vector<unsigned char>&& pixels) {
        auto metadata = raw_metadata(info);
        if (pixels.size() != size_t(info.stride_bytes) * info.height) throw std::invalid_argument("Pixel length mismatch");
        std::lock_guard<std::mutex> lock(mutex_);
        if (stopping_) return false;
        if (available_) ++replaced_;
        pending_ = Packet{std::move(metadata), std::move(pixels)};
        available_ = true; ++accepted_; condition_.notify_one(); return true;
    }
    RawStreamStats stats() const { return {accepted_, sent_, failed_, replaced_, send_us_, bytes_}; }
    void stop() {
        { std::lock_guard<std::mutex> lock(mutex_); stopping_ = true; available_ = false; pending_ = {}; }
        condition_.notify_all(); if (worker_.joinable()) worker_.join();
        if (fd_ >= 0) { ::close(fd_); fd_ = -1; }
    }
};
}
