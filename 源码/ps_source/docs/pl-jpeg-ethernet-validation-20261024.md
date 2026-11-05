# 1920×1080 PL 网口预览验证（2026-10-24）

本记录按本轮聊天日期 2026-10-24 归档。沿用前一日创建的隔离目录 `D:/yzd/tmp/pl-jpeg-ethernet-1080p-20261023`，目录后缀不代表以下工作发生在 23 日。前期设计记录见 `pl-jpeg-ethernet-1080p-20261023.md`。本记录仅依据源码、仿真、综合、构建日志与本轮只读板端检查。

## 当前进展

后续更新：共用高速时钟的 SERDES 单向发送候选已完成独立布线和时序检查，见 `pl-ethernet-shared-clock-validation-20261024.md`。这是对下文早期发送侧失败的后续进展，整板仍未验收、未生成或部署新 bit/BOOT；不能混同两类结果。

目标保持完整 1920×1080：SDI 原始 RGB → PL 流式 JPEG → WJP1/UDP → PL 千兆网口 → 内网接收机 → 浏览器。识别仍使用独立的原始 RGB565 采帧，避免把 JPEG 解码变成模型输入。当前新增位流尚未生成、打包或部署，整板实现尚未验收，不能据此宣称上板 1080p30 或实际节省百分比。

## 可行性复核与路线收口（15:40 后）

用户指出应先确认能做什么、不能做什么。本轮复核后停止追加 CAD 参数试验；当前没有本任务 Vivado worker 运行。此前把完整收发、动态 ARP 和极限噪声 30 fps 零丢帧一起推进，超过了先证明连续 1080p 预览的最小验证范围。用户明确选择的是 1920×1080 分辨率；全场景 30 fps 零丢帧不是用户已经确认的硬性要求。仍必须拒绝坏帧、限制积压，并如实测量实际帧率。

| 项目 | 现有证据 | 结论与边界 |
| --- | --- | --- |
| 1080p JPEG 编码与分片 | `pipeline-fifo-r5/pipeline-gradient/summary.json` 和 `pipeline-fifo-r5/pipeline-noise/summary.json` 各 3 张完整 JPEG，通过校验并解码为 1920×1080 | 数字逻辑短时仿真成立；物理采集、板端运行尚未证明 |
| 整板集成 | r5 完成综合和布局/物理优化，随后中止；控制复位已修正并通过 12 相位回归 | 尚无最终 routed 通过结果；不能打包、部署或承诺交付 |
| 接收网口时序 | 独立试验多种路径尚未得到可直接整合且余量充分的方案；最好的直接 PLL 位置与原 PS PLL 冲突 | 当前完整收发接法不能作为已可用的实现；不等于 PL 网口硬件不能做 |
| 主机与浏览器 | 渐变短测通过；原生原型高噪声回环 600 帧完整 599 帧、内核丢 35 包 | 普通负载链路有软件证据；实际相机帧率、物理 NIC 和长期负载仍未验收 |

下一条更小的候选路线是固定内网接收端 MAC 的单向 UDP：保留 PL 编码、分片与物理发送，不在 FPGA 中接收数据或动态解析 ARP。源码依据为已固定的上游 `udp_ip_tx.v`、`ip_eth_tx.v`（显式输入目标 MAC）、`eth_axis_tx.v` 与 `axis_gmii_tx.v`；只是源级可组合性判断，尚未实现或验证。它针对当前 RX 采样和区域 BRAM 约束，避免改动原 NPU/DDR 时钟。代价是需要配置实际下一跳 MAC，接收机换网卡、跨子网或网络拓扑变化后必须重新核对，不能作为通用自动联网能力。

后续应先做独立 TX 候选的有界验证：真实 TX 引脚与电平、固定时钟与外部 PHY 建立/保持约束、最终完整路由、合法时钟连接以及从 RTL 捕获到的 FCS/IP/UDP/JPEG 校验全部通过，才进入一次整板集成。任一项失败先给出具体路径和资源判断，不继续无界扫参数。独立 TX 通过也不等于整板成功；整板仍须新路径时序、原硬件合同保持及后续可恢复上板验收。若发送侧同样无法关闭风险，再评估 PL 编码后经现有 PS 网口传送的替代路线；该替代会保留 PS 搬运开销，也尚未测量收益。此处只收口结论和验证顺序，没有启动新实现或更换板端程序。

## 经确认的单向发送独立验证（15:45–16:05）

用户随后同意先做单向发送验证。新增候选 `rtl/wcis_jpeg_network_tx.v`，仅组合已固定上游 `udp_checksum_gen`、`udp_ip_tx`、`ip_eth_tx`、`eth_axis_tx`、`axis_async_fifo`、`axis_gmii_tx` 与 `ssio_ddr_out`。UDP 校验和保留，目的 MAC 显式配置，零地址/组播地址拒绝提交报头；完整帧 FIFO 深度 4096，在 150 MHz 逻辑域与 125 MHz 物理发送域之间提供背压。协议与 MAC 上游源码未修改。没有接收时钟、RX FIFO、自动速度侦测或动态 ARP；PHY 的千兆全双工和 TX 内部延迟为零须由管理端确认后才能使能。

`sim/tb_jpeg_network_tx.sv` 与 `scripts/verify_pl_jpeg_tx.py` 分别用 SIM DDR 模型、只读 Xilinx ODDR/glbl 原语模型，各通过 17 个真实引脚输出报文检查：1/17/1440/1472 字节负载、奇数尾字节、连续最大报文、572 个 producer 背压周期、非零 UDP 校验和、IPv4 校验和、Ethernet FCS、逐字节负载、中途 UDP 复位与更换 MAC 后恢复。零 MAC 与广播 MAC 的报头提交均被拒绝。结果 `tx-only/simulation/summary.json`、`tx-only/simulation-xilinx/summary.json`。这些是硬件行为仿真，不是物理收发验收。

新增 `sim/tb_pl_preview_pipeline_tx.sv` 和 `scripts/verify_pl_preview_tx_pipeline.py`，串联真实像素输入、JPEG 核、WJP1 分片和本次发送模块；256×64 渐变输入 3 帧，编码和接收各 3 帧，9 个 UDP、0 个 ARP，拒绝/中止 0，JPEG 均成功解码并检查像素误差。证据 `tx-only/pipeline-gradient/summary.json`。共用校验器 `verify_pl_preview_pipeline.py` 新增显式 `tx_only` 分支，旧完整收发模式默认行为保持。当前这次小图验证不能冒充新 TX 路线的全高清或板端证明；旧 r5 全高清编码证据仍有独立源散列。

物理探针为任务目录 `tx_probe.v`、`probe-tx-only.tcl`，固定六个既定 TX 球位 AD23、AD26、AF24、AF25、AA24、AB24、LVCMOS18、DRIVE 8、FAST slew；使用既有预览所选 PLL 位置 X1Y1 和 150/125/+90°125 MHz 配置，显式为所有生成时钟保留 0.1 ns 用户不确定度，输出两 DDR 边均为 +1.2/−1.2 ns 的建立/保持要求。第一次启动因 `sync_reset.tcl` 路径错误停止于约束加载，修正为固定上游 axis 子目录后只运行了一次完整布局布线，没有扫描 PLL 参数或放松约束。

**结果：独立物理门槛失败，停止进入整板。** `tx-only/physical/route.rpt` 显示 1827 个可布线网全部布通、路由错误 0；`timing.rpt` 的 WNS −0.061 ns、WHS −0.036 ns，各 5 个失败 endpoint，最差脉宽 +1.100 ns。`tx-io-timing.rpt` 将最差建立定位到 TXD1 输出，最差保持定位到 TXD2/TXD3；两个类型均在 Fast corner。不是主机或 JPEG 运算慢导致。探针资源为 LUT 953、寄存器 936、BRAM 2.5 tile、单个 PLL，包含常量配置的测试驱动；不可外推成可配置整板实际资源。

探针的 reference_clk/reset 是合成台架端口，没有板级约束，200 MHz 参考输入是假设，不能用于装板；真实整板 HP200 来源不同。DRC 保留 UCIO-1（这两个端口）与 ZPS7-1（无 PS7 的独立探针），没有降低其级别或生成 bit。因而当前失败仅能说明这次独立接法未满足合同，不能推论所有 PL 网口方案或真实整板均不可能。原 NPU/DDR 时钟、完整收发源码和板端程序均未切换。本轮没有启动下一次整板综合/布局布线或制造候选 BOOT。

## JPEG 后经 PS 转发的性能预算（17:40 后）

用户同意先核对厂商依据，并询问 JPEG 编码后的性能占用。本次只读查询板端 `/sys/class/net/eth0/{speed,duplex,operstate,mtu}`，2026-10-24 17:40:55（北京时间）返回 100 Mbps、full、up、MTU 1500；同时见 4 个逻辑 CPU。结果 `preview-current-link.json`，查询脚本 `read_preview_link_budget.py` 不调用 SDK、不改网口设置、不停止服务。2026-10-17 旧报告的 100 Mbps 记录不能单独代表当前，本次已重新确认。

以下均用十进制 MB，30 fps 是计算条件，不是板端承诺；JPEG 数值来自 r5 两组短时全高清 RTL 输出大小，不是新拍真人或确定的最坏上界。

| 数据 | 平均每帧字节 | 10 fps 净数据 MB/s | 30 fps 净数据 MB/s | 30 fps 净码率 Mbps |
| --- | ---: | ---: | ---: | ---: |
| 原始 1920×1080 RGB565 | 4147200 | 41.47 | 124.42 | 995.33 |
| Q75 JPEG，渐变仿真 | 296427 | 2.96 | 8.89 | 71.14 |
| Q75 JPEG，高噪声仿真 | 1799491.7 | 17.99 | 53.98 | 431.88 |

当前 100 Mbps 对应理论 12.5 MB/s，尚未扣网络协议和其他业务；高噪声这组样本即使不计开销，也只够约 6.95 fps，不能许诺当前 PS 网口传全场景 1080p30。渐变组 30 fps 净码率低于链路速率，但这不是实际 TCP/UDP/浏览器吞吐证明。JPEG 大小取决于质量和画面，PS 网络出口按观看端数量还可能重复发送。

若 PL 完成编码，PS/VPU 的连续 JPEG 编码工作可由此支路替代；PS 仍需完成压缩字节读回或 DMA、缓存同步、用户态/内核态传递和网络发送，不能说 CPU 零占用。仅由 MB/s 推算 CPU 百分比没有依据；每增加一次完整内存拷贝，还会发生对应的一次读和一次写。原生接收器约 0.401 核来自 102 主机的回环重组与 HTTP 测试，不是板端 PS 转发测量，不用于估计 PS 占用。

已有 2026-10-16/17 板测 `docs/pl-jpeg-board-acceptance-20261017.md` 证明旧 100 MHz JPG1 DDR 路径可以把 PL 编码字节读回 PS，驻留原帧编码约 23.9 fps；该结果包含原帧读取/编码，不能当成当前 SDI 流式 JPEG→PS 网口的转发基准。JPEG 核旧独立综合 `D:/yzd/tmp/pl-jpeg-20261016/synthesis-core/utilization.rpt` 为 2622 LUT、1224 FF、16 BRAM36、29 DSP，仅是核心历史资源，不含采集 FIFO、DDR/DMA、网络或整板拥塞，当前整板用量不能归因给 JPEG 单模块。

本地原始 FPGA 案例范围内，本次搜索只发现 PS 配置 IP 中的 RGMII 电平检查，没有找到可直接套用的 PL 网口完整工程。有限网络检索找到复旦微产品规格列 2×GigE（https://www.fmsh.com/fpga/products/chip/fmql30tai.html）及 Motorcomm PHY 调试说明链接；规格能力不等于当前链路已协商为千兆，本次未取得与本板/完整设计匹配的 PL RGMII 时序参考工程，不能由此断言厂商没有。下一步仍需核对可复用依据；在 PS 转发方案上，100 Mbps 协商原因也是必须排查的性能变量。没有改网线协商参数或启动新的 CAD 试验。

## 原 VPU 约 28 fps 的同条件核对（17:55）

用户指出原 VPU 预览能达到约 28 fps。之前用 1080p 高噪声样本说明百兆带宽风险，不能直接解释旧预览瓶颈，更不能据此断言旧预览需要千兆或 PL 编码会更快。源码 `ps_app/src/wcis_camera_owner.cpp` 的采集、元数据及 NV12 转换为 960×540，`wcis_owner_vpu.hpp` 的连续 JPEG 默认质量为 80；与新 PL 路线的 1920×1080、Q75、不同仿真画面不是同条件对照。

2026-10-24 17:55，`read_current_vpu_budget.py` 通过已有管理连接，只读 owner 控制文件及 `/dev/shm` 内当前原子发布的 `latest.frame`，不调用 SDK、不创建 VPU 实例、不切换服务、不保存图像。连续约 1 秒读取 25 个不同帧，解析每份 JPEG SOF，均为 960×540；JPEG 为 9323–9600 B，平均 9493.72 B。按用户观察的 28 fps 换算，净 JPEG 流量约 2.13 Mbps，远小于当前 100 Mbps 链路，因此两者没有矛盾。这个当前场景大小不代表其他场景或长期平均值，也不能把像素数扩大 4 倍直接当作 JPEG 大小或 CPU 负载扩大 4 倍。

同一短窗口 `encoded` 计数增加 29、间隔 0.9811 s，约 29.56 次编码完成/秒；该值只测 owner 编码计数，未测网络、浏览器实际显示或端到端延迟。当前旧元数据没有 `preview_mode/vpu_enabled` 新字段，记录为 null，没有据此宣称新按需模式已部署。证据 `current-vpu-budget.json`。结论是应以相同实拍输入、相同分辨率和可比画质核对 VPU/PL 的帧率与 CPU/VPU 占用；当前没有 PL 优于现有 VPU 预览的实测结论。

## 编码与实际 MAC 串联验证

`sim/tb_pl_preview_pipeline.sv` 将采集桥、真实 JPEG RTL、WJP1 分片、UDP/IP/ARP、MAC 与 RGMII 串联。没有注入预制 JPEG，也没有强制内部 FIFO/MAC 状态。网口捕获包含真实前导码、FCS 和仿真时间戳；`scripts/verify_pl_preview_pipeline.py` 独立检查 FCS、IPv4/UDP 校验和、重组、JPEG 解码与完整帧数。

- 小尺寸 64×16、256×64 均通过；后者 3 帧分为 9 个 UDP 包，覆盖多分片传递。
- 完整 1920×1080、150 MHz 编码域、约 74.25 MHz 像素域、2200×1125 时序，在隔离 Linux 仿真工作目录运行 Verilator。渐变和高噪声各输入 3 帧，分别产生 636、3858 个 UDP 包；两组均编码/接收 3 帧，拒绝和中止均为 0。
- 渐变组完整帧间隔约 30.00003 fps，噪声组约 29.99840 fps。6 张接收 JPEG 均解码为 1920×1080。渐变图与已知输入的像素平均绝对误差约 3.537（8 位通道），包括完整上下边缘。
- 这些是约 100 ms 有效输入的 RTL 仿真结果，包含真实网络模块背压，不能替代长期板测、真实 PHY、电缆/交换机、主机丢包或浏览器显示帧率验收。

证据：任务目录的 `pipeline-gradient/summary.json`、`pipeline-noise/summary.json`、对应 `simulation.log`、`ethernet-stream.bin`、`received-*.jpg`；上传源快照与散列见 `pipeline-source.tar.gz`、`pipeline-source.json`。早期仅采集桥+编码器的实验与本次完整 MAC 实验分别保留。

另做了网络受阻后恢复的串联用例（`pipeline-recovery`）：512×128 高噪声，先不给 ARP 响应，编码/网络背压使第一帧被完整拒绝；随后提供有效 ARP，再输入 3 帧，全部编码并在主机完整解码。结果输入 4、JPEG 3、拒绝 1、中止 1、UDP 完整帧 3；坏帧没有被展示，也没有阻止后续帧恢复。该变体台架由 `test_pipeline_recovery.py` 生成，精确编译输入散列保存在该目录 `source-hashes.json`，区别于普通全高清台架。它不等于真实拔线/重协商或 1 秒 ARP 完全超时测试。

## 整板集成、资源和约束修正

`scripts/prepare_pl_jpeg_preview.py` 在任务副本中集成 `U_pl_preview` 和新网口，接入 `sdi_rx_clk`、完整 `cam_rgb/cam_vs/cam_data_en`。保留旧 FAC1/JPG1 寄存器页、原 DDR 主接口和已部署的固定优先级参数。旧布线网表把 CSR 信号与其他控制器合并，不能安全截取别名，所以采用完整源码综合，再复用已部署参考布局；不是盲目往旧网表接线。

更新后的 r4 整板综合当时完成，日志 `build-full-r4-console.log`；当时记录资源为 LUT 56215/78600（71.52%）、BRAM 207.5/265（78.30%）、DSP 79/400、BUFG 24/32、MMCM 5/5、PLL 4/5。同名 `preview-full-synthesis.dcp`、`preview-full-synthesis-utilization.rpt` 后来由 r5 更新，当前内容应以下节 r5 结果为准。初版 BUFR 综合曾为 BUFG 23/32；增加的一个全局缓冲见下文。上述是综合资源，不是最终布线资源。新增时钟使用剩余 PLL 产生 150/125 MHz 和 125 MHz +90°；前期记录中的“独立 MMCM”描述在此更正，整板没有剩余 MMCM。

首次约束检查发现 Vivado 2018.3 的 `read_xdc` 不执行 XDC 中的 `foreach/if`：14 个网口信号没有绑定，发送时钟也未创建。该次候选实现已停止，未生成位流。修正为逐项管脚声明和确切层级后，新增 `scripts/assert_pl_preview_constraints.tcl` 在布局前强制检查 15 个精确球位/电平、RX/TX/MDC 时钟、发送口有限的建立/保持约束，检查通过；错误约束不能靠降低告警级别跳过。

MDIO 为 GP100 时钟使能输出，数据只在 MDC 下降沿或空闲起始时改变，PHY 在半周期 250 ns 后采样。不能套用“每 10 ns 改一次 MDIO”的输出时序假设。现对 MDC/MDIO 的物理输出路径分别设置 200 ns 上限，给 PHY 最小 10 ns 建立/保持留出余量；`sim/tb_mdio_clause22.sv` 验证高电平期间数据/输出使能不变化，以及完整半周期的准备窗口。读数据在双级同步后、高电平中间采样，20 ns 官方延迟和额外 62 ns 仿真裕量均通过；62 仍不是手册参数。

YT8521S Table 13 要求复位低电平至少 10 ms；管理工具使用低 20 ms、释放后等待 50 ms。新网口采用官方完整板球位，数据/时钟/管理为 bank13 的 LVCMOS18，RESET 为 LVCMOS33。RGMII 仍含 0.2 ns PCB 偏差预算这一设计假设，尚未测量真实走线偏差。

实现采用 `D:/yzd/tmp/sdi-refclk-fix-20261020/refclk-final.dcp` 参考布局，只固定旧 DDR 物理接口与时钟位置；其他逻辑保留布局自由度。修正流程避免同一次实现重复导入增量参考。共享 Vivado 数据库受只读保护；未改 NPU 1 GHz、原信号球位或厂商库，也未用宽泛假路径处理新链路。现有厂商 1 GHz 最小周期问题仍需独立保留，不能宣称生产时序完全通过。

随后实际布局出现新的局部限制：`Place 30-859/30-365` 指出 RX FIFO 所在时钟区域需要 41 个 BRAM，可用仅 39 个；整片 78% 的利用率不能证明局部放得下。根因是上游 `CLOCK_INPUT_STYLE="BUFR"` 使用区域时钟，把 RX FIFO 限定在已经拥挤的区域。现选上游已有的 `BUFIO` 模式：IDDR 继续用专用 BUFIO，MAC/FIFO 改由 BUFG 驱动，允许在其他区域放置，额外使用一个全局时钟缓冲。中间仅使用 BUFG 的尝试在接受产物前停止，最终选择保留专用 I/O 时钟的分支。更新后的 r3 已完成布局和物理优化，未再出现该局部 BRAM 放置错误；布线因另一项固定走线冲突失败，详见下节。因此尚不能宣称整片实现通过。源尺寸、编码质量、FIFO 深度和 NPU 频率没有因该问题改变。

为验证实际 I/O 分支，`test_xilinx_io.py` 使用当前包装的 `TARGET="XILINX"`，只读引用已安装的 BUFG、BUFIO、IDDR、ODDR 原语模型和 glbl，运行 64×16 的真实编码/MAC 串联仿真：3 帧输入、3 帧完整接收、拒绝/中止 0，JPEG 均可解码；输入散列见 `pipeline-xilinx-io/source-hashes.json`。旧全高清仿真快照仍明确对应修改前的网口包装；小图原语验证不能替代全高清板测或布线时序。

中途停止旧综合主进程后，四个并行工作进程仍持有任务日志，导致一次重启报告日志访问拒绝。核对完整任务目录、父进程和 `SYNTH_DESIGN_PARENT16380_` 标识后，仅清理本任务的残留工作进程，确认日志可独占打开，再启动最终 r4；保留失败日志，没有停止其他工程任务。

## 布线失败定位及 r5 修复验证

r3 的 `place_design` 和 `phys_opt_design` 成功，随后出现 `Route 35-341`：旧 GP/DDR 时钟的固定走线与新增 `U_pl_preview/net_clk` 的时钟脚冲突，最后以 `Route 35-9` / HDRTException 中止。错误检查点仅供诊断，未作为有效 routed 产物。该轮日志及物理优化检查点备份在 `implementation-r3-failed/`，没有覆盖板上 BOOT。

对物理优化检查点单独报告时序，建立余量最差 −4.862 ns，路径从 JPEG 字节 FIFO 的读指针，经大规模分布式 RAM 组合读和 EOF/ready 逻辑，返回编码器；网络 RX 保持余量为 −4.760 ns。它们是布局后的估算，不是最终布线时序。

- `wcis_jpeg_compressor.v` 增加显式 `PIPELINED_FIFO`，连续预览选择已固定版本的 `axis_fifo` 同步 RAM 和两级读流水线。旧 native JPEG 默认继续采用 FWFT 分支，深度保持 4096 字节，溢出仍完整中止当前帧并清空预取状态。
- 新分支和旧分支各通过 7 组仿真，包含多种质量、随机背压、FIFO 绕回、溢出、外部中止、复位和后续恢复；两者成功输出的 JPEG 散列逐项相同，独立解码与系数比对通过。证据 `byte-fifo-pipelined/summary.json`、`byte-fifo-legacy/summary.json`。局部综合 `byte-fifo-ooc-utilization.rpt` 确认该字节 FIFO 用 1 个 RAMB36、36 LUT；局部综合时序不是整片验收。
- 修改后的全高清串联仿真单独保存在 `pipeline-fifo-r5/`，有独立上传源快照。渐变和高噪声仍各为输入/编码/完整接收 3/3、拒绝/中止 0，分别 636 和 3858 个 UDP 包，6 张图片完整解码为 1920×1080；帧间隔约 30 fps。`source-test-pipelined` 另覆盖坏宽度拒绝与下一帧恢复。
- 网络受阻恢复的 Icarus 重跑达到 240 秒主机执行超时，没有当作通过。使用相同生成台架与新 RTL，在隔离 Linux 目录用 Verilator 重做：`pipeline-fifo-r5/recovery/summary.json` 记录输入 4、完整帧 3、拒绝/中止各 1；ARP 恢复后 3 帧全部解码。此项与真实拔网线测试仍不同。
- 接收时序重新使用下一次 DDR 跳变描述：1.95 ns 参考延迟下，将前一跳变的 −3.2…−0.8 ns 整体平移半周期，写为 +0.8…+3.2 ns，保持同一数据眼宽度。原检查点重算仍有约 −0.760 ns 保持余量，说明不能仅修正边沿关系就宣布通过。尝试 IDELAY 的布局估算未找到同时满足两项余量的设置，没有纳入 RTL。
- 当前候选将 PHY RX 延迟从标称 1.95 ns 改为 8×150 ps = 1.20 ns；XDC 对应把两个输入边界同时平移 +0.75 ns，得到 1.55…3.95 ns。该推导依赖寄存器标称步长，0.2 ns PCB 偏差仍是预算，尚未由板测确认，不能冒充厂商对任意设置的独立保证。新配置程序在学校服务器隔离目录 `net-admin-20261024-r2` 交叉编译成功，读回检查值为 A003 掩码内 `0x2000`；源码、二进制散列及 1200 ps 候选值记在 `net-admin-build-receipt.json`，尚未部署。
- 新 `release_pl_preview_routes.tcl` 检查完整层级的叶节点，仅保留 DDR 私有 I/O 走线，不再把共享时钟误认作私有走线。整网解路诊断耗时过长，只停止本任务对应的诊断进程；最终改为释放 22 条共享时钟走线。`check-preview-route-unlock-r2-console.log` 确认解锁及检查点保存成功；后续仅指定少量网络路由的命令被 Vivado 增量模式拒绝，这不是布线通过证据。

包含上述缓冲修改的整片 r5 综合已完成：LUT 55207/78600（70.24%）、BRAM 208.5/265（78.68%）、DSP 79/400、BUFG 24/32、MMCM 5/5、PLL 4/5。与 r4 综合比较，减少 1008 LUT，增加 1 个 BRAM tile；不能据此推算实际帧率或功耗。

r5 已启动实现，复用 r3 成功完成的物理优化检查点作为布局指导，减少重复放置；该检查点没有被当作已部署的参考。实际板端 f6 检查点仍独立用于旧球位、NPU PLL 配置/位置的审计。输入绑定见 `preview-implementation-inputs.json`、布局来源见 `preview-layout-guide.txt`；当前最终布线与时序未验收。打包门槛新增每个 RX 数据输入的有限建立/保持检查，并要求最终余量非负、配置工具与时序合同匹配。没有改变 NPU 频率或安装工具的数据库。

检查实现日志发现 Vivado 2018.3 的增量 `Default` 模式以参考检查点的 −4.862 ns 为优化目标。仅停止已核对命令行与父进程的本任务布局工作进程，将布局和布线指令改为 `Explore`，保留 r5 综合及逻辑优化检查点，从 `place_design` 恢复；停止前日志和输入清单另存 `implementation-r5-default-stopped/`。新日志 `implementation-r5-explore-console.log` 明确记录目标 WNS 为 0 ns，输入清单重新绑定当前约束、脚本、综合和逻辑优化产物。此时仍没有最终布线通过结论。

新 FIFO 的器件 I/O 回归也完成：`pipeline-xilinx-io/summary.json` 使用只读 Xilinx BUFG/BUFIO/IDDR/ODDR 仿真模型，64×16 测试输入/编码/接收均为 3，拒绝和中止为 0。它覆盖当前流水 FIFO 与器件 I/O 封装的组合行为，不代表 1080p 的物理接口或时序验收。

### r5 中止与控制复位修正

r5 的布局、物理优化完成，但布局后最差建立余量仍为 −2.661 ns。`r5-placed-setup.rpt` 定位到 HP200 复位寄存器，经 `reset` 和配置控制组合逻辑，直接驱动 NET150 配置寄存器 CE；两域边沿间隔只有 1.667 ns。`r5-placed-rx.rpt` 另有 RX_CTL 保持 −0.010 ns、RXD0 保持 −0.004 ns；这些仍是布局后报告。整片布线出现拥塞提示，尚未形成最终 routed 结果。确认存在必须修正的源级控制路径后，仅停止核对过进程链的本任务 worker 37596；控制进程正常报失败退出。检查点、日志、原输入绑定和路径报告保存在 `implementation-r5-stopped/`，没有位流或启动文件变更。

`wcis_pl_jpeg_preview.v` 去掉 NET150 配置 bank 条件中的原始 `reset`，保留异步置位、在 NET150 两级释放的 `enable_to_network` 控制；下游共用复位仍直接隔离停用/复位状态，没有增加时序例外。声明顺序也调整为先声明后连接，兼容 Icarus。新增 `sim/tb_pl_preview_control.sv` 与 `scripts/verify_pl_preview_control.py`，12 种复位相位下覆盖默认禁用、不完整配置拒绝、原子配置、快速禁用/重新配置、运行时复位和配置握手中取消，`control-r6/summary.json` 通过。测试真实 CSR、mailbox、顶层控制和 packetizer，PLL、视频源和 PHY 使用明确标注的 stub，不能证明 PLL 或网口电气行为。

网口时序改为先做独立小工程试验，保持实际 RX 球位和 LVCMOS18，逐项检查路由完整性和建立/保持余量。`rx_timing_probe.v` 及 `probe-rx-*.tcl` 均为任务目录的试验，未集成入板级源码，也不生成板级候选。输入数据延迟、全局采样、时钟延迟以及 PLL 相位/补偿的多种设置尚未得到足够余量；其中 kind 2 存在未布通的时钟网络，明确作废，不能仅凭命令完成就计为通过。后续采用厂商表 137 明确的“PHY 不加延迟、输出 skew ±500 ps”合同进一步验证；保留 0.2 ns PCB 预算及原 0.1 ns 用户不确定度，不将标称 150 ps 步长外推成新的保证，也不缩小预算以通过检查。整板下一版本尚未重新综合。

直接 PLL 的最初无 PHY 延迟试验曾显示约 +0.097/+0.098 ns，但路径报告暴露主时钟的用户不确定度未自动传递到 PLL 生成时钟，不能接受这个数值。`probe-rx-pll-vco.tcl` 显式保留生成时钟 0.100 ns 用户不确定度后，最优试验为乘/分频 11、OPTIMIZED、163.636°，全局最小余量仅 +0.014 ns（`rx-probe-pll-vco-input.rpt`）。`r5-pll-locations.txt` 同时证实试验占用的 `PLLE2_ADV_X0Y1` 已是原 PS 包装时钟 PLL 的位置。这不构成可直接整合的候选；未移动旧 PLL、改变旧时钟或忽略额外时钟合同风险。

15:34–15:37 的区域时钟试验 `rx_regional_probe.v` 使用真实 RX 球位、LVCMOS18、BUFIO+BUFR，分别尝试直接时钟、时钟 IDELAY、数据 IDELAY。三种最优全局最小余量分别为 −1.392、−2.066、−0.147 ns，均失败；报告 `rx-regional-{0,1,2}-{route,input,best}.rpt` 保留。后两者包含仅供 STA 的常量 IDELAYCTRL 复位，明确不能用于板级集成。试验均正常退出，不产生板级 bit/BOOT。停止追加试验，按上面的可行性边界与最小发送路线重新评估。

## PS 资源卸载准备

`ps_app/src/wcis_camera_owner.cpp` 新增显式 `pl-preview` 模式：连续预览由外部 PL 接收机提供；PS 不启动连续采帧线程、不创建 VPU 编码器、不提前挂下一帧 DMA。识别请求到来时才采一帧原始 RGB565，保留原模型/PL 预处理调用；仅为这一份识别结果生成一张 960×540 JPEG 缩略图。两个 DMA 缓冲首次使用时分别校验 CPU 映射与 SDK 读回，不跳过所有权与故障隔离检查。旧连续 VPU 模式保留。

`camera_owner_runtime.py` 检查本机程序明确报告支持新模式。`serve_photos.py --camera-pl-preview-url http://<内网接收机>:<端口>` 只转发少量状态 JSON，把浏览器视频/预览请求重定向至接收机，避免整路 JPEG 绕回 PS。若浏览器经远程隧道访问，新增 `--camera-pl-preview-browser-url` 单独指定浏览器可达的地址；PS 状态请求仍访问原内网地址。没有假设校园网客户端能直接访问接收机的 192.168.1.x 地址。`external_preview.py` 对两种地址均限定无凭证的固定内网 IPv4、状态响应 16 KiB 上限和 1 秒超时，不跟随状态重定向。识别结果仍显示自己的采样帧和检测框，不把旧框叠在独立播放的视频帧上。

页面帧率改用实际完成帧计数 `encoded`，避免把被跳过的源帧 ID 差值误算成接收帧率。已有视频独立性、单一在途识别、暂停/单次、过期隐藏和检测框关联回归通过；新增状态适配器 5 个 HTTP 用例通过，覆盖直接视频 URL、尺寸/超大响应拒绝、拒绝状态重定向、来源约束与隧道地址分离。

AArch64 程序在学校服务器独立目录 `D:/yzd/tmp/pl-jpeg-ethernet-1080p-20261023/owner-on-demand-20261024` 交叉编译通过，构建前重新检查工具和现有任务。源码、临时目录、缓存均隔离。产物 `wcis_camera_owner`、`owner-build.log`、`owner-build-receipt.json` 已取回；没有在板上编译模型，也未部署该程序。此阶段不能量化节省的 CPU/VPU 或识别速度变化。

## 接收机真实 UDP/HTTP 负载与限制

`gateway_receiver_load.py`、`replay_udp.cpp` 在 192.168.1.102 的独立任务目录对真实接收程序做回环测试：使用 RTL 捕获中的完整 WJP1 数据，修改连续帧 ID，按原 30 fps 时间戳发送 60 帧，HTTP 客户端实际读取 multipart JPEG 并核对散列。原先仅按截止时间追赶的发送器会产生超过千兆线速的回环突发，不能当成物理链路负载；修正为计算 Ethernet 前导码/FCS/IFG，并限制相邻发送不超过 1 Gbit/s 后再记录有效比较。此测试仍让发送、接收和观看端共享双核主机，不能代替独立摄像头/网口实测。

- 渐变负载：60/60 帧完整接收，HTTP 也收到 60 帧，12720 个包全部收到，内核丢包 0；尺寸一直为 1920×1080。证据 `receiver-load-gradient/summary.json`。
- 高噪声负载：当前程序这次发送 77160 包、收到 72117 包，接收程序通过内核 `SO_RXQ_OVFL` 直接读出该 socket 丢包 5043，与差额一致。60 帧中仅 28 帧完整，HTTP 收到的 28 张均为正确原始 JPEG 散列，没有把残片当成有效图像。该项吞吐门槛失败，不能写成 1080p30 全场景通过。证据 `receiver-load/summary.json`，包括精确软件散列和 CPU 计数。
- 主机 `rmem_max=212992`，申请的 4 MiB 被限制为 `SO_RCVBUF=425984`（Linux 包含倍增记账）；当前用户无法使用 `SO_RCVBUFFORCE`。应用状态新增实际缓冲、是否受限和该 socket 的累计内核丢包计数。没有更改系统全局设置或要求管理员权限。
- 尝试批量 recvmmsg 和缩短线程时间片均未达到无丢帧门槛，已从正式源码撤回，实验留在隔离目录。保留 HTTP 分开发送头/JPEG/结束符，消除每帧拼接大 bytes 的额外复制；这项本身不保证帧率。后续需结合真实相机场景与主机接收缓冲/处理能力决定是否采用更强接收机或原生收包程序。

进一步在任务目录验证了不受 Python GIL 影响的原生线程原型 `native_udp_preview.cpp`，并以原 Python 重组器作为参照，12 项实际 UDP 差分用例通过，覆盖顺序/逆序、重复、重复冲突、中止、新帧取代旧帧、ID 回绕、错误 CRC/会话不破坏当前帧、超长报文、错误 JPEG 几何、超时不复活及后续恢复。证据为 `receiver-load-native/differential.json`、`native-receipt.json`，对应 poll 版本源码和库散列已保存。高噪声同机负载中 poll 版本一次完整收到 53/60 帧，内核丢包 214，接收进程约消耗 0.318 个 CPU 核；blocking 变体仍有丢包。原型虽有改善，仍未满足 60/60 的本轮吞吐门槛，没有纳入正式接收程序或部署。不同发送器优先级/调度变体单独留档，不能据两秒实验宣称确定的速度提升百分比。

新接收器调用的 HTTP 流增加每连接 64 KiB 的请求发送缓冲和 0.5 秒写入超时，发送不畅时释放连接，页面按既有逻辑重新取新帧；未改变旧调用者的默认超时。`tests/test_preview_slow_client.py` 用 4 个停止读数据的真实 TCP 客户端确认先达到观看数上限，随后超时释放，新的观看请求恢复。修改后的正式源码再次通过渐变负载 60/60 的 UDP 与 HTTP 完整帧检查。该保护减少积压风险，不等于已经测量真实浏览器端到端延迟。

等待 r5 实现时，另在隔离原型中把每包 poll/recvmsg 改为最多 64 包的 recvmmsg 批量排空；未修改正式接收器。仅批量收包仍为 51/60、内核丢包 221，不能单独归因于系统调用数量。将测试发送/观看进程和接收进程分配到双核主机的不同 CPU 后，短测为 UDP/HTTP 60/60、77160 包全部接收、内核丢包 0（`receiver-load-native-batch-pin-r5/summary.json`）；修改版本的 12 组协议差分也通过，对应源/库散列已保存。

随后扩展至 600 帧、约 20 秒，高噪声负载完整接收并通过 HTTP 核对 599 帧，771600 包中收到 771565，内核丢包 35；平均接收进程约消耗 0.401 核。缺损的 1 帧未展示，后续正常恢复，无错误 JPEG。证据 `receiver-load-native-batch-pin-600-r5/summary.json`。严格零丢帧检查仍失败；短测 60/60 不能外推为长期零丢包，也不能由回环测试替代真实网口验收。CPU 亲和性只作用于本任务创建的进程，没有修改全局缓冲、其他任务或服务。原型继续留在任务目录，正式服务未切换。

因此，分辨率、PL 编码能力、码率、主机完整帧率和浏览器显示率必须分别验收；已经通过的短时 RTL 仿真不能覆盖上述主机压力失败。

## 当前板端只读检查与后续门槛

`board-readonly-20261024.json` 初次检查记录 boot ID 仍为 `00e85ed6-f66b-4176-ae7a-79d786c552a8`，与现有启动证明一致；证明内 BOOT SHA 为 `f6da96abbc0144ce5a48f4fa85aed6dab65067211b8932e8f4e4db87d5110297`。初次检查仅读取现有证明。随后 `snapshot_current_board.py` 确认当前根分区和 SD 启动分区没有其他挂载，短时只读挂载 `/dev/mmcblk0p1`，实际读取/核对并备份 7023552 字节 BOOT、DTB、uEnv，操作后卸载；实际 BOOT SHA 与证明完全相同，启动文件没有改写。另备份 5 份既有服务/部署配置，没有修改或重启服务。证据为任务目录的 `board-before.json`、`before-BOOT.bin`、`before-config-*`、`snapshot-current-board.log`。

正确绑定地址上的识别健康接口为 ready，旧预览为 960×540、连续采帧/VPU 30 fps 上限。正式防伪状态仍为 `not_evaluated`。

后续仍需最终布局布线与新路径时序/CDC审查、打包前源与位流绑定、保留 PS 分区的 BOOT 校验、定时回滚，然后验证 PHY 身份/电平 strap、千兆链路、真实 SDI 几何、完整图像、长期丢包/延迟以及 FAC1/NPU/图库保持。对仅在仿真中使用的 `192.168.1.114` 做 3 次 ARP 探测，收到了 MAC `da9abd9eac37` 的占用响应，因此拒绝把该地址分配给 PL（`arp-probe-1921681114.json`）。改探测 `192.168.1.240`，3 次未观察到冲突（`arp-probe.json`）；这只是当时的探测结果，不是 DHCP 预留或永久地址准入，目前仍没有使能新网口。新预览跑通后再切换按需采帧模式并测量系统收益。

## 上板事务的离线准备

任务目录新增 `preview_boot_transaction.py`、`board_preview_trial.py`、`prepare_preview_trial.py`。本地打包器要求最终 routed gate、当前 BOOT/bit 载荷核对、PS 分区相同和当前回退脚本测试散列一致，才允许生成本地上传包；它没有 SSH、挂载或重启操作。当前最终时序尚未验收，因此还未生成或上传该试运行包。

板端试运行脚本先设置 600 秒恢复定时器，再停止原预览/识别服务；只有 native owner 明确记录 `stopped`、`sdk_closed=true`、`camera_pending=false`，且无当前 boot 故障标记、无残留 SDK 进程并独占相机/NPU 锁，才替换 BOOT。首轮只换位流，保持原应用，PL 推流仍默认关闭。恢复流程检查已知 BOOT、DTB/uEnv 和两份准入配置版本，恢复原文件与服务启用状态后重启；配置半更新、普通写入失败或复制损坏均保留可追查的状态。不会覆盖未知的启动文件或配置版本。

`test_preview_boot_transaction.py` 和 `test_board_preview_trial.py` 在隔离 Linux 临时目录共 23 项通过，覆盖复制失败/损坏、写完但目录同步失败、配置第二项失败、未知文件拒绝、混合状态恢复、先启用恢复定时器后停服务、SDK 退出不干净禁止替换以及停止服务超时后的文件恢复。证据 `boot-transaction-linux-tests.log`、`boot-transaction-tests.json`，记录测试源散列。测试替换了系统操作入口，没有访问板卡、真实启动分区或执行重启；不是已经完成一次板端回滚。回退定时器依赖 Linux 正常启动，不能覆盖启动前故障或断电造成的 FAT 损坏，SD 读卡器恢复仍是最后手段。
