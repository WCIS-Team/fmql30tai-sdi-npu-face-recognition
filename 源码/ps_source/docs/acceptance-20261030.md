# 2026-10-30 阶段验收与功能冻结

日期按聊天客户端 Asia/Shanghai。用户要求：停止新增功能，转向现有实现的优化和文档。结论为**现役 960×540 原型有条件通过阶段验收**；不等于完整产品验收、现场防伪有效性或整板时序签核。后续工作范围见 [维护与优化清单](maintenance-plan.md)。

## 验收对象与依据

- 当前本地工程 `D:/renlianshibie/fpga_project`；本目录没有 Git 元数据，因此不虚构提交号。源码校验清单、测试输出和本次只读板端快照保存在 `D:/yzd/tmp/acceptance-20261030`。
- 正式应用 `/root/wcis-face/apps/camera-h264-20261030-r1`；录像应用路径按此前部署记录为 `/root/wcis-face/candidates/recording-h264-20261030-r1`。本次复查正式应用的 39 个受管文件，均与板端清单相符。
- 其中 31 个可直接映射到本地的源文件，30 个逐字节相符；根目录 `camera_panel.html` 是旧片段，与本地双视图片段不同。实际 HTTP 首页与正式 `site/index.html` 相符，包含双视图、两种帧率及 PAD 元素，不能把旧片段差异说成当前网页故障。`camH264` 由匹配的 `camera_panel.js` 动态创建，不要求静态 HTML 存在该元素。完整映射仍需在发布整理时补齐。
- 原生程序 SHA256 `b56cf75f2276c2661fe0096c34bd0552295b10b4449ab9d51fb739dc4264acc0` 与学校构建收据及正式清单相符；本地 `ps_app/src/wcis_camera_owner.cpp` SHA256 `d62fbbcd60461302ee34e0d12a729888939acd3486f10132a770ee1f1cbfa70e` 与该次源文件收据相符。本轮没有编译或替换原生程序。
- 同时读取 `D:/xiangmuwendang/WCIS-FPAI/repos/FPAI30TAI图像FPGA/README.md`。该补充快照仍记录 10-27 的 JPEG 录像，不能当作现役状态；当前 H.264 以源码、10-30 部署收据和本次板端核查为准。未访问旧站点或前台浏览器。

## 本轮实际验证

### 软件回归与修复

使用已有隔离依赖运行现有测试，首次发现两个失败，保留 `local-checks.json` 与对应 `*-initial.log`，没有覆盖失败证据：

1. `lan_stream/raw_protocol.py` 的接收帧率使用时间窗跨度作分母，两次到达时间相等时除零，真实 HTTP 测试中 `/api/frame` 因异常断开。`status()` 和 `lan_stream/server.py` 的旧 JPEG 接收端存在相同写法。三处均增加正时间跨度判断；没有有效跨度时显示 0，仍保留最新帧、序号和时效检查。新增 `tests/test_receive_fps.py` 的两项确定性回归覆盖相同时间、后续正常计数、像素保持和过期拒绝。修复后的原始帧 HTTP 测试 13 条检查通过。
2. `tests/test_owner_pad.py` 的退出收据测试导入依赖 `fcntl` 的 Linux owner，Windows 无法运行。只给这一个测试增加明确的平台跳过，不伪造 `fcntl`。在板端独立 `/tmp/wcis-acceptance-20261030-6355e2bc` 中运行同一测试文件，21 项全部通过；测试使用模拟 owner、临时管道和文件，不打开 SDK/NPU/VPU。

最终合并首次无失败的组和修改后的定向复测：

| 范围 | 本次结果 | 证明边界 |
|---|---|---|
| Windows Python 单元测试 | 154 项中 151 项通过，3 项明确跳过 | 使用真实 Python 代码与模拟硬件收据，不证明模型推理 |
| Windows 页面 JS | 7 组全部通过 | 节奏、并发、帧归属、防伪展示、双视图等模拟 DOM 回归，不是浏览器实播 |
| Windows HTTP/协议 | 诊断状态、原始帧两组通过；原始帧组含 13 条检查 | 本机回环；未传入可选 C++ sender/wait-test，不声称跨编译或板端传输通过 |
| 板端 Linux 单元测试 | owner/PAD 21 项、H.264 9 项全部通过 | 包含 Windows 跳过的退出收据、文件轮转、FIFO 握手；仍是软件契约测试 |

Linux 首次 H.264 测试副本漏带 `h264_media.py`，导入失败；补齐后仅复跑该组并通过。保留 `linux-checks-initial.json` 和初始日志。此失败属于验收脚本依赖遗漏，不是板端编码故障。

本轮生产代码修改仅涉及旧接收路径的帧率除零保护，**只修改本地源码，未部署**。正式 540p H.264 使用 `vpu_live_server.py`，本轮没有对其做性能修改，不宣称本次修复提高了正式预览帧率。

### 板端只读健康检查

2026-10-30 18:50 左右（北京时间），`board-readonly.json`：

- 启动 ID `fd5d27fd-00f6-4c41-8991-a796091a53f9`；读取时 uptime 约 12780 秒。它只说明当前启动时长，不等于该时段全程压力验收。
- 三个正式服务 active；健康接口、模型缓存及摄像头 ready；现役传输为 `PS_VPU_H264`、960×540，源帧号推进。
- 约 10.015 秒计数窗口为 26.96 fps。HLS 按片段发布且语音后台服务同时存在，这不是与早前 29.94 fps 同负载、同窗口的性能对照，不能据此直接归因退化或承诺恒定 30 fps。
- 录像输入 ready，格式 H.264/MP4，模式 off、state idle、error 为空；自动清理关闭。本轮未开启录像、删除录像或修改人员库。
- 当前启动内核所筛选的 MVX/MMU/watchdog 行仅有设备识别，未见对应故障行；这不排除所有类型错误。
- `klar_asr.py` PID 3622 仍在运行。本轮未停止它、重启板卡或开始 1080p 压测。
- 正式首页 HTTP 内容与受管 `site/index.html` 一致。本轮没有新开浏览器做实播、没有发起新的推理或录像请求；上述功能性证据引用此前收据，不能冒充本轮重做。

## 能力验收矩阵

| 能力 | 结论 | 证据及仍缺少的内容 |
|---|---|---|
| 540p H.264 预览、MP4 录像、旧 JPEG 兼容 | 阶段通过 | [H.264 集成记录](h264-ffmpeg-20261030.md)及 `formal-final.json`：重启、浏览器实播、240 帧 MP4 全解码、Range/旧帧回放；本轮复查服务及输入健康。正常光照画质、端到端延迟和长期录制未通过专项验收 |
| YuNet/MobileFaceNet 身份链路、单 owner 与会话缓存 | 有界回归通过 | [缓存优化](face-pad-speed-20261027.md)、[H.264 集成](h264-ffmpeg-20261030.md)保留的固定帧比较；本轮软件合同通过。不能将旧帧回放、无人脸 HTTP 成功当新多人现场准确率 |
| 同帧、最多四脸双 PAD | 模型证据链通过；安全能力不验收 | [多人防伪](face-pad-multi-20261027.md)，当前健康明确 `pad_security_calibrated=false`；现场真人/照片/视频/打印及误放误拒、阈值校准仍缺，不作为开锁许可 |
| 录像管理、存储边界 | 软件及历史有界板测通过 | [录像管理](recording-management-20261027.md)、[存储显示](recording-storage-20261027.md)与本轮 25 项录像测试；长期磁盘满、掉电恢复和持续并发另验 |
| 完整 1080p 采集＋VPU＋NPU | 不通过，冻结为遗留项 | [分档试验](h264-1080-load-sweep-20261030.md)、原始 `summary.json`：5/10 fps 各 60 请求通过；15 fps 24/60 后采集 Error；30 fps 未测。后台负载混杂未排除，不是已证明的性能上限 |
| PL 直接网络预览、新候选位流、PL PAD 裁图 | 不纳入现役交付 | 候选/仿真不能替代现役部署；见 [PL 续作](pl-preview-continuation-20261028.md)。停止继续扩展此路线 |
| 整板时序、PL DDR 全容量 | 未签核 | [时钟依据](npu-clock-vendor-review-20261022.md)、[硬件核查](board-hardware-review-20261014.md)：NPU 最小周期告警和完整 PL DDR 容量扫描仍未闭环；本轮不改 RTL/BOOT/地址映射 |

## 阶段决定与未关闭风险

允许以现役 540p 配置进入维护阶段；不再新增接口、网页功能、模型、调度层或硬件路线。1080p 待测保留证据，取消“等待语音任务后自动继续”的工作安排，待以后明确重启该遗留问题时再按隔离条件复验。

优先处理发布可复现、文档一致性与现有异常闭环，再做性能对照。第一次 H.264 试验曾有 YuNet 原始张量散列不一致但未留存原张量，后续 120 次通过不能抹去此风险。任何优化均保留原始失败、输出比较、现场负载和回退证据，不只比较平均帧率。

本次无需模型/原生编译；以后如需，仍按学校服务器优先、每次重新核查、任务独立目录与共享工具只读规则。没有把本机 Python 测试当成交叉编译或部署。

## 复核入口与记录归档

- 当前结论入口：[README](../README.md)、[维护与优化清单](maintenance-plan.md)。历史 `verification.md` 已补当前入口，历史正文保留。
- 本次证据：`D:/yzd/tmp/acceptance-20261030/local-checks.json`、`local-recheck.json`、`acceptance-summary.json`、`linux-checks.json`、`board-readonly.json`、`source-deployment-comparison.json`、`served-page.json`、`source-manifest.json` 及逐组日志。
- 历史原始依据：`D:/yzd/tmp/h264-ffmpeg-20261030/formal-final.json`、`integration-build-receipt.json`、`native-integration-sha.json`；`D:/yzd/tmp/h264-1080-load-sweep-20261030/summary.json` 及各档 `result.json`。
- 同步追加到 `D:/bigfuture/竞赛/记录/2026-10-30.md` 的本轮专属区块，保留同日既有 H.264 与负载测试记录。只归档副本，不移动、删除或改写原始证据。
