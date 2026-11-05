# UYVY 直接交 VPU：停帧定位与隔离试验（2026-10-29）

## 结论

**已确认阻塞位置，但未查明唯一根因，尚无通过持续实拍验收的新版本。** 本轮没有部署 1080p 候选。正式系统最终恢复为优化后的 `camera-psopt-20261029`、540p PS/VPU 预览。

确认的事实：

- VPU 可以编码 1920×1080 UYVY。纯 PS 内存探针不打开 iCraft 设备、不运行模型、不启动摄像头 DMA，提交/返回 302 帧，约 10 秒。302 张 JPEG 全部解码为 1920×1080；重复输入同一保存帧，输出 SHA256 只有一种。与该 UYVY 帧按 full-range BT.601 解释的参考图，首张 PSNR 约 53.71 dB。它是静态原帧回放，不是真实摄像头 30 fps 验收。
- 真实采集组合中的卡点是 VPU 输入缓冲 `VIDIOC_DQBUF`：调用日志停在 `DIAG_INPUT_DQ_BEGIN`，线程等待点为 `vb2_core_dqbuf`，系统调用为 ioctl、请求值 `0xc0585611`。并非仅凭旧帧数推测。
- 同次诊断出现 MVX 固件 watchdog 超时；另一次在正常关闭 UYVY 试验、重开原 NV12 预览时出现 `V5/V7-JPEGENC: MMU ABORT`。后者发生于恢复阶段，不能移写为所有 UYVY 停帧的已知原因。
- 改为独立输出线程仍失败；真实取帧与编码串行、排空后再采下一帧的候选也发生输出超时。因此“只是单线程输入输出互相等待”不是已确认根因，不能将加线程写成已修复。

纯内存与真实采集的差别还包括 SDK 打开/模型描述加载、DMA/内存路径、调度和缓冲生命周期等。当前不能只凭这组差分把问题唯一归于 PL DMA、DDR 带宽、VPU 驱动或固件中的某一项；更不能断言 PHY、CPU 性能或硬件格式不支持造成此次停帧。

## 实施过程

读取当前 AGENTS、现役源代码、前一轮 UYVY 失败收据，并补充读取 `D:/xiangmuwendang/WCIS-FPAI/repos/FPAI30TAI图像FPGA/README.md`。快照仅作背景；实际板卡、程序及日志优先。所有工作在 `D:/yzd/tmp/uyvy-diagnose-20261029`；板端 `/root/wcis-face/candidates/uyvy-diagnose-20261029`。未修改生产源文件、位流、BOOT、引脚、电平或模型。

1. 核对 SDK 的 `enqueueDataPtr()`：输入缓冲复用调用阻塞式 `getAvailableBuffer()`；其内部为 `VIDIOC_DQBUF`。原调用顺序是入队后读取输出；厂商 `vpu_encoder_actor.hpp` 则有独立输出处理线程。官方 V4L2 文档也区分输入 OUTPUT 与编码结果 CAPTURE 两个队列，但这些资料不能代替故障复现。
2. 使用板上已有 strace 跟踪原试验二进制。约 10 秒正常完成并排空 282 帧；未复现。跟踪会改变时序，所以不将这次短测当成稳定证明。恢复程序最初仅因 systemctl start 成功就标记 formal_restored，后续健康检查发现固件 MMU ABORT，已由 `restore-failure.json` 和恢复记录撤销该现场成功判断。
3. 无 strace 再运行，复现停帧，最后保存发布计数 68；随后快照新鲜度拒绝并退出。
4. 学校服务器构建调用边界诊断版，只增加输入出队、提交和输出边界日志，捕获到发布计数 32 后输入出队调用未返回。保存实际线程等待及系统调用；没有通过增加超时阈值放行。
5. 按厂商 actor 思路建立独立输出排空线程，帧队列加互斥，SDK 仍只在原所有者主线程访问。仍在最后保存发布计数 20 后失去更新，未通过。
6. 尝试系统 v4l2-ctl 单独喂内存原帧。第一次控制名不被该工具识别；第二次虽退出 0，但它先设置 CAPTURE，驱动将 JPEG 输出尺寸回填成 2×2，最终文件为空，并报 capture_setup streamoff error。这是无效试验，`v4l2-default-result.json` 中按返回码填写的 passed=true 不能作为通过证据。
7. 改用小型 C++ 纯内存探针，按已验证 SDK 顺序配置 UYVY 输入和 JPEG 输出，保持质量 80、双缓冲。有限回放、输出排空、streamoff、全量 JPEG 解码检查通过，形成上述 302 帧证据。
8. 最后测试真实采集与编码串行的候选：不提前启动下一次采集，每轮编码输出全部排空。最后保存发布计数 533，但随后仍报 `Serialized VPU output deadline`。该计数不是 533 张完整解码验收；只有保存的快照可独立核验。未接受或部署此候选。

## 各试验范围

| 试验 | 证据与结果 |
|---|---|
| 原采集程序 + strace | 正常关闭，captured=encoded=282；恢复原预览后另有固件 MMU ABORT |
| 原程序，无 strace | 最后保存发布计数 68，快照新鲜度失败，exit=3 |
| 调用边界日志版 | 最后保存发布计数 32；输入 DQBUF 阻塞、MVX watchdog |
| 独立输出线程 | 最后保存发布计数 20；新鲜度失败，exit=3 |
| v4l2-ctl | 控制名/配置顺序问题，零字节输出；不计为通过 |
| 纯 PS 内存探针 | 302/302 返回、全量解码、1920×1080，正常退出 |
| 真实采集与 VPU 串行 | 最后保存发布计数 533，输出 deadline，exit=3 |

只有纯内存探针提供本轮完整压缩输出验证。各诊断运行有额外日志/轮询、窗口长度不同，不将其 CPU、帧数或耗时当成公平性能比较，也不把纯内存重放当作新采集帧。

## 构建与产物

每次构建重新检查学校服务器工具和既有任务；经原局域网入口及两级固定主机身份校验连接。所有源码/缓存/临时文件隔离在 `D:/yzd/tmp/wcis-camera-preview-uyvy-diag-*`，共享 SDK/工具只读，显式使用 MSYS2/工具链 PATH 与参数转换配置。未本地交叉编译。

- 边界诊断版：学校任务 `1396733c`，二进制 `0ceb1f38cdc3e3ccf3bac8b20e1722dc7f59e2535eb6eef4be33ee7a92207913`。
- 独立输出线程：学校任务 `3f8b84cb`，二进制 `223d334ef5f72c9ed1e58e5a36060529fb03a9ad5b5bae04e22eda8484e348bf`。
- 实际通过的纯内存探针：学校任务 `4e8e1f31`，二进制 `44cee9e88cdbafa73d36b46c7c20bb2470ee9977c565cedae10c6a99ec28657f`；本地 `memory_probe`、`memory-build-receipt.json` 保存与实际板测一致的版本。另一次同源重复构建不替代该收据。
- 串行候选：学校任务 `203a7138`，二进制 `8642d13d5dc6614f881c14b13f284f3e227981f7afefde5b5063c9dfe725d050`；最终 `build-receipt.json` 指此版本，不能用于绑定前面的其他试验。

任务 `source/`、`memory-source/`、`serial-source/` 分别保留各阶段源，服务器隔离目录保留构建输入。日志与收据：`trace-result.json`、`syscalls.log`、`restore-failure.json`、`plain-result.json`、`diag-result.json`、`diag-native.log`、`blocked-input.json`、`split-result.json`、`split-native.log`、`v4l2-*-result.json`/对应日志、`memory-result.json`、`memory-native.log`、`memory-qa.json`、`memory-output.mjpeg`（板端）、`serial-result.json`、`serial-native.log`、`run-summary.json`、`final-verification.json`。诊断内核报告只记录实际读到的内容，未对猜测 DDR 地址进行探测。

## 恢复与后续边界

不能正常关闭硬件的运行保留收据与当前启动隔离信息，使用原镜像正常重启恢复，没有删除标记后继续打开 SDK。最后启动为 `fd52abb7-20c6-4fb6-8136-7942b95e6162`，正式仍为 `camera-psopt-20261029`；健康、硬件准入、模型缓存 ready，540p 预览帧号推进，录像 off，正式应用清单散列匹配。真实摄像头识别一次成功，现场无人脸，约 435.65 ms；不算真人/攻击或多人验收。BOOT 仍为原 f6da96ab 版本。

下一步若继续定位，应先用相同纯内存输入补充 SDK 打开但无相机 DMA 的对照，或结合厂商 MVX/固件日志进一步核对地址映射、缓冲所有权和调度；不要将本轮候选直接上线。当前未证明两天内可以交付稳定的 1080p UYVY 预览。

参考：[Linux V4L2 memory-to-memory](https://docs.kernel.org/userspace-api/media/v4l/dev-mem2mem.html)、[V4L2 poll](https://docs.kernel.org/userspace-api/media/v4l/func-poll.html)，以及本地厂商 `pipeline/vpu/vpu.h` 和 `pipeline/actor/vpu_encoder_actor.hpp`。日期按客户端 2026-10-29；本文同步补充至 `D:/bigfuture/竞赛/记录/2026-10-29.md`，保留既有记录及来源文档。
