# PL JPEG 单向发送整板验证（2026-10-25）

## 工作范围与日期

继续 [2026-10-24 整合准备](pl-jpeg-tx-integration-preparation-20261024.md)，在同一独立任务目录 `D:/yzd/tmp/pl-jpeg-tx-integration-20261024` 完成离线整板实现检查。目录日期沿用任务开始日；本记录及归档日期按本次工作日 2026-10-25。没有连接板子、配置真实 PHY、写启动分区或重启服务。

候选链路是 SDI 1920×1080 原图分支 → PL JPEG → WJP1/UDP/IPv4/MAC → 共用 250/125 MHz 时钟的单向 RGMII 发送。PS 工具只管理配置，不搬运原始预览帧。默认关闭，NTP2 配置与旧工具隔离；识别的原图/DDR、FAC1/JPG1 和原 NPU 时钟配置保留，尚须路由后对照原设计核实。

## 中断恢复及已完成检查

前一轮只有 RTL 综合结束日志，缺少写出的全顶层 DCP，因此没有冒充完整综合成功。重新执行综合并复用已经生成的 IP 产物；本轮 `synthesis-recovery.log` 出现完整检查点写出及 `FULL PREVIEW SYNTHESIS COMPLETE`，任务保存 `preview-full-synthesis.dcp`。恢复时没有重复控制回归及学校服务器交叉编译；串联仿真后因新发现的台架相位问题补跑一次，详见下文。

综合报告 `preview-full-synthesis-utilization.rpt` 为全设计估算：54,343 LUT（69.14%）、72,195 寄存器（45.93%）、207 BRAM tile（78.11%）、79 DSP（19.75%）、23 BUFG、5/5 MMCM、4/5 PLL。不能当作布线后实际资源或帧率。厂商原工程的约束/黑盒警告仍存在，没有新增降低告警级别的设置。

整板逻辑优化后，约束检查通过：9 个新网口球位/电平逐一匹配，六个 OSERDESE2 存在，250 MHz 主时钟正确，5 个数据/控制输出都有有限的建立/保持路径。使用 `fmql30tai_pl_ethernet_tx.xdc`，未沿用旧 RX 路径约束，也未放宽输出要求。

原部署参考 `D:/yzd/tmp/sdi-refclk-fix-20261020/refclk-final.dcp` 只作为布局引导及独立审核基准，其载入信息自身报告 WNS −0.031 ns、WHS +0.002 ns；不能据此声称新的整板已过时序。原 DDR 物理接口及既有时钟位置固定，其余控制逻辑允许为新增链路重新安排。布局脚本在检查时序前保存 `preview-placed.dcp`，避免诊断脚本错误导致丢失布局成果；执行前更新了此保存点脚本的绑定，初版输入清单保留为 `preview-implementation-inputs-launch.json`。

## 复用验证的边界

`recheck_baseline_1080.py` 首先核对旧 `pipeline-fifo-r5/pipeline-gradient/summary.json` 中记录的全部源码散列与当前源码一致，再把旧捕获数据复制到本任务 `reused-baseline-1080` 重新解码检查。收到 3 张 1920×1080 JPEG、636 个 UDP；原来源数据和报告没有改动。

该旧仿真使用原收发/ARP MAC，因此只用作未变的采集、JPEG、WJP1 全尺寸几何验证，不能声称新串化器已跑过 1080p 整链仿真。新串化器的真实原生模型串联验证仍以 2026-10-24 的 256×64、3 张 JPEG/9 个 UDP 为范围；两个证据层次分别保留。仿真时间间隔不是板端或浏览器帧率。

本轮复查发现新串联台架中 250 MHz 首个上升沿为 2 ns，125 MHz 为 4 ns，未按整板同相 PLL 的关系对齐。原 17 报文发送器台架已将两个首个上升沿对齐到 4 ns；无需重复该项。修正 `tb_pl_preview_pipeline_tx.sv` 的 250 MHz 起始相位后，`pipeline-native-aligned/summary.json` 再次通过：输入 3 帧，得到 3 张 JPEG/9 个 UDP，拒帧/中止为 0，完整 CRC/校验和、解码与像素核对通过。后续整合结果绑定该新报告；先前 `pipeline-native-fixed` 只保留作历史过程。此修改限于台架，不改变整板 RTL 或重做综合/布局。

## 当前物理实现状态

第一轮布局完成，门槛正确停止于布线前。布局估算的全局 WNS −4.577 ns、WHS −2.480 ns；新增预览最差建立路径为分片 `position_reg[0]` → UDP `checksum_reg_reg[16]`，−3.574 ns。该路径要求 6.667 ns，数据延迟 10.005 ns，其中连线 8.908 ns（89.035%），组合逻辑 13 级。整板网口输出的建立检查最差 +0.306 ns，不能把内部长路径失败说成串化器引脚已经失败，也不能把这一布局结果冒充最终布线时序。

保存 `preview-placed.dcp` 后复用此检查点，释放继承的共享时钟/普通逻辑走线，仅保留原 DDR 专用物理连线及既有 I/O/时钟位置，再执行一次物理优化。没有重新综合/布局。优化后的全局 WNS −2.646 ns；关键路径仍是分片位置寄存器副本 → UDP 校验累加。`preview-refined.dcp`、`preview-refined-timing.rpt` 和 `preview-refinement-gate.txt` 保留结果：新增路径 from/max −2.634 ns、to/max −2.646 ns、保持 −0.137 ns。该轮没有执行 route 或生成 bit/BOOT。`frozen-inputs/` 与 `integration-result.json` 绑定第一轮实际使用的源码及报告，避免后续改码与旧结果混淆。

最终仍要求完整路由、非负建立/保持余量、CDC/总线偏差检查、DDR 校准驱动、原引脚和 NPU 时钟对照审核；第一轮没有通过这些整板门槛。

## 第二轮：切断已定位的组合路径

新增 `wcis_udp_payload_pipe.v`，复用原已固定版本的 MIT 上游 `axis_fifo`：16 字节、注册读口、byte/last 一起传递、满时背压，不丢帧、不旁路。插在分片数据与 UDP 校验器之间，头部握手和协议字段保持原接口；不改编码器、分辨率、NPU 频率或 PHY 外部时序要求。该小缓冲不是整帧队列。

任务独立放在 `D:/yzd/tmp/pl-jpeg-tx-pipeline-20261025`。新控制回归通过 12 个复位相位；`tx-pipe-native/summary.json` 原生串化器模型通过 17 个报文，覆盖背压、中途复位和变更目标地址后恢复；`pipeline-native/summary.json` 真实 JPEG 串联再次收到 3 张 256×64 JPEG、9 个 UDP，拒帧/中止为 0。它们是新缓冲的功能验证，不是物理时序证明。

第二轮完整综合检查点已生成。综合估算 54,364 LUT、72,225 寄存器、207 BRAM tile、79 DSP；相对第一轮增加 21 LUT/30 寄存器，BRAM/DSP 不变。逻辑优化后的结构检查实际通过，找到 46 个缓冲/存储寄存器，原位置寄存器的组合扇出不再直接到达校验寄存器 D；这是检查组合拓扑，不依赖时序假路径。

准备脚本支持从上一轮任务复制已完成的 IP 产物，复制后逐项重写候选项目路径，并重建顶层；厂商综合前 hook 仍会触发 MIG 的重建，日志如实保留，没有绕过厂商补丁。上一轮优化后的检查点只用作布局引导，原 f6 检查点仍独立用于引脚/NPU 时钟审核。

第二轮布局完成后，新增预览最差建立余量改善为 −1.832 ns，门槛仍停止于 route 前。原分片到校验器的组合路径已切断；最差点转为像素 FIFO 的帧号比较 → JPEG 取消/有效信号 → 分片 RAM 写使能，数据延迟 7.815 ns，其中连线 6.311 ns，逻辑 12 级。不能简单延迟取消信号来隐藏这条路径，否则需要额外证明坏像素和帧尾不会先被接受。

2026-10-25 后续恢复前重新核对源码/仿真/构建散列全部一致，且没有遗留 CAD 进程。从第二轮 `preview-placed.dcp` 直接继续物理优化，既未重做综合/布局，也未修改 RTL。`preview-refinement-gate.txt` 得到新增预览建立 +0.055 ns、保持 −0.319 ns；全局建立 −0.487 ns。生成时钟未连接数为 0。建立已转正，但保持及全局尚不能算通过最终时序。

在原有 −0.5 ns 布线前门槛内启动本任务第一次完整 `route_design -directive Explore`。`route_refined.tcl` 使用已优化检查点，保存原始路由结果后按原工作目录调用未修改的厂商 route-post hook，再输出最终报告；不伪造原工程 run 的完成状态。共享时钟走线若已在上一轮清理，清理脚本允许明确的空操作，但仍检查专用 DDR 连线所有权；未取消任何时序要求，初版输入绑定和实际执行版本分别保留。

本次完整布线已完成。Explore 算法内部经历多次全局重排及一次自动布局调整，不是重新综合或手动重复整板构建。最终 `preview-route-status.rpt` 为 116,613/116,613 个可布线网络全部连接，布线错误为 0；不能把连通性通过当作时序通过。

最终全局建立 WNS −1.218 ns（1,251 个失败端点），保持 WHS +0.029 ns（0 个失败端点）。新预览路径建立最差 −0.792 ns，保持 +0.059 ns；5 个 RGMII 数据/控制引脚的最差建立 +0.326 ns、保持 +0.351 ns。因此串化器外部发送时序通过，内部及整板建立时序仍失败。原 NPU 1 GHz 的两项脉宽失败仍为 −0.409 ns，没有改频或用新豁免掩盖。没有生成 bit/BOOT，没有连接或更换板端镜像。

## 布线后定位与局部时钟诊断

全局最差路径位于原 `frame_to_ps_inst0`，时钟偏斜 −2.814 ns：`cam_clk_inferred_i_1` LUT3 输出经普通连线分发到 2,064 个时钟负载。同一时钟从 LUT 到发射端的连线为 4.139 ns，到捕获端为 1.309 ns。候选 `case/rtl/sdi/rx_sdi.v` 和只读原厂案例均存在 `assign cam_clk = rx0_locked ? rx_usrclk : sys_clk_200m;`，因此是原案例已有的普通逻辑时钟选择，而非新 JPEG/网口分支新增。新预览使用独立的原始 `sdi_rx_clk=rx_usrclk`。

`diagnose_camera_clock.tcl` 已核实 BUFG 原语和空闲专用缓冲位置。第一次只读诊断误用了此 Vivado Tcl 不支持的 `redirect` 命令，未改设计；改为普通报告后完成检查。

`camera_buffer_eco.tcl` 的独立子目录试验已完成：在原时钟选择 LUT 后只加一个 BUFG（空闲 `BUFGCTRL_X0Y23`），精确保留 2,064 个负载、原 141,145 个原语的类型/位置/BEL 及端口配置，只重布两条相关网络。`camera-buffer-eco-v4.log` 实际局部路由约 69 秒，116,614/116,614 个网络已连接、错误 0。原最差路径建立改善为 +1.317 ns，时钟偏斜由 −2.814 ns 降至 −0.279 ns。

但局部修复并未通过整板验收：全局建立 −1.210 ns、保持 −2.130 ns（136 个保持失败端点），新预览仍为 −0.792/+0.059 ns。新的保持最差点是原始 RX 时钟驱动的 RGB 数据到缓冲后摄像头时钟驱动的 `rate_gate/m_data_reg`，新增时钟插入延迟改变了两者关系；不能只看原最差路径转正就宣布成功。原检查点、候选源 RTL、NPU 参数及所有时序要求未改，实验不准打包或部署。缓冲也不能证明原异步时钟切换无毛刺。

局部脚本调试中的失败分别为误以 `FIXED_ROUTE` 字符串非空判定固定路由（改为检查真实 `IS_ROUTE_FIXED`）、逐器件字典检查过慢（只停止本任务诊断，改为原对象集合属性向量比较），以及此版本 `-preserve` 不能与其他路由选项合用（保留 `-nets` 的两网络限定）。这些诊断没有重新综合或重跑整板路由，均发生在实验副本；`camera-buffer-placed.dcp` 额外保留局部走线前检查点。

`prepare_camera_buffer_evidence.py` 生成源/DCP/脚本/报告散列及 `rx_sdi-buffer-equivalent-unsynthesized.v` 解释性副本，明确标注未综合该 RTL 副本、未签核、未上板。从实验已布线 DCP 执行一次 `ExploreWithAggressiveHoldFix` 路由后物理优化，约 9 分 22 秒完成：全局建立 −0.590 ns（982 个失败端点）、保持 +0.003 ns（0 个失败端点），116,635/116,635 网络连接、错误 0。优化器重新安排部分原控制器的位置/连线并插入 14 个保持修复缓冲；“原器件位置不变”的核对只适用于前一单 BUFG 实验，不适用于这次物理优化。

`structural-diagnosis/preview-routed-audit.txt` 完成全部 9 组邮箱、DDR 校准驱动、274 个原端口球位/电平及原 NPU PLL 配置/位置对照。邮箱和 10 项网口输出检查通过，生成时钟源没有失联；NPU PLL 仍为 `5.000 1 5 1 0.000 PLLE2_ADV_X1Y3`，未降频。仅新增预览的 from/max、to/max 两项局部路径检查仍为 −0.590 ns，因此诊断按设计以错误退出，未输出生产验收通过标记。现有两项 NPU 脉宽失败亦未消除。

随后明确选出 6 条 354–365 负载的分片计数器数据网，调用工具的强制复制选项；Vivado 2018.3 返回 `Option -force_replication_on_nets ... not supported yet for post-route physical synthesis`，没有修改设计或输出新 DCP。没有为此盲目重跑整板路由，改为重构分片 RAM，详见 [同步 RAM 分片缓冲](pl-jpeg-bram-chunk-20261025.md)。旧任务的 `frozen-inputs/`、`frozen-inputs.json` 和历史结果解析器保存实际已综合/仿真的旧源，避免新源码被当作旧物理结果的依据。

预览域的当前最差路径已转为分片 `count_reg[0]` 到分片分布式 RAM 写地址。先复用当前路由检查局部物理优化的效果，未无证据地重复整板构建。

`package_pl_preview.py` 已适配 NTP2 候选，只在对应学校服务器构建收据、源/二进制散列和完整路由审核一致时准备后续打包脚本。现有 NPU 1 GHz 脉宽问题必须单列报告，不能把保留原参数写成生产时序签核。当前没有新 bit/BOOT，也没有板端验收。

## 本地来源与归档

关键来源：上述任务的综合/实现日志、`preview-staging.json`、`preview-implementation-inputs*.json`、控制/原生仿真结果、`school-manager/receipt.json` 和 `reused-baseline-1080/summary.json`。实现入口为 `scripts/implement_pl_jpeg_preview.tcl`，检查入口为 `scripts/assert_pl_preview_constraints.tcl`、`gate_pl_preview_placement.tcl`、`audit_pl_preview_tx_routed.tcl`、`package_pl_preview.py`。

本记录同步到 `D:/bigfuture/竞赛/记录/2026-10-25.md`，与 2026-10-24 的准备记录分开保存，保留原始来源及当日其他记录。
