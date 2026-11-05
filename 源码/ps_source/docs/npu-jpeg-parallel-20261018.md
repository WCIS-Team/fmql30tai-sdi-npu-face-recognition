# NPU推理与PL JPEG真正重叠执行（2026-10-18）

本轮已在现役板卡上验证**真实NPU卷积与JPG1硬件同时处于执行窗口**，不再只是先后调用。
6份保留原帧、30组串行/重叠配对，共60次NPU前向与60次JPEG；30次重叠均有卷积完成时JPEG仍忙的证据。
全部NPU输出及JPEG字节与串行基线一致，6份完整原帧读回一致。

这是独立ModelBackend原型，正式HTTP入口、连续SDI采集、录像业务及语音/ASR/LLM调度未接入。
另完成FAC1/JPG1端口轮流仲裁的源码和仿真；**板端仍使用现役位流，未部署该仲裁改动**。

## 先区分两件事

`wcis_recording_customop.v`中的JPEG优先只描述FAC1人脸预处理与JPG1共用的native端口。
不能仅凭这个仲裁器就推断NPU推理一定在相同端口上等待。本次分别验证：

- NPU＋JPG1：在当前位流上，用统一SDK设备/分配器实际重叠执行。
- FAC1＋JPG1：修正本地RTL的公平性，在真实包装层压力仿真和两个真实PL核同时执行的仿真中验证。

不直接删除`npu.lock`，不让两个独立SDK分配器同时管理同一DDR，不边编码边重新打开/关闭另一份设备实例。

## 同一设备中的硬件重叠

新增`npu_photo/src/parallel_npu_jpeg_runner.cpp`，构建为`wcis_npu_jpeg_parallel`。
进程启动只加载CPU模型；每个命令只打开一次设备，按以下顺序管理资源：

1. 校验本boot、现有保留帧描述符、128 MiB窗口、原始1920×1080和紧密pitch。
2. 首先通过既有`frame_lease::Reservation`保留源帧及人脸scratch，再用同一分配器申请8 MiB JPEG输出和两端guard。
3. 创建/应用一个NPU会话，设置与现役程序相同的后端选项，准备软件输入；此时两个核均未开始执行。
4. 重叠模式在第一个真实ZG330 `Conv2dNode`前回调中提交JPG1，随后继续该NPU前向。
   串行模式则在NPU完成后才提交JPEG；两种模式使用相同的卷积观察逻辑。
5. 后回调显式等待该卷积输出Tensor ready，再读取JPG1状态。只有前后两次busy均为1，且后端/算子/输出契约正确，
   才记为`overlap_proven=true`。不以“两个调用时间接近”或“进入回调”作为并行证据。
6. 等待整张网络和JPEG各自完成，检查帧号、长度、guard与输出，再销毁会话/临时Tensor/内存，最后关闭共享设备。

使用实查SDK 3.39头文件中的Session回调、Backend绑定与Tensor::waitForReady接口。
没有另外启动SDK线程，不依赖尚未证实的多线程SDK安全性；JPEG自主运行时，主线程继续提交NPU算子。
出错/超时保留当前boot的硬件复核标记，不自动重试或释放后让其他请求继续使用。真正卡死/断电恢复未验收。

首次BGRX单人用例的重叠观测：

| 模型 | 硬件Conv2d op_id | 回调前/输出ready后JPEG状态 | 观察时间（相对前向开始） |
|---|---:|---|---|
| YuNet | 406 | 1 / 1，busy均置位 | 16.985 → 18.311 ms |
| MobileFaceNet | 783 | 1 / 1，busy均置位 | 0.838 → 1.008 ms |

该观测来自实际ZG330绑定和卷积输出ready，是运行期重叠证据；不是ILA逐周期轨迹，也不能推断整张网络始终与JPEG重叠。

## 构建和板测

学校独立任务：`D:/yzd/tmp/wcis-face-parallel-20261018`。
本机证据：`D:/yzd/tmp/face-jpeg-parallel-20261018`。
已重新检查学校连接、进程、GNU AArch64 10.3.1、CMake及SDK，程序在学校服务器交叉编译通过。
源码/构建/缓存/临时目录独立，显式配置TMP/TEMP/TMPDIR、XDG_CACHE_HOME、工具链PATH、CROSSWIN_TC和MSYS2_ARG_CONV_EXCL。
没有修改共享SDK/环境或停止其他人的任务，也没有重新导出/编译模型。

板测启动ID为`43d0a6fd-ef63-4b81-8972-173d658eff1e`，与现役已验证启动记录一致。
先做1份输入、2个模型的4命令试验，再做6份输入的完整配对，最后做命令在途停止测试。
输入沿用上一轮已校验的单人/四人拼图/无脸测试图，两种格式BGRX8、RGB565LE；部分原图放大后打包，均非SDI实采。

完整配对由`npu_photo/check_npu_jpeg_parallel.py`执行：

- 6份源内容，各上传一次；每个模型做3对串行/重叠，交替变更模式先后顺序。
- YuNet共18对；有脸的4份源取检测分数最高的一张脸准备特征输入，MobileFaceNet共12对。
  四人图参与检测，但本轮没有为每张图的4张脸都测完整身份流程。
- 比较所有软件FP32输出的原始字节SHA，禁止NaN/Inf、维度错误与缺失输出。
- 所有JPEG完整解码为1920×1080，串行/重叠、不同模型及重复次数的JPEG字节一致。
  再按原帧SHA对照上一轮已独立做像素验证的JPEG，60份全部字节相同。
- 核对JPEG完整输入块数、输出长度/标记、原帧ID/token，最终全量源读回。
- 当前请求仍整段持有现役`npu.lock`；只允许一个组合命令在途，防止其他SDK所有者插入。

结果：60次网络前向、60次JPEG均完成，30次重叠均有真实卷积证据，输出与源帧保持一致；两个worker正常退出码0。
另向测试父进程在组合命令在途时发送SIGTERM，当前组合命令完整返回后验证源帧并退出，两个worker均为0。
信号不发送给SDK worker；没有强杀在途DMA。定时信号不代表已定位到某个具体硬件beat。

## 成对计时及代价

计时窗口从已建立会话、准备好输入后开始，覆盖前向/等待、JPEG完成及JPEG压缩字节读回和普通文件写出。
**不含设备打开、会话建立、原图上传、PS检测框解码、其他人脸特征、NPU输出导出和fsync**。
因此不能称门锁端到端耗时，也不能与上一轮包含更多阶段的JPEG worker时间直接比较。

| 模型＋1张JPEG | 配对数 | 串行中位 | 重叠中位 | 每对缩短比例的中位数 |
|---|---:|---:|---:|---:|
| YuNet＋JPEG | 18 | 72.31 ms | 65.15 ms | 10.02% |
| MobileFaceNet＋JPEG | 12 | 63.34 ms | 55.17 ms | 12.95% |

最近秩口径p95：YuNet为75.12→66.70 ms，MobileFaceNet为63.48→56.50 ms；样本小，不代表长期尾延迟。

并行存在资源争用，不能假设组合耗时必然等于两者最大值：按当前100 MHz周期换算，JPEG自身周期中位数从
约41.67 ms增加到YuNet重叠时48.14 ms、特征模型重叠时53.35 ms。
本次观察到组合窗口变短、JPEG自身变慢；DDR/互连争用是可能解释，未用硬件带宽计数将原因完全定位。
这不是20 FPS持续录像或四人每秒2轮识别的证明，完整流水线收益需要另测。

## FAC1/JPG1端口公平性

修改`rtl/wcis_recording_customop.v`，增加`FAIR_ARBITRATION=1`，读写分别轮流选择。
只有在实际握手后改变下一次优先方；背压时冻结获胜方和请求内容，读返回仍绑定原请求者，仅一笔读在途。
`FAIR_ARBITRATION=0`保留旧JPEG优先行为，CSR地址/协议不变。

`sim/tb_recording_arbiter.sv`用测试流量发生器饱和真实包装层，并注入长短停顿、返回背压及客户端单独工作阶段：

- 未修改快照：双方持续写请求的首阶段，人脸获得0次写握手，复现固定优先的饥饿风险。
- 轮流仲裁：同阶段人脸获得897次写握手；整个测试读握手416/414、写握手3532/3551。
- 兼容参数0与旧快照计数一致；背压请求不改变、没有双重读在途或错误返回归属。

公平性是“持续争用时按已接受事务交替”，不能保证外部DDR无限停顿下的固定时钟延迟。
流量发生器不冒充真实JPEG/人脸算法，另用`sim/tb_recording_parallel.sv`运行**两个真实PL核**：

- 64×16、两种格式、各2帧，实际FAC1恒等采样与JPEG同时工作。
- 逐像素验证FAC1，独立JPEG软件参考DCT系数最大差不超过1，输出guard不变。
- 每帧两核busy重叠6926～6972个仿真HP时钟周期，完整源读与两个输出写回均通过。
- 同时保留原JPEG非法描述符、容量溢出、运行中错误配置等回归。

新仲裁RTL尚未综合、整板布局布线或部署；**此次板端NPU/JPEG并行使用原有位流**，与源码仿真成果分开。
未将之前未部署的行缓存或PAD裁图改动宣称已部署。

## 入口、记录及未完成范围

候选：`/root/wcis-face/candidates/parallel-20261018-fcaeef77d5ac`。
独立程序：`wcis_npu_jpeg_parallel --serve <现役models.json>`，请求字段包含`mode`（serial/overlap）、role、
retained_frame、input_f32、output_directory、fault_marker。调用方持有原硬件锁并保留原帧直到两个核完成。
可复跑检查入口为候选下`src/check_npu_jpeg_parallel.py`，参数见`--help`；输出只能放在eMMC recording-tests新目录。
构建脚本：`scripts/build_face_parallel_school.ps1`。

本机证据：

- `smoke-verification.json`、`full-verification.json`、`stop-verification.json`及各`*-run.json`/日志。
- `measurement-summary.json`：按角色配对计时及与上一轮独立JPEG基线的匹配结果。
- `arbiter-verification/verification.json`：旧快照、轮流、兼容参数三组；`before/wcis_recording_customop.v`保存原源码。
- `real-core-regression/summary.json`及两格式仿真日志/JPEG；`sdk-reference/`为只读SDK接口取证。
- `board-before.json`、`board-final.json`、`final-audit.json`、`source-manifest.json`、`arbiter-change.patch`。

本轮没有重启、改时钟、写启动分区、更换正式服务或人员库；前后boot、FDT、服务文件、人员库及应用SHA核对保留。
现役服务保持ready，测试后硬件锁释放，无当前boot隔离标记。测试期间其他识别请求仍可能因全局锁而busy。

后续才是把组合后端接入完整人脸流程，复用设备/缓冲，接真实SDI生产者，验长期延迟与保存吞吐；
新仲裁位流的实现/部署也需独立验收。ASR/LLM与视觉共享NPU的调度未在本轮测试。
背景信息站本轮仍连接被拒绝，未读取最新内容。记录同日归档至`D:/bigfuture/竞赛/记录/2026-10-18.md`。
