# H.264 预览与录像试验：1080p 独立编码通过，共存未通过（2026-10-29）

## 当前结论

用户目标为预览、录像改用 H.264；次要任务是 PL 原始画面直接交 VPU，且必须为完整 1920×1080，不能把 540p 回退当作直送成功。720p 裁边方案保持暂停。

**本轮没有交付或部署 H.264 替换版。** 独立的真实 1080p UYVY→VPU H.264 编码已通过有限窗口；加入现役人脸/PAD 工作负载后出现停帧。把 VPU 编码分到独立进程、禁用摄像头采集、仅编码固定内存帧，与 NPU 工作负载共存仍复现 MVX watchdog，说明摄像头、网页或 MP4 封装不是复现的必要条件。尚未唯一定位 SDK、驱动、固件、复位、内存或总线机制，不能写成某个物理原因已确认，也不能外推为芯片不支持 NPU/VPU 并发。

正式系统保留优化后的 540p VPU JPEG，应用 `/root/wcis-face/apps/camera-psopt-20261029`。没有修改 RTL、重做布局布线、更新位流或启动分区。实验源码及前端/录像适配均为**未接受的草稿**；不应仅凭构建通过而切换正式服务。

## 已得到的板端证据

| 用例 | 有效结果 | 验证边界 |
| --- | --- | --- |
| 固定内存 UYVY→VPU H.264 | 240 帧 / 约 8.00 秒；1920×1080 Main、无 B 帧；全帧解码、MP4 封装通过 | 无真实采集、无 NPU；保存样本复杂度有限 |
| 真实 SDI 1080p、独立采集线程→VPU H.264 | 900 帧 / 29.947 秒；900 帧全部解码；14,909,768 字节；进程采样约 0.249 CPU 核 | 约 30 秒原型；未接网页、录像或 NPU，不是整套系统性能 |
| 复用独立采集实现接回单 SDK owner | 一次空闲窗口约 30.16 fps、0.317 CPU 核 | 模型重放后视频停止推进，后续窗口也有启动后停帧 |
| 暂停采集、排空编码，整个识别请求期间分时 | 一次完整用例正常关闭；空闲约 30.07 fps，连续单脸/身份/双 PAD 重放约 4.17 fps；模型中位耗时约 380.8 ms | 识别负载下帧率明显不足；没有作为可用直播交付 |
| 540p RGB565→CPU NV12→H.264 对照 | 一个空闲窗口约 26.01 fps、0.316 CPU 核 | 模型工作负载下也停帧；不能仅归因于 1080p 数据量 |
| 轻量 NEON UYVY→NV12、缩小暂停窗口、模型预热等 | 编译通过，未得到可靠的共存通过结果 | 未接受这些策略；不把它们写成优化成功 |
| 省略 NPU `device.reset(1)` 的隔离实验 | 后续模型出现 `sync failed in op_id:756's output_tensor` | 省略复位不是通过的解决方案；没有给正式系统省略复位 |
| VPU 与 NPU 分进程，VPU 固定内存输入、SDK owner 禁用摄像头 | NPU 完成 12 次保存单脸重放；VPU 在约第 84 次提交处阻塞；内核 MVX watchdog | 不涉及真实摄像头、网页、封装；跨进程未解决共存问题 |

CPU 数取自有限进程采样窗口；900 帧用例包括采集、搬运、硬编及写出，不包含网页、录像进程或识别。约 4 Mbps 是该 1080p 测试码流的实测平均量级，不是所有场景的码率/画质保证；不能把上述数据当作正式吞吐或长期稳定性。

所有实验使用既有准入检查、SDK/摄像头锁和已核对的 UDMA 地址窗口。未正常结束或出现硬件隔离标记时保留证据，并正常重启回原配置；没有删除同启动标记后重试 SDK。最终恢复检查另见下文，不能把父脚本的启动命令成功等同于服务恢复。

## 应用草稿

- `ps_app/src/wcis_owner_h264.hpp`：厂商 VPU API 的 H.264 原型，6 个缓冲、无 B 帧、定期 IDR；尝试板端配套的私有率控 ioctl。`wcis_direct_capture.hpp` 复用真实采集、寄存器读回、双缓冲和启动映射检查；仍有整帧搬运，**不是零拷贝**。
- `ps_app/src/wcis_camera_owner.cpp`、`wcis_owner_kernels.hpp`：保留默认 MJPEG；H.264、540p 对照、1080p 直送及暂停/预热策略均由实验配置进入。SDK 仍保持单 owner；实验策略不能作为已验证的生产配置。
- `ps_app/src/wcis_h264_segments.hpp`：发布完整 IDR 起始 GOP，携带单调采集时间与样本数，保留有界窗口。`lan_stream/h264_packager.py` 使用现有 FFmpeg `-c:v copy` 封装，不做软件视频编码；生成 fMP4 片段并按采集时间放置时间线。
- `h264_media.py`、`h264_fragments.py`：按 owner、启动、会话和新鲜度读取有界片段，拒绝跨会话、非预期路径和不连续片段；解析 MP4 时间基与样本数。
- `h264_player.js`、`camera_panel.js`、`serve_photos.py`、`vpu_live_server.py`：MSE/fMP4 的预览草稿，保留原 MJPEG 路径。**未做真实浏览器播放验收**。
- `recording_service.py`、`recording_library.py`、`recording_panel.*`：H.264 GOP 预缓冲与 MP4 保存草稿；流复制收尾以生成从零开始、可定位的录像；保留旧 MJPEG 目录、时间索引回放、软删除、恢复和配额逻辑。新增 MP4 Range 回放路径。H.264 索引记载源片段采集时间，不能当作收尾后 MP4 的字节偏移索引。

## 已完成的软件验证

- 原录像 24 项回归、原 Frames 11 项回归、新增 H.264 片段/路径/时间基 7 项测试通过；三个 JavaScript 文件通过语法检查。它们不覆盖驱动共存、真实浏览器或长期录像。
- 板端对实际 H.264 码流的两个 GOP 做外部封装：60 帧、1920×1080、约 1.999989 秒、起始时间为零；完整解码通过。
- 板端独立录像组件测试生成 MP4，目录读取、软删除/恢复以及占用记账一致。测试使用任务目录和测试 Store，**不是正式 eMMC 录像服务、断电恢复或长稳录像验收**。
- AArch64 C++ 均在学校服务器的独立 `D:/yzd/tmp/wcis-camera-preview-h264-*` 任务中交叉编译；构建前复核工具及任务，使用独立缓存、临时目录及 MSYS2 参数约定，未改共享 SDK。
- 当前草稿最后一次原生构建收据：`build-receipt.json`；C++ SHA256 `61d6fc754756c6eb087bc41305d08401b9f76ffae876844930b1fc58d5df06c9`，学校任务 `wcis-camera-preview-h264-f463cee8`。构建通过不代表本目标通过。

阶段性尝试直接链接 libavformat 的源码曾遇到头文件缺失和静态 OpenCV/OpenJPEG 符号冲突；匹配板端版本后能构建，但未解决共存。最终草稿转为独立 FFmpeg 封装，原生 owner 不再新增 FFmpeg 链接依赖。板端驱动头枚举与泛化文档均不作为组合可用性的证明。

日志拉取助手曾覆盖本地待上传的构建收据，导致一次 NV12 用例在启动前被 SHA 断言拦截；该次未进入硬件，不计作驱动失败。助手已改为另存远端收据；不同脚本需使用相符的归档二进制和收据，不应把当前 owner 二进制直接交给旧 probe CLI。

## 最终恢复

`final-verification.json`：启动 `dace9468-2d7d-4d71-8767-b001caf6267a`，三个正式服务 active；健康、硬件准入及模型缓存 ready，960×540 帧号推进，短窗口约 29.35 fps；一次真实摄像头识别成功，现场 0 张脸。正式应用所有受管文件 SHA 匹配，75 个既有录像/索引/摘要文件与此前优化验收收据逐项匹配；录像 off，保留原自动清理设置。本次启动内核仅见 MVX 设备识别行，没有新的 watchdog/MMU 异常。

只读内存盘点：CMA 总量 256 MiB、正式 JPEG 状态下空闲约 127.7 MiB；udmabuf0 为已公布的 `0x30100000`、128 MiB、非 coherent。未获得 CMA debugfs 明细；这些快照不证明 H.264 内部缓冲与 SDK 是否重叠，也不能据此宣称 CMA 耗尽或地址冲突。没有探测猜测的物理地址。

## 剩余工作与时间判断

真正的接受条件仍是：1080p、新鲜连续画面、H.264、模型/身份/PAD 共存、网页播放、MP4 录像，以及整套 CPU、延迟、丢帧和容量验证。**当前共存这一关未通过，后面的网页/正式录像不能冒充完成。** 在两天还要覆盖其他优化和文档的约束下，不应继续承诺应用层换格式即可交付；需要对配套 SDK/驱动/固件及其设备复位、内存和同步契约作进一步定位，必要时取得厂商的已验证组合与技术支持。不擅自更换启动镜像或驱动。

## 来源

- 当前源码：本文列出的 `D:/renlianshibie/fpga_project` 文件。
- 任务证据：`D:/yzd/tmp/h264-preview-record-20261029`，包括 `none-result.json`、`capture-result.json`、`owner-*-trial.json`、`process-isolation.json`、`process-vpu.log`、`package-test-result.json`、`recording-test-result.json`、`cma-inventory.json`、`final-verification.json` 和各版构建收据、源码归档。
- 既有对照：`docs/uyvy-vpu-isolation-20261029.md`、`docs/ps-preview-software-20261029.md`，及后者原 75 文件散列收据。
- 补充快照：`D:/xiangmuwendang/WCIS-FPAI/repos/FPAI30TAI图像FPGA/README.md`；厂商 actor 的同步后 `device.reset(1)` 参见本地 `vendor/include/ai_example/yolov5_npu_actor.hpp`、`multinets_npu_actor.hpp`。没有用网站概述或历史 benchmark 替代当前实测。

日期依据为客户端 2026-10-29。同步归档至 `D:/bigfuture/竞赛/记录/2026-10-29.md`，不改写来源记录，不删除已有内容。
