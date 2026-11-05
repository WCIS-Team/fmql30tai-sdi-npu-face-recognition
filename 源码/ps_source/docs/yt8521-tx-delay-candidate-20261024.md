# YT8521 内部发送延迟候选（2026-10-24）

## 当前结果

接续 `pl-ethernet-reference-review-20261024.md` 的案例对照，用户要求继续。新增了默认关闭的同相发送候选，并完成数字逻辑仿真；物理时序依据仍未补齐，因此没有启动新的综合/布局布线、生成 bit/BOOT 或操作板卡。本轮不实现移动展示配置，不改 NPU/DDR 时钟、引脚、电平、原 PHY 配置工具或已安装工具库。

验证结果为 6 组正常用例、每组 17 个报文，共 102 个报文通过；另外 2 组故意配置错误的用例均被接收时序监视器拒绝。这里是数字逻辑证明，不是实际 YT8521、PCB、PHY 全温压或新的 routed 通过证明。

## PHY 资料核实

使用 PDF 技能对现有制造商手册做只读核对。`YT8521S-datasheet.pdf` 首页标记 V1.01 / 2020-06-17，文件 SHA256 为 `71be2eacdc1ccaeef333a434c382ba05db556d3e69d22c2b19f631c6df6ff172`。

- PDF 第 31 页（印刷页 20），`RGMII_Config1` 的 `Tx_delay_sel[3:0]` 写明千兆发送时钟延迟**典型**每步 150 ps；该条目没有给出所选 code 的最小/最大延迟。
- PDF 第 73 页（印刷页 62），Figure 16 / Table 138 列出建立/保持时间最小 1 ns、典型 2 ns。没有取得能够把 code 13 的标称 1950 ps 直接转换成所需全温压外部时序边界的补充依据，故不改写现有 +1.2/−1.2 ns 接收端要求，不把典型值视为确定延迟。
- 使用本机已有 Poppler 将上述两页渲染成 `datasheet-register-a003.png`、`datasheet-timing.png` 并目视核对；渲染器报 Symbol/ArialUnicode 字体提示，生成图片的表格和关键数值可读，没有据文本抽取臆补波形含义。
- 搜索命中制造商域名的软件开发指南：`https://www.motor-comm.com/Public/Uploads/uploadfile/files/20250424/yutaiyitaiwangphyxinpianruanjiankaifashuoming.pdf`。web 打开与普通后台 HTTP GET 均实际返回 404；没有将搜索摘要称为已下载或已完整阅读的指南。
- 官网 `/download` 公共索引实际 HTTP 200；官方 YT8521 产品简介实际 HTTP 200、353055 字节，SHA256 为 `151cfc75f674b69fda8418aee95d1b3d12aef242744cba02e4377836d72dadd0`。产品简介不能替代缺失的详细时序依据。本轮未登录、提交资料申请或联系他人。

这些结果不说明 YT8521 不支持内部发送延迟。前轮核对的 Linux v6.12 驱动仍能作为寄存器配置依据，当前缺的是与具体型号/配置匹配的物理时序验收依据。

## 实现内容

`rtl/wcis_jpeg_network_tx.v` 新增静态参数 `USE_PHY_TX_DELAY=0`：

| 值 | FPGA 转发时钟 | PHY 责任 | 状态 |
| --- | --- | --- | --- |
| 0，默认 | 原 +90° 的 125 MHz 时钟 | TX 内部延迟为零 | 保留原数字行为；不改变早前物理时序失败结论 |
| 1 | 与数据/控制 ODDR 共用同一个 `gtx_clk` | 提供匹配的内部 TX 延迟 | 仅离线候选，未取得板级准入 |

实现只选择既有上游 `ssio_ddr_out` 的 `USE_CLK90` 参数，没有修改固定 MIT 上游源码、协议栈、校验和、帧 FIFO 或地址配置逻辑。修正了一条将物理时钟误称为“更快”的注释：本模块在 150 MHz 逻辑域与 125 MHz MAC 域之间跨域，并非后者更快。

`npu_photo/src/pl_net_config.cpp` 保持原来的 MAC +90° / PHY TX 零延迟逻辑，未修改或重新编译/部署。正式整板仍使用原完整收发模块；新参数为 1 的调用仅出现在此次离线台架。因此不能只把候选参数打开后直接运行旧配置程序，也不能据此声称同相方案已经集成或上板。

## 仿真方法与结果

`sim/tb_jpeg_network_tx.sv` 增加显式的行为接收时钟延迟和窗口检查。采样事件按接收时钟的真实仿真时刻执行，不额外平移 0.1 ns；在活动报文期间，监视数据/控制线在每个接收采样点前后是否至少保持 1 ns。该监视器检查的是**理想数字波形**，没有包含布线传播、晶体管、PHY 延迟误差、温度或电压变化。

| 用例 | 输出原语模型 | FPGA 模式 | 行为接收延迟 | 结果 |
| --- | --- | --- | ---: | --- |
| 原默认模式 | SIM | MAC +90° | 0 ps | 17/17 报文通过 |
| 原默认模式 | Xilinx ODDR/glbl | MAC +90° | 0 ps | 17/17 报文通过 |
| 同相候选 | SIM | PHY 负责延迟 | 1950 ps | 17/17 报文通过 |
| 同相候选 | Xilinx ODDR/glbl | PHY 负责延迟 | 1950 ps | 17/17 报文通过 |
| 理想窗口偏早点 | SIM | PHY 负责延迟 | 1200 ps | 17/17 报文通过 |
| 理想窗口偏晚点 | SIM | PHY 负责延迟 | 2700 ps | 17/17 报文通过 |
| 故意漏加延迟 | Xilinx ODDR/glbl | PHY 模式 | 0 ps | 预期失败，被窗口监视器拒绝 |
| 故意重复加延迟 | Xilinx ODDR/glbl | MAC +90° | 再加 1950 ps | 预期失败，被窗口监视器拒绝 |

1200/1950/2700 ps 是为检验理想数字采样窗口选择的三个测试点，不是已测得的 PHY 延迟范围，不代表寄存器支持全部这些数值，也不是 PVT 裕量。2700 ps 尤其不能当作该 GE TX 延迟字段的可选设置。

每组正常用例仍覆盖 1/17/1440/1472 字节负载、连续 12 个最大报文、输入背压、零/广播下一跳拒绝、半包复位和更换 MAC 后恢复。Python 从输出字节独立核对前导码、FCS、IPv4 校验和、非零 UDP 校验和、长度/地址/端口与完整载荷；不是只检查 HDL 打印的 PASS。候选的 Xilinx 验证只使用已安装原语功能模型，不是布局后时序仿真。

`scripts/verify_pl_jpeg_tx.py` 增加 `--phy-tx-delay` 和仅供行为仿真的 `--receiver-delay-ps`。所有结果显式写入 `clock_mode`、`receiver_delay_ps`、`nominal_phy_model_only=true`、`physical_timing_verified=false`、`board_verified=false`，并绑定实际源码及验证程序散列。

验证命令示例：

```powershell
python fpga_project/scripts/verify_pl_jpeg_tx.py --out D:/yzd/tmp/yt8521-tx-delay-20261024/sim-phy1950-xilinx --phy-tx-delay --xilinx
```

## 验收边界及后续

当前可以确认同相发送候选的数字报文结构与默认模式兼容，且测试能够识别两端延迟分工错误；尚不能确认该模式在实板满足建立/保持时间或提高吞吐。

只有补齐具体 PHY/所选 TX 延迟的接收端时序依据、PCB 预算，并让 FPGA 模式/PHY 配置/有限双边沿约束绑定一致后，才能进入新的独立物理验证。不能用理想接收模型通过来绕过这一步；原整板打包/部署门槛不变。本轮未对同相候选建立宽松假设约束来获取“时序通过”报告，也未继续 PLL 参数扫描。

## 关键本地来源与归档

- 项目文件：`rtl/wcis_jpeg_network_tx.v`、`sim/tb_jpeg_network_tx.sv`、`scripts/verify_pl_jpeg_tx.py`。
- 资料与旧物理证据：`pl-ethernet-reference-review-20261024.md`、`D:/yzd/tmp/pl-jpeg-ethernet-1080p-20261023/YT8521S-datasheet.pdf`、`tx-only/physical/tx-io-timing.rpt`。
- 本轮隔离目录：`D:/yzd/tmp/yt8521-tx-delay-20261024`，含 `vendor-fetch.json`、`web-evidence.json`、PDF 渲染图、6 个正常用例目录、2 个预期失败目录及日志。
- `check_candidate_results.py` 核对全部正常结果的当前源码散列，并要求两组错误配置确实在已成功编译后的仿真阶段触发接收窗口错误。汇总 `candidate-checks.json`：`positive_cases=6`、`positive_packets=102`、`negative_cases=2`、`physical_timing_admitted=false`、`cad_run=false`、`board_verified=false`。
- 本轮记录按聊天日期同步到 `D:/bigfuture/竞赛/记录/2026-10-24.md` 的独立标记块；保留当日既有记录和原始资料。
