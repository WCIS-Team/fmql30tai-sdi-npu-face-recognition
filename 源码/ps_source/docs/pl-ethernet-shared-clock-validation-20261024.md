# PL 网口共用高速时钟发送验证（2026-10-24）

后续进展见 [整合准备记录](pl-jpeg-tx-integration-preparation-20261024.md)。本文保留独立探针完成时的证据与边界；下文“尚未切换”描述的是当时状态。

## 当前结论

**新的独立发送模块完成最终布线，时序门槛通过；尚未进行整板集成、生成新 bit/BOOT 或上板。** 本轮接续 PHY 延迟候选的工作，用户要求继续，期间询问手册是否说明使用方法。手册给出了接口、寄存器和原语用法，不能由某种接法未过时序推断网口硬件不可用。本轮改用 FPGA 内部生成时钟错位的结构，不再将所选 PHY 追加 TX 延迟的最坏边界作为该候选的前置条件。

本轮沿用原有真实 TX 球位、LVCMOS18、DRIVE8、FAST、0.100 ns 用户时钟不确定度，以及 PHY 接收端双边沿 +1.2/−1.2 ns 要求（原 1 ns 要求加 0.2 ns PCB 偏差预算，预算仍是设计假设）。没有修改 NPU/DDR 时钟、已有板级信号球位或工具时序数据库；没有配置真实 PHY 或改变板端服务。

## 结构及依据

- 新增 `rtl/wcis_rgmii_tx_serdes.v`：5 个数据/控制串化器和 1 个转发时钟串化器，全部使用同一条 250 MHz 串行时钟及相位对齐的 125 MHz 并行时钟。
- 每个 8 ns 周期，数据串化图样为 `低半字节、低半字节、高半字节、高半字节`；时钟图样为 `0、1、1、0`。由此产生正常 RGMII 的两次数据传输，并在理想波形中形成 2 ns 的采样错位。PHY 的追加 TX 延迟配置应关闭。
- 使用 OSERDESE2 的 4:1 DDR 模式，`DATA_RATE_TQ="DDR" / TRISTATE_WIDTH=4`，遵循 AMD 2018 年 UG471 v1.10 Table 3-8 的组合；CLK 和 CLKDIV 来自同一 PLL，均经 BUFG。独立探针保持 PLL 位置 X1Y1、VCO/150/125 MHz 参数，原预览的 125 MHz +90° 输出改为同相 250 MHz 输出，不增加 PLL/MMCM。
- 原工程 2026-10-15 的 routed 利用率报告已有 112 个 OSERDESE2，仅作为该工具流支持此原语的历史旁证；不是新候选已部署的证据。
- `wcis_jpeg_network_tx.v` 新增默认关闭的 `USE_SERDES_TX=0` 及只供该候选使用的 `gtx_clk250`。默认 ODDR 模式及此前 PHY 延迟实验模式保留；同时选择 SERDES 与 PHY 追加延迟时拒绝报头提交。没有修改固定上游协议/MAC 源码。

官方来源为 [UG471 v1.10（2018-05-08）](https://docs.amd.com/api/khub/documents/IbGcnPFe6eF19RHma_Y~IA/content)，本地保存 `D:/yzd/tmp/rgmii-shared-clock-tx-20261024/ug471-v1.10.pdf`，SHA256 为 `187298d2c8072595f00e433fab42082c0ced0ae0e2fd60599188d1cc9dc5788e`。第 166 页已用 Poppler 渲染并目视核对。本结构是依据官方原语构造并验证的新候选，不冒称取得了悟净板厂商完整网口参考工程。

## 功能验证

最初 Icarus 无法展开已安装 OSERDESE2 模型所依赖的 `B_OSERDESE2`，该次编译失败保留，没有添加行为 stub 冒充厂商模型。随后使用现有 Vivado 2018.3 的 xvlog/xelab/xsim、`unisims_ver` 和 `secureip` 原生库，通过完整 17 个报文测试。

`scripts/verify_pl_jpeg_tx.py` 的 `--serdes-tx --xilinx` 自动采用上述原生仿真，普通模式继续采用原 Icarus 流程。测试本副本只替换 TARGET/模式参数，实际编译副本、原始台架与 RTL 散列均保留；XSim 必须出现目标台架的 PASS，不能仅依据进程退出码判断成功。

17 个报文覆盖零/广播下一跳拒绝、1/17/1440/1472 字节负载、连续大包和背压、中途复位、变更目标 MAC 后恢复。Python 独立检查完整载荷、Ethernet FCS、IPv4 校验和及非零 UDP 校验和；台架在理想波形的两个接收采样边沿检查至少 1 ns 的建立/保持窗口。该功能模型本身不提供布线或 PVT 证明。

原默认模式 SIM、原默认模式 Xilinx ODDR、PHY 延迟模式 Xilinx ODDR 各 17 个报文回归通过。另用原默认发送模式串联真实采集桥/JPEG/分片/MAC，在 256×64 台架输入并接收 3 张 JPEG、9 个 UDP，拒绝/中止为 0，接收 JPEG 解码通过。此回归用于兼容性，不冒充新 SERDES 路线的 1080p 串联或板测结果。

## 实现过程与问题修正

1. 独立探针使用固定六个真实 TX 球位，参考时钟/reset 是明确标注的合成台架输入。第一次综合后，脚本按斜杠查找生成层级失败，停止于约束加载；实际生成层级使用点号。改为按原语类型与实例名唯一定位 CLK，并保存综合检查点。此次多做了一次小模块综合，没有进行整板重编。
2. 第二次综合、布局和物理优化完成。初次生成时钟使用 250 MHz 的 `{2 4 6}` 边沿，理想波形正确，但 Vivado 没有建立其源时钟路径：报告 DCD 为 0，`check_timing` 明确指出 1 个生成时钟未连接到源。由此出现的 −5.788 ns 不能作为结构本身失败的可靠结论，该次在布线前停止。
3. 复用已保存的布局检查点，对同一理想波形改用正主边沿 `{1 3 5}` 加统一 `-edge_shift {2 2 2}`。最终仍为 8 ns 周期、上升/下降边沿 2/6 ns，外部要求和用户不确定度不变。工具恢复真实时钟路径，生成时钟未连接数归零。两次辅助诊断还分别因旧版 Tcl 的可选报告语法和不存在的删除时钟命令停止；日志保留，修正后以同名定义覆盖旧时钟，没有重新综合/布局或降级告警。
4. 原生 XSim 的稳态采样核对到转发时钟相对 250 MHz 时钟的正确半周期位置；约束修正是恢复该波形的源延迟关系，不是挪动输出相位以改善报告。依据包括 [create_generated_clock 的边沿/edge_shift 定义](https://docs.amd.com/r/en-US/ug835-vivado-tcl-commands/create_generated_clock)及 [生成时钟延迟关系](https://docs.amd.com/r/2021.2-English/ug903-vivado-using-constraints/Clock-Latency)；后者为较新版说明，实际能力以本次 2018.3 的报告为准。
5. 从修正时钟后的既有布局检查点只执行一次完整布线；没有重新综合或布局。`resume_route.tcl` 在布线前后检查源时钟关联，逐根检查 5 个输出的建立/保持路径，保留既有 FIFO/同步器的有限跨域约束，未增加输出假路径。

## 最终独立探针结果

| 指标 | 结果 | 边界 |
| --- | ---: | --- |
| 可布线网络 | 1824 / 1824 完全布通 | 路由错误 0 |
| 全局最差建立余量 | +0.326 ns | 独立探针，不是整板 |
| 全局最差保持余量 | +0.034 ns | 位于 MAC CRC 寄存器之间，余量较小 |
| TX 数据/控制端口最差建立余量 | +0.326 ns | 5 个输出均有有限检查 |
| TX 数据/控制端口最差保持余量 | +0.351 ns | 不能与全局 0.034 ns 混淆 |
| 最差脉宽余量 | +1.100 ns | 该探针不含原 NPU 1 GHz 域 |
| 未连接到源的生成时钟 | 0 | 没有用手填内部时钟延迟掩盖问题 |
| 资源 | 955 LUT、936 FF、2.5 BRAM tile、6 OSERDESE2、1 PLL、5 BUFG | 包含常量配置/测试驱动，不能外推整板实际用量 |

最终 `timing.rpt` 显示 0 个建立/保持/脉宽失败端点；FIFO 总线偏差报告无违规。上述全局保持余量较小，整板集成、不同布局或时钟走线后必须重新验证，不能把独立结果当作整板必然通过。

DRC 保留 `UCIO-1`（合成参考时钟/reset 未绑实板球位）和 `ZPS7-1`（独立探针没有 PS7），未降低级别。该探针**不是可以装板的设计**，没有生成 bit 或 BOOT。200 MHz 合成参考也不能替代真实整板 HP200 来源与时钟树。实际 PHY 设置、真实电缆、千兆协商、SDI 实拍、长时丢包及浏览器帧率都未在本轮验证。

## 后续整板工作

独立 TX 门槛已有通过依据，下一步可准备单向发送的整板候选：接入完整 SDI JPEG 流、以默认禁用方式原子提交实际下一跳 MAC、将预览 PLL 输出替换为该候选时钟，并更新约束/审核脚本。需要保留现役 FAC1/JPG1 页、原 NPU/DDR 时钟和现有回退路径；不能直接把独立探针装板。

当前 `wcis_pl_jpeg_preview.v` 仍是原完整收发/动态 ARP 结构，尚未切换到此 TX-only 模块。固定下一跳 MAC 的配置接口和管理工具还未接入；不能复用旧 ARP 字段冒充 MAC 配置。整板实现仍须单独通过时序/CDC/资源及源文件绑定检查，才考虑可恢复部署。现有 D12 百兆网络也不满足此固定千兆发送候选的实网验收条件，需要届时准备实际千兆接收路径。

## 证据及归档

- 项目改动：`rtl/wcis_rgmii_tx_serdes.v`、`rtl/wcis_jpeg_network_tx.v`、`sim/tb_jpeg_network_tx.sv`、`scripts/verify_pl_jpeg_tx.py`。
- 任务目录：`D:/yzd/tmp/rgmii-shared-clock-tx-20261024`。`before/` 与 `before-sha256.json` 保留本轮改动前三份源文件；`probe*.log`、`diagnose-clock*.log`、`route-console.log` 分别保留失败与成功阶段。
- `simulation-final/summary.json` 为最终原生仿真结果，`phase-query.log` 为稳态相位查询；早期 `native-simulation/` 是修改三态参数前的历史仿真，不能替代最终结果。
- `physical/positive-master.dcp` 为修正时钟后的布局检查点，`physical/routed.dcp` 为此次最终路由结果。`probe.tcl` 已修正为规范时钟描述，但本次路由实际复用的是已保存布局，不冒称已从修正后的完整脚本重新综合复现。
- `physical/timing.rpt`、`tx-io-timing.rpt`、`route.rpt`、`clocks.rpt`、`final-check.rpt`、`bus-skew.rpt`、`drc.rpt` 为准入依据。
- `audit_result.py` 校验当前源码与仿真记录散列、输出所有有限时序路径、完整布线和生成时钟关联；`result.json` 绑定关键源、脚本、检查点、报告与官方资料 SHA256。`independent_timing_probe_passed=true`、`full_board_accepted=false`、`board_verified=false`。
- 按聊天日期同步归档到 `D:/bigfuture/竞赛/记录/2026-10-24.md`，保留原始文件与当日其他记录。
