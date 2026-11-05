# PL 网口参考案例与发送时序复核（2026-10-24）

## 本轮结论

本轮获准先寻找可复用案例，对照当前 PL 网口发送时序失败点，再决定实现方向。已读取项目规则、`D:/xiangmuwendang/WCIS-FPAI/wiki/README.md`、完整板手册摘录、现有 RTL/约束与独立 TX 布线报告，并查询原作者代码和厂商文档。背景信息来自本地文档，本轮没有登录网站或声称读取站点最新后台。

有可复用的协议/MAC 源码和 7 系列物理接口参考；在本次有限搜索范围内，**没有取得同时匹配悟净完整版、YT8521、1.8 V、当前时钟资源及本工具环境，并附完整时序通过证据的工程**。不能由此断言厂商没有案例，也不能说所有 PL 网口方案均不可行。

当前 ODDR 数据输出、+90° 转发时钟的结构并非没有参考依据。AMD 官方 7 系列 HR I/O 路线采用相同基本结构；替换整个 UDP/MAC 协议栈不能自动消除当前 I/O 时序违规。本轮没有修改正式 RTL/电气设置、运行综合或布局布线、连接板卡、生成/部署 bit 或 BOOT，也没有实现展示网络配置。

## 参考案例与适用边界

| 来源 | 可复用内容 | 与本项目的差异或限制 | 本轮决定 |
| --- | --- | --- | --- |
| alexforencich/verilog-ethernet，固定提交 `77320a9471d19c7dd383914bc049e02d9f4f1ffb`，Nexys Video 示例 | UDP/IP、MAC、帧 FIFO、ODDR/IDDR 封装；本项目已经复用这些核心 | 示例为 `xc7a200tsbg484-1`、LVCMOS25/DRIVE16、MMCM；RX 用 BUFR。当前完整板为兼容代理 `xc7z030ffg676-2`、LVCMOS18/DRIVE8、PLL，且整板时钟/区域资源受限 | 保留协议核心；不复制外板引脚、电平或驱动强度，也不重新引入已导致局部 BRAM 问题的 RX 区域限制 |
| AMD PG051 v9.0，7 系列 HR I/O 发送逻辑与共享逻辑 | 数据/控制使用 125 MHz，转发时钟使用同源 +90° 时钟，通过 ODDR 输出；区分 HR 与 HP 接法 | 当前网页修订为 2024-12-11；v9.0 修订历史包含 2018 年条目，但这不证明网页全部内容与已安装 2018.3 输出逐字一致。更不能等同复旦微兼容目标的时序保证 | 作为结构依据，不能当作本板已通过的约束/网表 |
| Linux v6.12 Motorcomm 驱动与官方 PHY 文档 | 同一 YT8521 系列的 TX/RX 内部延迟配置、寄存器掩码与延迟归属 | 软件能设置延迟，不等于给出了本板走线偏差或任意配置的全温压延迟保证 | 用于评估由 PHY 提供 TX 延迟的候选；不直接更改现役寄存器 |
| Enclustra GigabitEthernetAppNote，GMII to RGMII | 延迟归属、时钟与接口预算的说明 | 原文明确所提供网表仅用于 UltraScale+，不能替换本项目的 7 系列兼容实现 | 排除直接移植网表 |
| 本地 JFM_Kits 中 `tri_mode_ethernet_mac_v9_0_rfs.v/.vhd` | 证明工具包包含该 IP 的支持文件 | 支持库不是板级示例工程，不能证明已配套授权、可正常生成，或当前球位/时序通过 | 不将其当作现成已验证网口工程 |

上游 `README.md` 已标记项目停更并指向 Taxi；本轮只读核对固定版本，没有迁移到后继项目。AMD 官方说明 TEMAC 完整功能涉及 IP 授权，评估或超时许可证可能存在；本轮未检查当前机器的 TEMAC 授权，不能把工具目录中存在文件等同可长期部署。继续使用现有 MIT 协议/MAC 核无须因为本次参考查询改成 TEMAC。

本轮读取 Nexys Video 的 `fpga.xdc`、`eth.xdc` 及 MAC 实例。前两份中没有该外部 RGMII 数据接口的 `set_input_delay`/`set_output_delay` 时序合同；`eth.xdc` 仅设置接收 IDELAY 值。MAC 内部同步约束是另一回事。**不能以复制示例后报告较好看为由，删除本项目的外部建立/保持时间要求。** 这只描述检查到的文件范围，不将其扩写成上游所有示例均无约束或均未验证。

## 与当前布线报告的对照

现有独立 TX 探针对应 `D:/yzd/tmp/pl-jpeg-ethernet-1080p-20261023/tx-only/physical/`。报告中 5 个数据/控制输出的建立、保持检查共 10 条路径均被复核；最差建立为 TXD1，最差保持为 TXD3，均为 Fast corner：

| 项目 | 当前值 | 证据含义 |
| --- | ---: | --- |
| 最差建立余量 | −0.061 ns | 未通过 |
| 最差保持余量 | −0.036 ns | 未通过 |
| 输出要求 | +1.2 / −1.2 ns，DDR 双边沿 | 原 PHY 1 ns 要求加 0.2 ns PCB 偏差预算，预算仍为假设 |
| 路径时钟不确定度 | 0.278 ns | 报告包含抖动、PLL 相位误差和 0.100 ns 用户不确定度，不能随意清零 |

在**固定布线延迟、固定不确定度、固定 DDR 边沿关系**的小幅相位平移模型中，令转发捕获时钟后移 δ：

```text
setup(δ) = -0.061 + δ
hold(δ)  = -0.036 - δ
setup >= 0 需要 δ >= +0.061 ns
hold  >= 0 需要 δ <= -0.036 ns
```

两项没有共同可行区间，区间相差 0.097 ns。这个算术说明：对该快照仅调整统一发送时钟相位，无法同时消除两项违规。它不是新 STA 运行，不表示改变结构、实际布线或已验证的接收端合同后仍必然失败；也不是对任意相位/采样边沿组合的穷举证明。本轮没有继续扫 PLL 参数或重新跑整板。

本次复核程序 `D:/yzd/tmp/pl-ethernet-reference-review-20261024/audit_reference.py` 成功解析上述 10 条路径，核对案例差异并生成 `audit.json`，绑定 13 份输入的 SHA256。它读取既有证据，不连接硬件、不调用 CAD，不产生新的时序通过结果。

## 下一候选及进入实现前的条件

建议保持已有 JPEG、分片和协议核心，优先评估：**数据与转发时钟共用同相 125 MHz，由 YT8521 提供发送内部延迟**。这是有官方 PHY 配置依据的另一种延迟归属，可能减少两路 FPGA 时钟之间的相位/偏差问题；性能或时序收益尚未验证，不能承诺一定通过。

Linux 官方文档建议在条件允许时优先由 PHY 提供 RGMII 延迟，并要求 MAC/PHY 不重复加延迟。v6.12 `ytphy_rgmii_clk_delay_config()` 明确处理 RGMII、TXID、RXID、ID 四种配置，并在 TXID/ID 中写入 GE TX delay 字段，默认配置映射到 1950 ps。这个值是配置依据，不能直接当作无误差的实测延迟。

进入一次新的独立物理验证前，必须先补齐或核实：

1. PHY 具体型号/修订、所选内部 TX 延迟下的外部输入时序保证及适用条件。现有 YT8521S 手册 Table 138 的 1 ns 要求不应在没有依据时改写成更宽松的边界；可编程 150 ps 步长不是任意延迟值的最大/最小保证。
2. 保留既定球位、1.8 V 和原 NPU/DDR 时钟，给出时钟/数据 PCB 偏差预算。尚无走线实测，不能把 0.2 ns 假设当作事实。
3. FPGA 的转发时钟、管理工具的 PHY 配置、时序合同与配置读回使用同一份候选定义；不得只改约束或只写 PHY 寄存器。需验证双边沿及每一根 TXD/TX_CTL。
4. 只有独立路由/时序门槛通过后，才考虑一次整板集成和可恢复上板。该候选仍是固定下一跳的单向 UDP，保留重配 MAC、接收端网络变化等限制，不等于重新解决 RX/动态 ARP。

如果无法取得足够的 PHY 时序依据，则保持当前候选未通过状态，评估已讨论的 PL 编码→PS 网口搬运方案；不要继续用没有依据的相位/延迟参数换取报告通过。这个替代方案尚未完成当前 SDI 流式集成或节省占用测量。

后续实网验收需要实际千兆接收路径。已定位的 D12 百兆端口是独立带宽限制；更换网络不会修复 FPGA I/O 时序，时序通过也不等于真实网线下零丢包。102 无须成为视频接收机。

## 来源与归档

- 板卡管脚/PHY：`D:/xiangmuwendang/WCIS-FPAI/wiki/PS/board_extract/41_manual_full_extracted.txt`，PDF 第 19–20 页对应摘录。
- 本项目状态：`pl-jpeg-ethernet-validation-20261024.md`；RTL `rtl/wcis_jpeg_network_tx.v`；约束 `constraints/fmql30tai_pl_ethernet.xdc`；固定来源清单 `rtl/vendor/verilog_ethernet/sources.json`。
- [固定上游 MAC 实例](https://github.com/alexforencich/verilog-ethernet/blob/77320a9471d19c7dd383914bc049e02d9f4f1ffb/example/NexysVideo/fpga/rtl/fpga_core.v)，[板约束](https://github.com/alexforencich/verilog-ethernet/blob/77320a9471d19c7dd383914bc049e02d9f4f1ffb/example/NexysVideo/fpga/fpga.xdc)，[接口附加约束](https://github.com/alexforencich/verilog-ethernet/blob/77320a9471d19c7dd383914bc049e02d9f4f1ffb/example/NexysVideo/fpga/eth.xdc)。首次请求误用了 `constraints/fpga.xdc` 路径，返回 404，随后按实际路径成功读取；未把失败请求当作已取到内容。
- [AMD PG051：7 系列 HR I/O 发送结构](https://docs.amd.com/r/en-US/pg051-tri-mode-eth-mac/Transmitter-Logic-for-7-Series-Using-HR-I/O)，[共享逻辑](https://docs.amd.com/r/en-US/pg051-tri-mode-eth-mac/RGMII-for-7-Series-Devices)，[版本历史](https://docs.amd.com/r/en-US/pg051-tri-mode-eth-mac/Revision-History)，[IP 授权说明](https://docs.amd.com/r/en-US/pg051-tri-mode-eth-mac/Licensing-and-Ordering)。另核对 2012 年 v5.5 PDF 的对应 7 系列结构，不把旧版本当作当前工具的完整配套文件。
- [Linux 官方 PHY 文档](https://www.kernel.org/doc/html/latest/networking/phy.html)，[v6.12 Motorcomm 源码](https://github.com/torvalds/linux/blob/v6.12/drivers/net/phy/motorcomm.c)。
- [Enclustra 原作者适用范围](https://github.com/enclustra/GigabitEthernetAppNote/blob/master/Chapter-5-GMII_to_RGMII.md)。
- 本地制造商 PHY 手册：`D:/yzd/tmp/pl-jpeg-ethernet-1080p-20261023/YT8521S-datasheet.pdf`；目视复核既有 `phy-timing-page-73.png`。内容见 Table 138 / Figure 16。
- 新证据目录：`D:/yzd/tmp/pl-ethernet-reference-review-20261024/`。`reference-snapshots.json`、更正后的 `nexys-fpga-xdc.json` 保存连接器读取内容/出处；`web-evidence.json` 保存检索与官方页面结果；`audit.json` 保存输入散列和推导边界。没有读取或保存凭证。
- 有限检索包括 FMQL30TAI/PL Ethernet/RGMII/YT8521 组合、GitHub 代码查询及本地案例/工具包；搜索无结果不代表全网不存在，其他架构的联网教程或仅 PS 网口工程不作为 PL 引脚时序验证依据。
- 按聊天日期归档到 `D:/bigfuture/竞赛/记录/2026-10-24.md`，新增独立标记块，保留已有日期记录和来源文档。
