# 原生1080p视频输入与PL JPEG整板测试

采样证据日期：2026-10-16；续接核验日期：2026-10-17，Asia/Shanghai。当前状态：**两种格式完整视频与板内编码测试通过，板内约23.9 FPS，包含最终落盘的批次为17.46/19.35 FPS**。照片服务恢复、人员库SHA保持一致。结果与复测方法见[核验报告](pl-jpeg-board-acceptance-20261017.md)；以下失败与构建过程为历史记录。

## 输入与测试目标

使用OpenCV官方测试资产 [1920x1080.avi](https://github.com/opencv/opencv_extra/blob/22b4a7bc7cf5e4ddd3a0426eafc88bae28d3dfc3/testdata/cv/video/1920x1080.avi)，
本地路径为 `D:/yzd/tmp/pl-jpeg-board-20261016/videos/1920x1080.avi`。
文件7624984字节，SHA256为 `42f77d89c19428a06c70e3c8f455cc3cced40bd0b46dafee3bfbfde323362153`。
OpenCV读取为1920×1080、25 FPS、165帧；使用文件本身的尺寸，不从较小视频放大。没有据文件尺寸推断拍摄设备。
来源与归属保留在同目录 `source.json`；未给该资产另行声明所有权或许可。

扩展原有 `scripts/stream_video_to_board.py`，增加 `--backend jpeg`，原face入口保持可用。
电脑OpenCV解码，按RGB565LE或BGRX8打包，通过已有SSH二进制分片协议发送；
板端PS接收至tmpfs、SDK上传PL DDR，JPG1硬件编码，压缩字节读回后由PS写eMMC。
这仍是采集后帧的注入测试，不是SDI电气输入或PL直接控制eMMC。

`--mode all`逐帧不限速，无20 FPS限制。计划分别测量：

- 新视频帧：本机解码→SSH→DDR→PL JPEG→读回→eMMC批末fsync。
- 板内DDR回放：同一已上传原帧连续编码，排除SSH速度限制，明确不算新的采集帧。
- DDR回放加保存：包括压缩字节读回、文件写入和批末fsync，不把页缓存写入速度当作落盘速度。

本次启动日志的网口为100 Mbps/Full。1920×1080 RGB565每帧4147200字节，
忽略开销的链路上限约3.01 FPS；BGRX8每帧8294400字节，上限约1.51 FPS。
这些是带宽算术上限，不是已测得FPS，不能用于判断将来SDI输入的压缩能力。

## 实现与验证边界

新增 `rtl/wcis_jpeg_customop.v`：复用官方512位CustomOp DDR端口，
GP 100 MHz / HP 200 MHz通过既有mailbox跨域，双64字节输入槽、有限输出容量、
地址/格式/重叠检查、错误及周期计数。JPG1寄存器页为 `0x400c2100`，ID `0x4a504731`。
`rtl/wcis_recording_customop.v`保留原FAC1和adder，增加有所有权保持的读写仲裁。
没有修改原人脸预处理RTL或vendor JPEG核心；压缩核来源和许可见
[独立原型记录](pl-jpeg-compressor-20261016.md)。

板端 `npu_photo/src/jpeg_runner.cpp`常驻打开设备、上传/编码/读回分别计时，
没有CPU JPEG编码和NPU模型推理。使用SDK管理的16683200字节分配，
源、输出及守卫均64字节对齐，限定在已验证的128 MiB窗口；没有扫测完整2 GB DDR。
每张新帧都完整读回核对，JPEG尾部DMA读回向上按64字节对齐，文件仅写真实JPEG长度。
会话最多300张源帧/每批300次回放、256 MiB录像，失败不自动重试硬件命令。

`receive_jpeg_stream.py`复用原帧协议和截止时间读入器；UUID、帧号、PTS、尺寸、步长、SHA均核对。
测试独占原NPU锁并暂停照片服务，完成后恢复；不能据此声称NPU与录像已并发运行。
源原帧只在tmpfs暂存，结束后删除；人员库、原照片服务文件不改。

本地验证已通过：

- 新DDR/CDC接口两种像素格式、4个完整JPEG；DC/AC系数与固定版本软件模型最大差异≤1。
  覆盖反压、守卫、无效/重叠/越窗地址、容量不足及恢复、忙中配置拒绝。
- 新外层wrapper通过原有6个人脸/adder场景，包括1080p检测预处理。
- 原帧协议/打包8项检查通过；Python后续入口修改另有语法检查。
- 新原生1080p视频首帧编码RTL通过：Q75、131453字节、4163570周期，
  100 MHz下折算24.01785 FPS；完整解码，RGB PSNR约44.37 dB。
  SHA256 `16f2219579d32ee1d6a444233ff665a9af2549b8c6adef23dbe2ec4f8d7e81c7`。
  仿真墙钟245.16秒，不是硬件处理耗时。

AArch64客户端在学校服务器独立任务中交叉编译，不在本机替代构建。
最终当前客户端SHA为 `fd156ccd330a2f68526dd526605a0223a6b1330a34de041b61c0817ff2ec6feb`，
部署应用 `/root/wcis-face/apps/jpeg-input-b27b63c58096`，已通过帮助/依赖启动检查。
只有硬件试验通过后才能把该应用视为板端功能验收。

## 首次整板失败与对照

首次完整实现完成：45236 LUT、62742 FF、172.5 BRAM tile、50 DSP，
setup WNS +0.030 ns、hold WHS +0.029 ns、布线错误0。
6个mailbox的数据路径均存在且有正余量，JPEG计数器时钟确认为100 MHz。
保留原厂两项1 GHz NPU脉宽告警WPWS -0.409 ns，不作生产时序签收。

Procise生成BOOT，核对新bit有效载荷确实进入PL分区，FSBL/BL31/U-Boot与原板逐字节一致，
DTB/uEnv不改。首次候选BOOT SHA为
`17f3879e876e2801bf7af1d701537a01691c7146231999d7bea6f018c1aa9206`。
原BOOT与启动分区备份已保留，试验设有未验收自动回退计时器。

两次新启动均在**JPEG启动前**的原帧上传校验失败。
详细一次为4147200字节中34043字节不同，首差异偏移33986。
随后使用同一SDK程序，仅对本次SDK分配内存做写/读，不发CustomOp命令：
offset 0/64、整块/64 KiB分块四种组合，新位流各约60487～60738字节不同；
重复读取还存在约2394～2680个字节变化。不能把该数据作为压缩输入继续计时。

恢复原BOOT后，同一程序、相同范围、四组组合及二次读取全部零错误。
原人脸检测12组输出、识别特征SHA及检测框与部署前完全相同，照片服务恢复。
因此已确认故障与新位流/初始化状态相关；尚未确定具体失效路径，
不能直接下结论为JPEG算法、网口或板卡永久损坏。

首次失败和回退证据位于任务 `attempt-1`、`source-verification-diagnostic.json`、
`memory-probe-new.json`、`memory-probe-old.json`、`face-rollback-summary.json`。
全板增量实现尝试在多轮布线中停留于一个冲突，已停止本任务进程并保留 `attempt-2`。
局部模块替换也验证了工具边界：旧优化网表多出276个内部端口，不能直接按RTL接口替换；
没有强行跳过接口检查。

当前使用 `scripts/build_jpeg_preserved.tcl` 与 `preserve_jpeg_shell.tcl` 复用原已验证检查点。
截至20:19，已收窄为只固定522个DDR物理接口和相关时钟单元的位置，
DDR控制器、NPU普通逻辑及新增逻辑允许重新布局；专用I/O之间的走线在布线前单独保留。
该方案仍需完成时序、布线、打包、DDR零错误、JPEG解码及人脸回归后才能验收。

## 再实现的约束问题与修正（10月16日晚）

保留区域实现中，尝试3因校准控制器RDY被锁而不能复制；尝试4只释放RDY，
出现 `Place 30-1113`：复制后的校准控制器RST未连接。这两轮均未上板。
尝试5释放IDELAYCTRL的RDY/RST/REFCLK控制网络后，布局及物理优化通过，
当前布局调用没有该严重告警，物理优化报告严重告警/错误均为0。
不能把这一步当作最终连接或板端DDR证明。

尝试5进入布线后，原有固定走线与新放置引脚产生1118项冲突，涉及307个固定网络；
查询已完成的物理检查点，305个普通网络的端点均为寄存器/LUT/进位链/片上RAM等，
另两项是合并常量GNDNet/VCCNet。没有强行忽略不可布线引脚。
原工程没有Pblock/布线包含区域，整块锁定方案约束范围过大。
[AMD UG905 v2018.3](https://docs.amd.com/api/khub/documents/dUZkF9u9qQ4x4MtRgpH9aQ/content)
说明了分区复用时Pblock与CONTAIN_ROUTING的要求；因此不能仅凭锁定命令推断可无冲突复用。

尝试6/7对冲突内部网络和常量网络逐项清理固定约束，遇到12009个层次网络片段；
批量属性修改耗时，尝试7进程工作集由约2.4 GB升至约6.6 GB，
机器剩余物理内存约1.2 GB，已停止本任务CAD进程并保留日志，没有生成或部署这两轮位流。
本轮仅停止通过PID、父进程与本任务运行标记核对的CAD子进程，不停止板端硬件工作进程。

当前 `release_jpeg_conflicts.tcl` 改用工具原生 `lock_design -unlock -level routing`，
保留已有单元位置/逻辑保护，只重新固定DDR非恒定、已有走线的物理I/O/PHY/时钟信号，
排除校准控制网络，允许内部控制线及共享常量线重新布线；仍需等待实现与板测。
最终保留网络清单将输出 `ddr-preserved-net-names.txt`。

已补强验收入口：`audit_jpeg_board.tcl` 直接检查最终网表每个IDELAYCTRL的RST/REFCLK均有驱动；
`package_jpeg_board.py` 区分追加日志中的当前调用，并以SHA绑定已完成的布局日志及恢复用物理检查点，
拒绝缺失连接检查或有校准复制错误的候选；`check_jpeg_ddr.py` 在不启动CustomOp的条件下运行
同一有界SDK内存对照，检测失败会隔离当前启动，不能继续用错误原帧测试压缩。
这些入口的代码就绪不等于已经完成本轮板端检查。

### 20:19继续检查

原生解锁区域走线已能正常执行，避免了逐项清理常量网络的高内存问题。
尝试8进一步暴露FIFO连接普通逻辑的固定线路冲突；尝试9仅保留1254条专用物理I/O之间的线路，
初始固定线路/引脚冲突为0，但原有单元位置整体仍被冻结，后续重叠节点由5299降至9后反复不变。
已保留 `attempt-8`、`attempt-9`，停止本任务CAD路由，不把中间结果打包上板。

接着从已有优化检查点重新布局，取消普通逻辑的位置固定。
尝试10额外设置 `IS_BEL_FIXED` 时触发 `Vivado 12-1405`，提示DDR差分P脚/F2负侧分类冲突。
没有更改原板管脚或降低该检查；取消额外BEL固定，沿用参考LOC与原板PACKAGE_PIN约束。
新一轮已确认 `DDR_IO_AND_CLOCK_LOCATIONS_FIXED=522`，校准复制错误为0，进入全局布局。
`Place 30-575` 的输入IOB_X1Y124与MMCM_X1Y1位置告警已与原正常工程日志核对一致，
沿用原厂CLOCK_DEDICATED_ROUTE设置，没有为本次新增降级。

打包检查另外拒绝当前调用中的 `Route 35-341` 固定线路/引脚冲突。
`analyze_jpeg_board.py` 补充核对每个新帧及每次驻留回放的完整DDR源读取块数、
JPEG写出块数和非零硬件计数，避免把复用JPEG文件误当作重新压缩。
以上仍为实现/验收入口进展，尚无通过本轮板测的JPEG帧率。
19:48再次只读核对原启动 `d5b537dc-c79d-4c35-8dc8-3a9c220b3046`：
人脸服务ready、人员库全部文件SHA与任务前一致、回退计时器disabled。

### 21:01继续检查

尝试11完成布局与物理优化，随后布线重叠节点由6079降至59、57，再升至58，
未形成可用的布线结果。已停止经PID/父进程及本任务rundef.js路径核对的CAD进程，
证据保留在 `attempt-11`，未部署该轮固件。成功布局日志与当前physopt检查点另以SHA绑定，
供仅恢复布线时验收，替换了早先尝试5的布局证明。

尝试12从相同physopt检查点继续，只清理旧普通逻辑走线，保留专用DDR路径及既有物理位置。
采用一次工具原生unroute操作，先合并层次网络别名，避免逐个修改共享常量树。
`clean-routing-status.rpt` 核对：104079条可布线网络中1153条仍固定且已布线，
102926条普通网络未布线，错误0。此前1254是候选专用网络数，其中部分为站内连接，
工具不接受额外固定标记；实际固定的可布线网络数以1153为准。

本轮实现仅启用4线程布线，不修改共享工具配置。新调用复用1112条网络、
非复用102892条，确认普通旧走线确已清除，不是再次沿用前一轮60.23%的普通走线。
尚需等待最终布线、时序和板端DDR/JPEG验收，不能由初始化阶段的时序估计推断结果。

### 21:24实现检查通过，待板测

尝试12清理旧普通走线后，布线约5分04秒完成，重叠节点清零。
最终报告仅原案例resize输出到frame FIFO有一条setup -0.009 ns，hold +0.004 ns。
没有放宽时钟或假路径，继续对已布线设计执行标准post-route物理优化，
setup改善为+0.025 ns、TNS 0，hold +0.004 ns、THS 0。
整板45329 LUT、62677 FF、172.5 BRAM tile、50 DSP。

旧工具单独启动post-route步骤时，自动生成脚本在打开检查点前查询current_project，
报 `Coretcl 2-88`。采用scripts-only生成，仅在本任务生成副本中把两处用于SDx状态提示的
TOOL_FLOW查询固定为当前Vivado流程，再运行原生成步骤。保留
`postroute-generated-before.tcl`、`postroute-generated-executed.tcl`、`postroute-child-console.txt`。
实际工具运行写出postroute检查点及完成标记，不伪造运行状态。

重新打开检查点的会话未恢复原XDC中的DRC级别设置，REQP-52/56重新显示Error。
核对原正常工程和任务副本 `constrs_1/ai7030.xdc` 前四行完全一致，
审计仅恢复原有REQP-44/46/52/56 Warning声明，保留其他错误检查，重新报告后通过。
未重新读取整个XDC或更改管脚/时钟。保留恢复前报告 `drc-before-restoring-vendor-policy.rpt`。

最终6组mailbox真实数据路径均存在且SLACK非负，JPEG计数器为100 MHz，
5个IDELAYCTRL的RST/REFCLK均有驱动，bus-skew无VIOLATED，布线错误0。
仍保留原有两项NPU 1 GHz脉宽告警，WPWS -0.409 ns，不作生产时序签收。
`timing-gate.json` 已通过，当前正在生成位流，尚不能称本轮板端DDR/JPEG已通过。

## eMMC有界写入基线（20:43）

在恢复的原固件上，对 `/mnt/wcis-emmc`（`/dev/mmcblk1p1`，ext4）执行两次32 MiB写入，
每次计时包含末尾 `fsync`，结果为10.775、10.756 MiB/s。
1 MiB随机缓冲在计时外生成，测试文件位于本任务独立目录，完成后删除，未操作PL/NPU。
证据：`D:/yzd/tmp/pl-jpeg-board-20261016/emmc-write-baseline.json`。

这是PS向eMMC写文件的短测，不能当作PL压缩吞吐或长时间录像证明。
已有原生RTL样本131453字节/帧在20 FPS时约需2.51 MiB/s，低于该短测写入速度，
但JPEG大小随场景变化，仍须完成真实压缩与写文件的组合测量。

## 修正后上板与两帧检查（21:27）

候选BOOT SHA `e472e96cdf7ce6d82d1f278fda0240b68580e71558c031045210f844865d629b`，
bit SHA `79b1ac4d1f00a5f35a3855fa2aa44f7d06707bf76aaac53e53818040f832f162`。
核对PL分区为本次bit，FSBL/BL31/U-Boot与原包逐字节一致，DTB/uEnv不改。
正常重启后的boot id为 `43d0a6fd-ef63-4b81-8972-173d658eff1e`。

在启动JPEG前，SDK有界内存四组写读、二次读取及两次读取间变化全部0错误，
见 `memory-probe-guided.json`。这是分配范围检查，不是完整2 GB PL DDR容量扫描。
两帧原生1080p RGB565LE视频编码均完整解码，大小138413、163140字节；
原帧DDR全量校验、原生读写计数、帧号及输出范围检查通过，首帧全部DCT系数与固定参考最大误差1。
硬件job计数41.63752、41.63761 ms，含电脑注入和最终fsync的两帧入口速度1.58 FPS。
该两帧尚不足以给出持续性能结论。

同一次启动中，人脸检测12个输出tensor SHA、识别特征SHA和检测框均与任务前完全相同，
服务恢复ready。已通过小用例验收并关闭未验收自动回退计时器，见 `accepted.json`、
`face-after-summary.json`、`smoke-rgb565-v2/performance.json`。
接下来分别进行完整165帧RGB565LE/BGRX8注入及每种格式两组300次DDR内回放，
测量期间独占硬件并暂停照片服务，结束后恢复；不能将该测试称为NPU并发录像验收。

## 证据与尚未完成项

任务文件统一在 `D:/yzd/tmp/pl-jpeg-board-20261016`；学校任务为独立 `D:/yzd/tmp/wcis-face-jpeg-*`。
后台项目站点已读取HTTP200项目正文，未保存认证数据；安装工具3个时序/器件数据文件SHA保持不变。
没有修改Downloads原案例或共享工具链，没有做任意物理地址探测。

完整165帧视频、两种格式各两组300次板内重新编码、930个保存JPEG完整解码和会话结束状态检查均已通过。
板内编码约23.9 FPS，包含最终落盘为17.46/19.35 FPS；后者尚未稳定达到20 FPS。
真实SDI持续采集、长时间录像、文件分段/配额、NPU并发/多人识别均不在本次已通过范围。

关键来源：本报告所列RTL/C++/Python脚本、`verification/summary.json`、
`face-regression/verification.json`、`native-rtl/video-1920x1080-q75/result.json`、
`school-build/receipt.json`、`attempt-1`下报告与BOOT清单，以及DDR对照JSON。
