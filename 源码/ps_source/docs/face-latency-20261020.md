# 摄像头识别交接延迟优化（2026-10-20）

## 结果

已部署到原页面 `http://192.168.1.113:8091/`。最终程序10次紧邻的真实摄像头请求通过：全部为桌面无人脸，排除首个请求后的中位HTTP耗时 **1.062秒**；上一阶段同样无间隔请求的5次暖运行中位数 **2.485秒**，本次下降约 **57.3%**。这是短时现场前后对比，不是同光照/系统负载严格配对的吞吐基准，也不是有人识别或活体防伪速度。

采集原生PID、会话在10次请求中保持一致，帧号严格递增；返回JPEG SHA与输入和帧元数据逐项一致。单人、无脸、双人照片分别返回1/0/2脸，坏图HTTP400；每种照片请求前后摄像头均恢复同一PID/会话的新帧。浏览器自动检测持续更新、暂停及单次检测通过。

当前仍串行执行取帧、排空采集、PL/NPU推理、恢复采集，推理期间预览仍暂停，**没有实现画面不停顿的连续视频检测**。当前桌面无人脸总请求约1秒；页面的约0.45秒是预处理和模型内部计时，不能替代总请求时间。现场真人姓名匹配和防照片攻击仍未验收，PAD保持`not_evaluated`。

## 原因与依据

任务开始重读根目录及`fpga_project/AGENTS.md`、`D:/xiangmuwendang/WCIS-FPAI/wiki/PL/plvid.md`与本地摄像头接入源码。背景材料intro的SFace与后面列出的MobileFaceNet不一致；本轮保持当前已部署YuNet + MobileFaceNet，不改模型。

通过原有互斥上下文实测3次无模型交接：停止服务约103–132ms，启动服务约741–830ms，启动返回后等新帧约897–1018ms。单次运行原`boot_prepare.py`耗时约622ms，其中读取BOOT约371ms。原来每次推理都结束整个采集程序，随后重跑启动文件核验、网络准备、Python与原生程序加载、SDK和VPU初始化，是主要额外开销。证据为`handoff-profile.json`与`prepare-profile.txt`。

## 实现

1. `ps_app/src/wcis_sdi_vpu_live.cpp`增加显式可选`warm`模式。程序常驻，正常推理交接时排空已发出的DMA及VPU输出，禁用采集，销毁相机/缓冲/寄存器句柄，调用`Device::Close`，再释放原`npu.lock`，最后原子发布带本次随机token、PID、boot及`device_closed=true`的暂停证明。没有把SDK并发打开作为提速手段。
2. 由有界文件协议接收暂停/恢复命令，token、PID及boot必须匹配；文件最大4096字节，恢复命令只匹配当前暂停token。暂停期间不留上一帧`latest.frame`冒充新画面；保持帧号递增、只发布最新JPEG。恢复前再次拒绝当前boot的硬件隔离标记，并非阻塞等待硬件锁后盲目重试。
3. 保留厂商VPU双输入缓冲要求：暂停到达编码器启动前时，先完成最小缓冲准备，再排空并交接。帧发布以编码器真实stream-on状态为条件，恢复后不会因全局帧计数已超过3而对尚未启动的编码器提前等待。
4. `scripts/run_sdi_vpu_capture.py`增加`--warm-handoff`，只用于无限循环的camera模式。仍继承原硬件锁和相机锁；硬件锁仅在已关闭SDK后主动释放，相机所有权持续保留。服务启动时的完整BOOT、应用文件和隔离核验保留，不再为每次帧推理重启服务。
5. `npu_photo/camera_interlock.py`仅对明确配置`handoff=warm_process`启用该协议；检查配对暂停证明，再检查硬件锁已可取得，才允许原推理链路。错误证明、超时、锁仍占用或SDK失败时隔离且不恢复。原停止/启动协议作为未配置warm时的路径保留。
6. `serve_photos.py`输出分阶段交接计时，health标记`camera_input_mode=warm_snapshot_handoff`。页面取消固定650ms间隔，仍等单个请求完成才取下一帧，不建立摄像头请求队列；文案明确推理期间画面暂停。

## 构建与部署

在学校服务器重新核验MSYS2、Arm交叉工具、SDK/CMake路径及编译进程。最后独立任务为 `D:/yzd/tmp/wcis-camera-preview-warm-6717a4c8`，所有源码、构建、缓存和临时文件放在该任务下，共享工具只读；无板上编译、模型转换或RTL/BOOT构建。

新增JSON协议复用`npu_photo/vendor`的现有nlohmann头文件，`ps_app/CMakeLists.txt`为该目标加include，构建归档包含相应头文件。最终C++源码SHA256=`1b8e75486c54e901e53241b62544ba05a724e700782f15b30cb32fc3ba6e75c6`；原生程序SHA256=`d255292bd4f7ff8bcec997dcf497f5a808d976f1ea1ea8e751b1e61974e13e5e`。首个可运行版本的测试单独保存在`verification-v1.json`，最终指标来自再次更新后的`verification.json`，不能混用版本。

部署先等待在途照片请求完成并停止照片服务，确认新鲜采集帧后正常停止相机，要求退出0且无隔离，再替换程序、入口脚本、后端和配置。仅给原相机服务添加warm参数，没有增加网络监听。完整部署前副本及精确路径映射在板上 `/root/wcis-face/candidates/face-latency-20261020/before.json`，备份名`backup-*`，包含原配置、camera-control、camera服务、采集程序/receipt/launcher、后端和页面。

没有重启或替换BOOT，最终启动仍为`6d292f53-4a5d-4600-bbcd-28ea2654a6c0`。最终原生哈希与构建回执一致，所有配置清单文件及站点脚本一致；三个服务active/enabled、health ready、硬件准入可用，正式库6文件SHA与部署前相同。tmpfs为1个活动相机会话、0个遗留摄像头请求目录。

回退需要先完成正常的请求/采集排空，停止照片与相机服务，按`before.json`路径映射恢复所有`backup-*`副本，再daemon-reload并启动相机、确认新帧后启动照片服务。若已有当前boot隔离标记，先核查故障，不自动重开SDK。不要调用更早会重启整板的恢复入口来代替本轮精确软件回退。

## 验证边界与证据

- 14项无硬件测试通过，包括首帧等待、坏帧、停止证明、错误token/未关闭设备证明拒绝、warm期间SDK故障不恢复、暂停证明后硬件锁仍占用时隔离。脚本语法检查通过；原框坐标和逐脸关联实现未变。
- 最终10次真实camera请求无错误，同一PID/会话、递增帧号及SHA绑定通过。单/双/无脸和坏图共4种交替调用通过，每种前后摄像头仍可正常识别新帧。
- 浏览器首次打开时与照片验收同时访问，收到409并暂停，未启动第二条SDK调用；验收完成后手动恢复自动检测通过。这是忙时拒绝行为，不能视为可并行处理多个客户端。
- 目前没有长期运行、反复完整开机、真人运动画面或安全攻击集验收。有人脸还需要对齐、特征模型和匹配，耗时会增加，不能承诺所有场景均1秒。

关键证据在 `D:/yzd/tmp/face-latency-20261020`：`build-receipt.json`、`school-preflight.txt`、`build.log`、`handoff-profile.json`、`prepare-profile.txt`、`verification.json`、`photo-verification.json`、`final-state.json`、`live-latency.png`、`before.json`和部署/测试脚本。

记录依据为上述源码、配置、回执与板测文件；同日合并归档到 `D:/bigfuture/竞赛/记录/2026-10-20.md`。
