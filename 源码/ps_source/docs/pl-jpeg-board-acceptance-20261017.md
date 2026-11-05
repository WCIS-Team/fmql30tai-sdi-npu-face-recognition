# 原生1080p PL JPEG板测核验

核验日期：2026-10-17，Asia/Shanghai。构建、视频采样和原始证据文件记载为2026-10-16，
本记录将采样日期与续接核验日期分开；过程见[整板实现记录](pl-jpeg-board-20261016.md)。

## 已完成的结果

修正后的固件已上板。本机解码原生1920×1080视频，经SSH注入板端，由PL完成Q75 JPEG压缩，
PS读回压缩字节并写入eMMC。没有用CPU进行JPEG编码。
复用固定版本[mjpegZero](https://github.com/lcapossio/mjpegZero)压缩核，板端使用官方CustomOp DDR接口。

| 测量范围 | RGB565LE输入 | BGRX8输入 |
|---|---:|---:|
| 板内DDR原帧连续重新编码，300次 | 23.895 FPS | 23.873 FPS |
| 重新编码、读回、写eMMC及末尾fsync，300次 | 17.456 FPS | 19.354 FPS |
| 本机解码、SSH传输、DDR校验、压缩、保存及末尾fsync，165张新帧 | 1.736 FPS | 0.895 FPS |
| 新帧硬件job耗时中位数 | 41.638 ms | 41.697 ms |
| 165张新帧JPEG总大小 | 28,528,985 B | 26,600,774 B |
| 单帧JPEG大小范围 | 138,413～184,284 B | 131,453～171,550 B |

两种格式各处理165张不同视频帧，再各做两组300次驻留DDR原帧重新编码。
合计330张新帧、1200次板内重新编码；保存的930个JPEG全部完整解码为1920×1080。
每次驻留测试均核对完整源读取块数、输出写块数、帧号及非零周期，不是重复写出已有JPEG文件。

每张新帧上传后的DDR全量校验通过；首帧完整DCT系数与固定软件参考的最大差异均为1。
BGRX首帧JPEG与原生1080p RTL仿真输出逐字节一致，SHA256为
`16f2219579d32ee1d6a444233ff665a9af2549b8c6adef23dbe2ec4f8d7e81c7`。
另已查看解码后的首、末帧，画面完整且随视频变化。

## 速度限制与判断

当前100 MHz、1080p、Q75配置的板内编码实测约23.9 FPS。
没有扫描更高时钟或其他质量配置，因此这不是芯片可达到的最高帧率结论。

RGB565落盘批次共17.186秒，最后fsync等待4.409秒；BGRX批次共15.500秒，最后等待2.735秒。
仅为定位耗时，扣去最后这段等待，两者循环分别约23.48和23.50 FPS；
**扣除fsync的数值不能作为真实落盘帧率**。实测整批落盘仍为上表17.456、19.354 FPS。
两种格式各仅一组批次，文件大小、后台写回状态及测试顺序也会影响fsync，不能据此承诺BGRX总是更快。

eMMC另有两次32 MiB写入短测，包含fsync，分别为10.775、10.756 MiB/s。
当前证据支持优先尝试有界压缩缓冲、编码与写盘重叠、分段落盘，减少末尾集中等待；
该优化尚未实现，也尚未证明长时间20 FPS录像。

新启动的eth0实读为100 Mbps、全双工。板端等待接收新原帧的中位时间分别约466.5、976.4 ms，
远大于41.6～41.7 ms编码时间；该阶段包含等待电脑准备及SSH发送。
未计协议开销的原帧线速上限分别约3.01、1.51 FPS，实际全链路速度见表。
因此电脑原始帧注入速率不能作为未来SDI采集速率。

## 板端状态与边界

- SDK有界内存四组写读及重复读回均零错误；没有扫描完整2 GB PL DDR。
- 新启动ID为`43d0a6fd-ef63-4b81-8972-173d658eff1e`，已通过小用例验收。
- 同一启动中，人脸检测12个输出tensor SHA、识别特征SHA及检测框与部署前一致。
- 最后检查：照片服务ready、人员库6个文件SHA全部保持一致、服务文件未改变。
- JPEG测试进程已退出、硬件锁可获取、tmpfs无测试残留、当前启动无隔离标记，回退计时器disabled。
- eMMC剩余30,632,620,032 B；压缩测试文件保留在独立recording-tests目录。
- 安装工具的3个受保护器件/时序文件最终SHA与构建前一致。

这是有界压缩与保存测试。硬件由测试独占，照片服务在会话结束后恢复；
真实SDI持续采集、NPU同时识别最多4人、每秒2次身份更新、长时间录像及录像配额尚未验收。
保留原案例两项NPU脉宽告警，不能把本次原型检查视为生产时序签收。

## 本地文件与复测

- 输入视频：`D:/yzd/tmp/pl-jpeg-board-20261016/videos/1920x1080.avi`，原生1080p、25 FPS、165帧。
- 可复用脚本：`D:/renlianshibie/fpga_project/scripts/stream_video_to_board.py`。
- RGB565压缩视频：`D:/yzd/tmp/pl-jpeg-board-20261016/video-rgb565/source-only.mjpeg`。
- BGRX压缩视频：`D:/yzd/tmp/pl-jpeg-board-20261016/video-bgrx8/source-only.mjpeg`。
- 上述source-only文件只包含165张新帧，未混入300张驻留回放帧。

PowerShell复测示例，输出目录须为新目录：

```powershell
& 'D:/yzd/tmp/face-video-stream-20261016/venv/Scripts/python.exe' `
  'D:/renlianshibie/fpga_project/scripts/stream_video_to_board.py' `
  --backend jpeg --video 'D:/yzd/tmp/pl-jpeg-board-20261016/videos/1920x1080.avi' `
  --mode all --max-frames 165 --pixel-format RGB565LE --jpeg-replay 300 `
  --out 'D:/yzd/tmp/pl-jpeg-retest-20261017'
```

测试期间会暂停照片服务，结束自动恢复。`all`模式逐帧不限速，没有强行限制为20 FPS。
该命令仍由PS接收并上传原帧，不能称为SDI电气输入或PL直接管理eMMC。

## 关键本地证据

统一目录：`D:/yzd/tmp/pl-jpeg-board-20261016`。

- `measurement-summary.json`：格式对比、输入/输出字节和逐字节参考结果。
- `video-rgb565/performance.json`、`video-bgrx8/performance.json`：完整解码、原生请求计数、分段耗时。
- 两目录的`summary.json`、`frames.jsonl`、`output.mjpeg`、`decoded-0.png`、`decoded-164.png`。
- `memory-probe-guided.json`、`face-after-summary.json`、`accepted.json`、`final-state.json`。
- `final-network-state.json`、`emmc-write-baseline.json`、`installed-libraries-final.json`。
- `timing-gate.json`、`mailbox-audit.txt`、`boot-candidate/manifest.json`：实现/打包证据，与板测分开解释。

## 录像空间与压缩速度核算（2026-10-17）

按两种输入格式的165张新视频帧统计，1080p、Q75平均JPEG大小分别为
172.90 kB/帧（RGB565LE）与161.22 kB/帧（BGRX8）。
本节GB、MB、kB均按十进制字节计算。

本次通过SSH只读核对eMMC挂载为`/dev/mmcblk1p1 /mnt/wcis-emmc`，
文件系统总计31.17 GB，当前可用30.63 GB。
以下以样本平均JPEG大小计算，帧率为规划值：

| 录像帧率 | 每秒视频数据 | 每小时视频空间 | 用完当前30.63 GB的理论时长 |
|---|---:|---:|---:|
| 20 FPS | 3.22～3.46 MB/s | 11.61～12.45 GB | 2.46～2.64 小时 |
| 24 FPS | 3.87～4.15 MB/s | 13.93～14.94 GB | 2.05～2.20 小时 |

计算式：`每小时字节 = 平均JPEG字节 × 帧率 × 3600`；
`可录小时 = 可用于录像的字节 / 每小时字节`。
如果只划24 GB给录像，20 FPS可录约
1.93～2.07小时。
用完全部可用空间的时长只是理论上限，尚未扣新增人员资料、日志、音频和容器索引。

压缩速度维持本轮实测：编码约41.6～41.7 ms/帧，板内连续编码23.87～23.89 FPS；
包含读回、写eMMC及最后fsync的300帧批次为17.46～19.35 FPS。
因此编码核短测超过20 FPS，完整落盘流程尚未证明稳定20 FPS；
后续重点是编码与写盘重叠、降低集中落盘等待。
按本次要求，摄像头模拟输入保持现状，不开展其解码/SSH优化。

空间估算只适用于这段视频的画面复杂度及当前Q75设置。JPEG没有固定码率，
真实摄像头的细节、运动与噪声会改变每帧大小；24 FPS一行不是持续录像已验收的声明。

证据：`D:/yzd/tmp/jpeg-capacity-20261017/capacity-estimate.json`、`emmc-space.json`，
以及原测试目录的`measurement-summary.json`及两种格式`performance.json`。
本次项目背景站后台访问失败（URLError），未读取最新站点内容；
容量与速度结论直接依据本地板测数据及本次板端空闲空间读取。

## 持续录像的编码选型复核（2026-10-17，尚未切换）

当前MJPEG逐帧独立编码，1080p Q75样本约12 GB/小时。对于较长时间录像，
仅优化写盘等待不能降低所需存储容量，应优先评估利用帧间冗余的视频编码。
[Axis官方编码说明](https://help.axis.com/en-us/axis-m1065-lw)将MJPEG描述为独立JPEG图像序列，
并说明H.264能够降低存储需求；不能把其他设备的压缩比当成本板实测。

本次核对的可复用依据：

- 官方SDK本地副本`fpga_project/ps_app/vendor/include/pipeline/actor/vpu_encoder_actor.hpp`
  已有VPU编码入口，配置包含h264/h265及bitrate；源码存在不等于当前板端有效。
- 当前板只读核对：`amvx`已加载，`/dev/video0`存在，设备名`mvx`，
  boot id仍为`43d0a6fd-ef63-4b81-8972-173d658eff1e`。本轮没有启动VPU编码。
- 历史资料`fpga_project/outputs/board-reference-20261014-current/md/技术文档/板卡镜像实测取证.md`
  §15.8记录H.264硬编码成功；§15.9记录旧驱动缺少bitrate_mode、码率设置不能打开有效率控。
  §19中的低码率只来自VTC合成图，不能用于真实摄像头存储规划。

按码率计算空间的规划示例如下，**不是本板已经实现的码率/画质**：

| 假设实际平均码率 | 视频空间/小时 | 使用当前约30.63 GB的理论时长 |
|---|---:|---:|
| 2 Mbps | 0.90 GB | 34.0小时 |
| 4 Mbps | 1.80 GB | 17.0小时 |
| 8 Mbps | 3.60 GB | 8.5小时 |

上述时间不含额外空间占用；所需码率、画质及是否能控制码率必须用真实内容验证。
容量问题的方案建议调整为：保留PL采集/人脸预处理与NPU路线，优先复用板载VPU做H.264录像，
PS负责缓冲交接、调度与eMMC保存；接入前核对VPU输入像素格式、内存域及缓冲所有权。
如果仍要求所有编码计算都在PL完成，则需另外评估帧间编码IP及资源，不能把现有JPEG核等同于H.264。

下一阶段应先验证当前启动下的VPU编码、有效码率/画质和输入缓冲兼容性，
再决定长期录像实现，不继续优化电脑模拟输入。
本轮只是选型复核，现有位流、服务及人员库保持原状态。

证据：`D:/yzd/tmp/recording-codec-review-20261017/vpu-inventory.json`、
`bitrate-space-estimate.json`及上列本地SDK/历史取证文档。

## PL到PS的原帧传输压力复核（2026-10-17）

VPU方案仍需将未压缩帧送入PS可供VPU访问的缓冲，不能只计算编码后的存储码率。
因此上节“优先VPU”修正为候选方案，须先通过原帧传输、复制成本、并发及率控验证。
若设计约束是“PS只接收压缩后的录像数据”，PS侧VPU方案不满足这个约束。

以1920×1080、20 FPS计算，未含行跨度填充、突发/仲裁损失：

| 原帧格式 | 每帧数据 | PL到PS原始载荷/秒 |
|---|---:|---:|
| NV12 / YUV420 | 3.1104 MB | 62.208 MB/s |
| UYVY / YUV422 | 4.1472 MB | 82.944 MB/s |
| BGRX | 8.2944 MB | 165.888 MB/s |

此通路是片内AXI/内存传输，不是此前100 Mbps SSH网口；不能因有原帧传输就直接判不可行，
也不能拿AXI标称峰值或PS内存喂VPU的帧率证明端到端可行。
当前任务副本`case/rtl/display/frame_to_ps_largebuf.v`具有64位AXI数据接口，
这里没有测定该真实采集路径的持续有效带宽、争用及丢帧率。

已核对SDK的实际调用：`vpu_encoder_actor.hpp`把原帧指针传给`enqueueDataPtr()`；
`vpu.h:864`起的实现内部使用`memcpy`拷入VPU输入缓冲（约890/895及921/926行）。
因此不能把方法名带Ptr解释为零拷贝。
以UYVY 20 FPS为例，PS DDR写入一次、VPU读取一次约165.888 MB/s，
再加一次CPU整帧复制的读/写，账面约331.776 MB/s。
这些是数据流记账，不是实测内存控制器流量；缓存、格式转换、驱动及其他任务还会改变负担。
同样不能把PL侧DDR的写/读、PS DDR流量与跨边界载荷混为一个数字。

摄像头若输入60 FPS，而录像只需20 FPS，必须在PL决定保留哪些完整帧，
避免先把60 FPS原帧全送PS再丢弃。识别2 FPS分支也应单独抽帧/预处理，
避免为识别再复制一条完整视频；这里是待验证的设计要求，不是现有实现已通过的声明。

历史VPU CPU/帧率测试主要从PS内存喂原帧，不包含当前PL采集与现役NPU并发，
不能作为这条完整链路的验收。当前PL JPEG测得约24 FPS也不能证明新VPU路线。
后续先对比两条路线的完整代价：PL视频编码可减少跨PS原帧载荷，但需要帧间编码IP、
参考帧缓冲及整板资源；VPU可复用硬编，但必须承担并验证原帧传输和当前SDK复制。
本次不切换VPU、不修改位流或模拟输入。

关键来源：当前任务RTL、官方SDK上述两文件、历史取证文档§15.8，
`D:/yzd/tmp/recording-transfer-review-20261017/bandwidth-budget.json`。

## PL先减量再交VPU的候选方案（2026-10-17，讨论阶段）

用户提出先在PL降低原视频数据量，再传PS侧VPU编码。该思路在结构上成立，
但要分别定义录像画质与模型输入，不能把模型裁剪/对齐结果直接作为全景录像。
建议从输入分出两路：识别分支按模型契约处理，目标2 FPS；录像分支保留完整视野，
先在PL完成整帧选择、必要的缩放及YUV格式整理，再送VPU，编码后写eMMC。
若真实SDI输入已经是YUV，可优先沿用该颜色空间，避免为录像绕经RGB。
以上为候选设计，未修改RTL、位流、VPU程序或摄像头模拟脚本。

按20 FPS、紧密排列、十进制MB计算：1080p BGRX为165.888 MB/s，
1080p UYVY为82.944 MB/s，1080p NV12为62.208 MB/s，720p NV12为27.648 MB/s。
NV12每像素平均1.5字节来自8位YUV420结构；实际缓冲须以驱动stride/sizeimage为准。
1080p BGRX转NV12载荷减少62.5%；但若源本来就是UYVY，只减少25%，不能混用基线。
720p NV12相对1080p NV12减少55.56%，代价是录像空间分辨率降为1280x720；
不能把其宣称为满足原1080p录像要求。
这些是原帧载荷计算，不是编码后码率或整条链路实测。

当前wcis_face_preprocess.v按单条命令从DDR读取像素，输出RGB888；
wcis_face_customop.v把每像素封装为32位写回。其几何采样思路可供参考，
但尚未证明适合作为持续录像缩放器，也没有现成NV12录像输出接口。
录像缩放需另外评估滤波、持续吞吐、缓存、背压与丢帧，不能仅把模型尺寸参数改大。
现SDK vpu.h的enqueueDataPtr仍有整帧memcpy，PL减量只能同步减轻该负担，不能消除复制。
历史取证文档2026-10-05曾验证NV12/UYVY送硬编出流；这是历史格式依据，
不等于当前PL输入和NPU并发链路已经验证。历史率控疑点也仍需当前环境复核。

现阶段建议保留1080p目标，先评估PL侧帧选择和NV12输出的62.208 MB/s路径；
720p为可选降画质档。后续验收应覆盖实际PL到PS持续搬运、VPU队列复制、
录像与识别并发、丢帧和真实场景码率。缩放降低原帧载荷，不保证压缩文件等比例缩小。

关键本地来源：fpga_project/rtl/wcis_face_preprocess.v、wcis_face_customop.v；
fpga_project/ps_app/vendor/include/pipeline/vpu/vpu.h:864；
fpga_project/outputs/board-reference-20261014-current/md/技术文档/板卡镜像实测取证.md的§15.2、15.4b、15.8/15.9。
格式定义核对：https://docs.kernel.org/userspace-api/media/v4l/pixfmt-yuv-planar.html 。
计算附件：D:/yzd/tmp/pl-vpu-preprocess-review-20261017/bandwidth-estimate.json。

本轮后台信息站检查：访问失败（URLError），本节依据本地源码、历史取证和格式官方定义。

## 人脸触发PL JPEG录像方案复核（2026-10-17，尚未实现控制逻辑）

本轮用户选择继续使用已完成的PL JPEG方案，提出检测到人脸才保存录像。
当前评估结论是结构上可行：PL维持像素处理与JPEG编码，PS根据人脸检测结果管理录像状态、
压缩帧队列、文件分段和eMMC写入。触发依据是检测到人脸，不要求匹配登记身份。
该调整主要减少无事件时的磁盘占用与写入，不改善有人时的压缩率、峰值吞吐。

存储连接依据face-emmc-store-20261015.md：32GB eMMC接PL引脚，经EMIO接PS原生MMC控制器，
Linux将/dev/mmcblk1p1作为ext4挂载到/mnt/wcis-emmc。PL引脚连接不等于PL自主存文件。
已有板测路径是PL压缩输出到DDR，PS读回JPEG字节后由文件系统写eMMC。
若要PL独立直接落盘，需要替换现有控制路径并实现eMMC访问、空间分配和共享一致性，
不属于现有已完成方案，也不是增加事件录像开关的必要条件。
真实摄像头接入后的目标录像路径是摄像头至PL、PL缓冲/编码、PS接收压缩字节、PS写eMMC；
当前SSH模拟输入仍先经PS上传原帧，不能宣称当前所有PS原帧搬运已消除。

建议控制行为（候选参数，不是已上线功能）：有效人脸检测立即进入录像；
最后一次检测到人脸后继续保存约5秒，期间再次检出则延长，避免偶发漏检切碎片段。
未知身份也应触发。可增加1至2秒压缩帧环形缓存补足检测延迟，但这要求待机时仍持续编码；
若待机停止录像编码可降低负载，却无法补回触发前画面，两者不能同时宣称实现。
检测2 FPS只是目标，触发延迟还包含模型处理及队列等待；不能承诺人脸一出现即保存。
帧队列需绑定帧号/时间戳，限定内存并明确写盘跟不上时的丢帧策略；
录像设置独立配额、按段保存，只轮转录像目录，人员库和每人一张原图须保护。

以此前165张不同视频帧实测平均JPEG大小、假设20 FPS估算，录制期间压缩载荷约3.22至3.46 MB/s，
约11.61至12.45 GB/实际录像小时。若包含延迟收尾后的录像占比为10%，
则每经过一小时约保存1.16至1.24 GB；若一直有人，空间消耗回到持续录像水平。
该比率是场景估算，不能保证现场压缩大小。短测PL编码23.9 FPS，
编码加读回、写盘及批末fsync为17.46至19.35 FPS，尚未证明长期20 FPS或与NPU并发达标。

本次只补充可行性与控制方案，不修改RTL、程序、位流或在线服务。
关键来源：face-emmc-store-20261015.md的存储连接与挂载说明；本报告已列出的PL JPEG板测和容量结果。

本轮信息站后台检查：访问失败（URLError），未读取最新站点内容。

## “AXI最高160 MB/s”来源与实际负载复核（2026-10-17）

用户提出板上AXI可能只有160 MB/s。本次查阅本地30TAI使用教程、悟净开发板硬件使用手册、
FPAI_DEMO说明，搜索项目源码/记录及公开资料，尚未找到该数值作为本板AXI统一上限的原始依据。
不能据此把160 MB/s判为真，也不能声称已测定每条AXI通路的最大持续吞吐。
FPAI_DEMO说明第3至4页把寄存器访问端口与512位PL DDR数据访问端口分开；
当前wcis_jpeg_customop.v也采用512位native DDR数据接口，不能与PS控制口或PS到PL搬运混算。
硬件手册中的DDR速率/位宽描述也不是当前PS到PL有效持续带宽测试。

复算已有2026-10-16板测，不开展新的DMA或在线压力试验：
BGRX首帧read_blocks=129600，每块64字节，读取8,294,400字节；
hardware_ms=41.69692，故原帧读取量除以整个硬件job时间约198.92 MB/s。
这是PL编码器读取PL DDR的已测路径，不是PS到PL最大持续带宽，亦不等于整片DDR带宽。
因此“所有路径统一封顶160 MB/s”与该记录不符；某一特定桥接/驱动/测试条件下是否160 MB/s，
仍须按对应端口、方向、时钟、突发、数据量和并发条件核实。
165帧逐帧复算及SDK短次读回计时见本任务bandwidth-evidence.json；
这些短次API吞吐数字不能直接作为连续摄像头传输或NPU并发的验收。

即便暂以PS接收压缩数据通路有效160 MB/s作假设，按已有样本1080p20 FPS的JPEG输出
约3.22至3.46 MB/s，只占约2.02%至2.16%，不会仅因这个假设就传不过去。
压缩帧大小会随场景变化，平均数不代表最大峰值；仍需有界队列。
不能只核算压缩字节：若在PL DDR先写入原帧、编码器再读一遍，JPEG再写入和读出，
同按20 FPS估算，BGRX总有效载荷约338.22 MB/s，RGB565约172.80 MB/s，尚未计NPU、
仲裁、行填充及其他访问。此为PL DDR流量账，不是把这些字节全部送给PS。
若160 MB/s确是上述共享资源的总有效预算，这些路径就需要调整；
但本次没有证据证明这一共享资源只有160 MB/s。
若摄像头输入60 FPS却先全量写DDR再选20 FPS，原帧写流量更高；
节流位置必须明确，不能用录像20 FPS替代真实采集写入负担。

结论：压缩数据交给PS保存本身暂无160 MB/s相关的不可行证据。
下一步真正需要验收的是采集写入、PL编码、NPU、压缩读回及落盘共同运行时的争用和丢帧。
已有23.9 FPS编码、17.46至19.35 FPS含落盘短测仍不能升级为长期20 FPS并发保证。
本次没有修改代码、位流、存储控制器或启动在线测试。

关键本地来源：fpga_project/rtl/wcis_jpeg_customop.v；
fpga_project/npu_photo/src/jpeg_runner.cpp的memory.read计时；
D:/yzd/tmp/pl-jpeg-board-20261016/video-bgrx8/frames.jsonl及两格式performance.json；
C:/Users/anxianji/Downloads/20260916/FPAI_DEMO说明.pdf。
附件：D:/yzd/tmp/axi-bandwidth-review-20261017/bandwidth-evidence.json。
信息站后台访问仍失败（URLError），未读取该站最新内容。

## 人脸识别帧率口径复核（2026-10-17）

本次重新读取2026-10-16的video-all-v3与video-latest/summary.json，分别4帧和8帧，
每帧face_count均为1、均有recognizer原始输出，属于单人检测、对齐、特征与比对链路，
不是只运行检测器。输入为768x432 RGB565LE；不是原生1080p动态识别验收。
完整帧收到后的pipeline_ms中位分别565.862与561.263 ms；
以帧数除以这批pipeline_ms总和，折合板端处理约1.751与1.771 FPS。
本机往返时间中位649与656 ms，倒数折合约1.54与1.52次/秒，
此处是延迟折算，不是从长时间连续运行验收得到的稳定帧率。
两次均为短样本且未与录像并发；不含模型启动准备。
每秒2次身份更新仍是目标，尚未达标；换成真实摄像头的收益不能预先算成已实现。

同时核对npu_photo/recognize_frame.py:40，当前源码仅在len(faces)==1时进行对齐和MobileFaceNet，
多人时返回multiple_faces及检测框，不会逐人完成身份识别。
因此不能把多人检测的存在称为已完成4人身份识别；4人2 FPS是待实现与验收目标。
事件录像的“检测到人脸”只需检测结果，可与身份特征计算分开设计，
但尚无独立检测触发路径的持续帧率实测，不给出假定FPS。

关键来源：fpga_project/docs/face-video-stream-20261016.md；
D:/yzd/tmp/face-video-stream-20261016/video-all-v3/summary.json；
D:/yzd/tmp/face-video-stream-20261016/video-latest/summary.json；
fpga_project/npu_photo/recognize_frame.py。
本次只查记录与源码，未重新测试或修改代码。后台信息站访问失败（URLError）。

## 两路硬件共存与软件并发边界核对（2026-10-17）

用户要求识别与录像并行，并核问JPEG位流是否移除了人脸路径。
结论需要分两层：现役接受的整板固件合入了两套硬件，但现有测试软件仍强制互斥，
没有实现识别和录像同时工作，不只是缺少同时运行的性能测试。
前文所述人脸触发录像“方案可行”不代表当前程序已经具备这种并发能力。

源码证据：wcis_recording_customop.v:50实例化wcis_face_customop，:60实例化wcis_jpeg_customop；
寄存器访问按页分流，512位DDR端口共用读写仲裁。stage_jpeg_board.py把旧顶层实例改为
wcis_recording_customop；构建任务case/rtl/ai7030_edif_top.v:257实际调用该合并包装层。
因此新BOOT/位流替换旧启动文件，但人脸预处理功能与JPEG功能共同保留，不是用JPEG删去人脸路径。

已完成的板证是同一启动分别运行：face-after-summary.json与accepted.json及两格式压缩日志
的boot_id同为43d0a6fd-ef63-4b81-8972-173d658eff1e；
同图检测12个tensor、特征输出SHA及框与改位流前一致。它证明功能保留，不证明同时处理。
本轮SSH只读核对启动号仍相同；照片服务active，访问其实际绑定的192.168.1.113:8091健康接口
返回ready、FAC1_customop_PL、模型缓存和eMMC就绪。首次127.0.0.1访问失败，
改用已有服务地址后成功；没有运行新的推理或压缩任务，也没有停止服务。
本次只复核当前启动号与已有验收记录一致，未重新读取/签收当前芯片配置或全盘BOOT内容。

软件证据：launch_jpeg_stream.py:32会停止wcis-face-photo.service，结束后恢复；
receive_jpeg_stream.py:36至37在整个JPEG会话持有npu.lock；人脸视频路径也持有同一把锁。
本轮同时读取已安装JPEG接收器与启动器，确认这些行为仍存在，SHA与本地源码相同。
现有机制因此禁止直接启动两条程序并行。不能简单删除锁：SDK设备打开/关闭、DDR分配、
原帧保留与输出缓冲所有权尚未统一管理，需先验证并发访问契约。

RTL的choose_rd/choose_wr在无挂起请求时选择JPEG请求，是固定JPEG优先；
保持请求所有权可以避免背压时换源，却不等于带最大等待保证的公平或实时仲裁。
目前仅允许一个native读事务在途，需在并发方案中核算双方等待和NPU共享DDR压力。

后续必要工作顺序（方案，未实施）：统一硬件设备与DDR缓冲所有权；
建立有界录像队列及独立识别抽帧，按帧号/时间戳保持原帧引用；
在SDK允许的范围内实现重叠/必要的短时分时，并保证仲裁等待有界；
再做录像、落盘、人脸检测/特征并行的长期丢帧和延迟测试，之后接入事件保存策略。
现有各路单独测得的FPS不能作为同时运行的FPS，20 FPS录像、2 FPS识别及4人目标仍未达标验收。

关键来源：fpga_project/rtl/wcis_recording_customop.v；fpga_project/scripts/stage_jpeg_board.py；
fpga_project/scripts/launch_jpeg_stream.py；fpga_project/npu_photo/receive_jpeg_stream.py与receive_video_stream.py；
D:/yzd/tmp/pl-jpeg-board-20261016/face-after-summary.json、accepted.json；
D:/yzd/tmp/face-jpeg-coexist-review-20261017/live-state.json。
本轮后台信息站访问失败（URLError），没有读取最新站点内容。未修改生产代码、位流或在线服务。

