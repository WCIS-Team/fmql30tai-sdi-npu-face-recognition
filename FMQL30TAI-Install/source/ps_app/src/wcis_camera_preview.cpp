// Model-free preview using the actual vendor SDICamera / udma MemChunk interfaces.
#include "pipeline/io/input/sdicamera.hpp"
#include "wcis_capture_wait.hpp"
#include "wcis_raw_publisher.hpp"
#include <yaml-cpp/yaml.h>
#include <csignal>
#include <iostream>
#include <fstream>
#include <cstdio>
#include <sstream>
#include <sys/file.h>

static volatile std::sig_atomic_t stopped = 0;
static void stop_handler(int) { stopped = 1; }
static uint64_t monotonic_us() {
    return std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
}
struct HardwareOwnership {
    int fd = -1;
    HardwareOwnership() {
        fd = open("/root/wcis-camera-preview/camera.lock", O_CREAT | O_RDWR | O_CLOEXEC, 0600);
        if (fd < 0 || flock(fd, LOCK_EX | LOCK_NB) != 0) {
            if (fd >= 0) close(fd);
            throw std::runtime_error("Camera hardware is already owned, or ownership cannot be established");
        }
    }
    ~HardwareOwnership() { if (fd >= 0) close(fd); }
};
int main(int argc, char** argv) {
    if (argc == 2 && std::string(argv[1]) == "--help") {
        std::cout << "wcis_camera_preview CONFIG.yaml RECEIVER_IPV4 [--probe-sdk|--inspect-camera|--run-camera|--run-vtc-test --attestation FILE]\n"
                     "Without a hardware mode: validate config only; no device is opened.\n"
                     "Hardware modes require a short-lived attestation for this boot and the verified factory BOOT.\n";
        return 0;
    }
    try {
        const bool hardware_mode = argc == 6;
        const bool probe = hardware_mode && std::string(argv[3]) == "--probe-sdk";
        const bool inspect = hardware_mode && std::string(argv[3]) == "--inspect-camera";
        const bool vtc_test = hardware_mode && std::string(argv[3]) == "--run-vtc-test";
        const bool readonly_mode = probe || inspect;
        if (argc != 3 && !(hardware_mode && (readonly_mode || vtc_test || std::string(argv[3]) == "--run-camera") && std::string(argv[4]) == "--attestation"))
            throw std::invalid_argument("Use --help for arguments");
        auto cfg = YAML::LoadFile(argv[1]);
        if (cfg["schema_version"].as<int>() != 1) throw std::invalid_argument("Unsupported config schema");
        auto input = cfg["input"]; auto output = cfg["transport"];
        if (input["type"].as<std::string>() != "sdi") throw std::invalid_argument("Only SDI adapter is implemented");
        const int width = input["width"].as<int>(), height = input["height"].as<int>();
        const int fps = output["fps"].as<int>(), wait_ms = input["timeout_ms"].as<int>();
        const int seconds = cfg["run_seconds"].as<int>();
        const int max_frames = cfg["max_frames"] ? cfg["max_frames"].as<int>() : 0;
        const auto base = input["register_base"].as<uint64_t>();
        if (width < 16 || width > 4096 || height < 1 || height > 4096 ||
            uint64_t(width)*height*2 > 8*1024*1024 || (uint64_t(width)*height*2)%8 ||
            fps < 1 || fps > 10 || wait_ms < 100 || wait_ms > 5000 || seconds < 1 || seconds > 3600 || max_frames < 0 || max_frames > 36000 || base != 0x40080000)
            throw std::invalid_argument("Geometry, rate, timeout or SDI register base outside supported contract");
        if (hardware_mode && !readonly_mode && input["vtc"].as<bool>() != vtc_test)
            throw std::invalid_argument("Source selection does not match camera/test mode");
        const auto url = input["device"].as<std::string>();
        if (url != "axi://zg330aiu?npu=0x40000000&dma=0x80000000")
            throw std::invalid_argument("Unverified device URL");
        wcis::RawStreamOptions options{argv[2], output["port"].as<int>(), output["timeout_ms"].as<int>()};
        in_addr address{};
        if (inet_pton(AF_INET, options.host.c_str(), &address) != 1 || options.port < 1 || options.port > 65535 || options.timeout_ms < 100 || options.timeout_ms > 5000)
            throw std::invalid_argument("Invalid receiver configuration");
        std::cout << "SDI " << width << 'x' << height << " RGB565LE, capture/send target=" << fps
                  << " fps, run=" << seconds << " seconds; models=not_connected\n";
        if (!hardware_mode) { std::cout << "Config validated. No board device opened.\n"; return 0; }
        // This is an operational compatibility gate, not a cryptographic attestation.
        // Only the reviewed deployer issues it after a reboot + read-only BOOT check.
        // Runtime boot identity and a short monotonic expiry reject stale/copied receipts.
        auto gate = YAML::LoadFile(argv[5]);
        std::string running_boot;
        std::ifstream boot_file("/proc/sys/kernel/random/boot_id");
        std::getline(boot_file, running_boot);
        const uint64_t now = monotonic_us();
        const uint64_t expiry = gate["expires_monotonic_us"].as<uint64_t>();
        if (gate["schema_version"].as<int>() != 1 || !boot_file || running_boot.empty() ||
            gate["boot_id"].as<std::string>() != running_boot ||
            gate["boot_sha256"].as<std::string>() != "0088581b738fdef741983d2dfd4dd52363d2d90fddc2fa4dafb30cfdb3b23fca" ||
            !gate["sdk_probe_permitted"].as<bool>() || expiry <= now || expiry-now > 300000000 ||
            (!readonly_mode && !gate["capture_permitted"].as<bool>()))
            throw std::runtime_error("Hardware entry blocked: missing, stale or incompatible BOOT attestation");
        HardwareOwnership ownership;
        if (!readonly_mode) {
            const char* review_path = "/root/wcis-camera-preview/capture-review-required.json";
            std::ifstream review_file(review_path);
            if (review_file.good()) {
                auto review = YAML::LoadFile(review_path);
                if (review["boot_id"].as<std::string>() == running_boot)
                    throw std::runtime_error("This boot has an unresolved capture failure; no new capture before peripheral review");
            }
        }
        if (!readonly_mode && std::rename(argv[5], (std::string(argv[5])+".used").c_str()) != 0)
            throw std::runtime_error("Cannot consume the one-use capture attestation; no hardware opened");
        std::signal(SIGINT, stop_handler); std::signal(SIGTERM, stop_handler);
        spdlog::set_level(spdlog::level::warn);
        std::cerr << "stage=device_open_begin\n" << std::flush;
        auto device = icraft::xrt::Device::Open(url.c_str());
        std::cerr << "stage=device_open_returned\n" << std::flush;
        auto fpai_device = device.cast<fpai::FPAIDevice>();
        std::cerr << "stage=frame_ctrl_version_read_begin\n" << std::flush;
        const uint32_t version = fpai_device.defaultRegRegion().read(base + 0x0c);
        std::cerr << "stage=frame_ctrl_version_read_returned version=0x" << std::hex << version << std::dec << '\n' << std::flush;
        if (version != 0x20230218)
            throw std::runtime_error("frame_ctrl version mismatch; camera configuration was not written");
        if (readonly_mode) {
            const uint32_t status = fpai_device.defaultRegRegion().read(base + 0x58);
            std::ostringstream evidence;
            evidence << "SDK_PROBE {\"version\":" << version << ",\"capture_status\":" << status << ",\"camera_configured\":false";
            if (inspect) {
                // Read only the documented factory register range. No request,
                // memory allocation, camera constructor or reset is performed.
                const std::pair<const char*, uint64_t> registers[] = {
                    {"request_pending",0x04},{"force_all_frames",0x08},{"image_enable",0x18},
                    {"continuous_mode",0x44},{"write_address_words",0x50},{"roi_x",0x5c},
                    {"roi_y",0x60},{"input_geometry",0x64},{"sampling_stride",0x68},
                    {"write_size_words",0x6c},{"reset_requested",0x70},{"done_to_fetch_cycles",0x84},
                    {"fetch_count",0x88},{"vtc_enable",0xb4}};
                evidence << ",\"registers\":{";
                bool first=true;
                for (const auto& item : registers) {
                    if (!first) evidence << ',';
                    first=false;
                    evidence << '"' << item.first << "\":" << static_cast<uint32_t>(fpai_device.defaultRegRegion().read(base+item.second));
                }
                evidence << '}';
            }
            evidence << "}\n";
            std::cout << evidence.str() << std::flush;
            return 0;
        }
        std::cerr << "stage=camera_configuration_begin\n" << std::flush;
        // Same constructor/configuration as the staged reference, without actors/model sessions.
        // PS output equals input size; no PS resize, no JPEG, no CPU color conversion.
        fpai::GenericSDICamera camera(0, fpai_device, width, height, camera_fmt::RGB565,
            width, height, camera_fmt::RGB565, crop_position::center,
            std::min(width, 640), std::min(height, 352), crop_position::center, base, vtc_test);
        std::cerr << "stage=camera_configuration_returned\n" << std::flush;
        auto chunk = fpai_device.getMemRegion("udma").malloc(camera.getBufferSize(), false);
        const uint64_t address_begin = chunk->begin.addr();
        if (address_begin % 8 || address_begin < 0x30100000 || address_begin+camera.getBufferSize() > 0x38100000)
            throw std::runtime_error("Vendor udma buffer is outside the verified 128 MiB DDR region");
        if ((camera.RegRead(0x18) & 1) != 1 || (camera.RegRead(0xb4) & 1) != static_cast<uint64_t>(vtc_test))
            throw std::runtime_error("SDI enable/test-pattern readback mismatch; capture was not requested");
        // No continuous or forced-all-frame capture. Only this app may own this peripheral.
        fpai_device.defaultRegRegion().write(base + 0x44, 0);
        fpai_device.defaultRegRegion().write(base + 0x08, 0); // disable forced all-frame mode
        wcis::LatestRawPublisher publisher(options);
        const std::string stream_id = std::string(vtc_test ? "vtc-" : "sdi-") + std::to_string(getpid()) + "-" + std::to_string(monotonic_us());
        auto end = std::chrono::steady_clock::now() + std::chrono::seconds(seconds);
        uint64_t sequence = 0;
        while (!stopped && std::chrono::steady_clock::now() < end) {
            const auto start = std::chrono::steady_clock::now();
            std::cerr << "stage=capture_request frame=" << sequence+1 << '\n' << std::flush;
            camera.take(chunk);
            auto result = wcis::wait_capture([&] { return static_cast<uint32_t>(camera.RegRead(0x58)); }, [] { return stopped != 0; }, wait_ms, true);
            if (result.state != wcis::CaptureState::Done) {
                std::cerr << "Capture stopped: state=" << static_cast<int>(result.state) << " status=0x" << std::hex << result.status
                          << ". No invalid pixels sent; no automatic reset/retry.\n";
                std::ofstream review_file("/root/wcis-camera-preview/capture-review-required.json", std::ios::trunc);
                review_file << "{\"boot_id\":\"" << running_boot << "\",\"capture_state\":" << static_cast<int>(result.state)
                            << ",\"status\":" << result.status << ",\"source\":\"" << (vtc_test ? "vtc_test" : "camera") << "\"}\n";
                review_file.flush();
                // The SDK has no proven DMA-cancel API. Do not return a possibly active buffer
                // to its allocator on error. Process exit; peripheral must be checked before rerun.
                publisher.stop(); std::cout.flush(); std::cerr.flush(); std::_Exit(3);
            }
            const uint64_t timestamp = monotonic_us(); // DMA completion, NOT sensor exposure time.
            std::vector<unsigned char> pixels(camera.getBufferSize());
            const auto read_start = monotonic_us();
            chunk.read(reinterpret_cast<char*>(pixels.data()), 0, pixels.size());
            const auto read_us = monotonic_us() - read_start;
            publisher.publish({stream_id, vtc_test ? "demo" : "camera", ++sequence, timestamp, width, height, width*2}, std::move(pixels));
            auto stats = publisher.stats();
            std::cout << "frame=" << sequence << " read_us=" << read_us << " sent=" << stats.sent
                      << " failed=" << stats.failed << " replaced=" << stats.replaced << " send_us=" << stats.last_send_us << '\n';
            if (max_frames && sequence >= static_cast<uint64_t>(max_frames)) break;
            auto next = start + std::chrono::microseconds(1000000/fps);
            while (!stopped && std::chrono::steady_clock::now() < next && std::chrono::steady_clock::now() < end)
                std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
        // A finite one-frame trial must give its queued packet time to receive
        // an HTTP acknowledgement. The transport remains bounded to two packets.
        if (!stopped && sequence) {
            const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(2*options.timeout_ms+100);
            while (std::chrono::steady_clock::now() < deadline) {
                const auto pending_stats = publisher.stats();
                if (pending_stats.sent+pending_stats.failed+pending_stats.replaced >= pending_stats.accepted) break;
                std::this_thread::sleep_for(std::chrono::milliseconds(5));
            }
        }
        publisher.stop();
        if (vtc_test) fpai_device.defaultRegRegion().write(base+0xb4, 0); // restore the real input after a completed test
        auto stats = publisher.stats();
        std::cout << "accepted=" << stats.accepted << " sent=" << stats.sent << " failed=" << stats.failed << " replaced=" << stats.replaced << '\n';
        return stats.sent ? 0 : 4;
    } catch (const std::exception& e) { std::cerr << "Preview error: " << e.what() << '\n'; return 2; }
}
