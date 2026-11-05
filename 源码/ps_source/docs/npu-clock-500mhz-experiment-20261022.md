# 500 MHz PLL 候选离线检查（2026-10-22）

工作日期依据任务目录及工具日志为 2026-10-22。后续上板记录另见 `npu-clock-500mhz-board-comparison-20261023.md`，本文件保留离线证据边界。

## 修改与结果

在已完成布线的优化版 1 GHz 检查点副本中，将实际 PLL 输出属性 `CLKOUT0_DIVIDE` 从 1 改为 2；输入 200 MHz、反馈倍频 5、PLL VCO 1000 MHz 不变。自动生成时钟由 1 ns 变为 2 ns，对应配置输出 500 MHz。未重新综合、布局或布线，未增加时序豁免。

目标 PLL 为 `U0_ps_ai_peripheral/ZGolo/u_AI_Mate_top/clkrst_wrapper_u0/AI_CORE_CLK/inst/plle2_adv_inst`，位置保持 `PLLE2_ADV_X1Y3`。实际输出为 `CLKOUT0`。背景资料《官方demo时序基线与器件库补丁》写成 `CLKOUT1` 且称用户不可改，和当前网表/属性修改结果有差异；本次以实际检查点为准。参数可修改仍不代表厂商保证其硬核兼容。

| 检查 | 1 GHz 原值 | 500 MHz 候选 |
|---|---:|---:|
| BUFG 最小周期余量 | -0.409 ns | +0.591 ns |
| PLL 最小周期余量 | -0.071 ns | +0.929 ns |
| 最差 setup 余量 | +0.005 ns | +0.005 ns |
| 最差 hold 余量 | +0.004 ns | +0.004 ns |

完整报告中 setup 246184 个端点、hold 243965 个端点、时钟检查 74353 个端点，失败数均为 0；105185/105185 条可布线网络已完整布线，无布线错误。DRC 无 Error/Critical Warning，bus-skew 无 VIOLATED；保留原有 REQP-44/46/52/56 的 Warning 配置，没有新加降级。

另外 67 个时钟的周期/波形未变，6 条 PLL 相邻网络的路由相同，SDI 参考时钟 U6/U5 未变。这是定点检查，不声称本轮重复完成了全设计物理等价证明。检查点二进制重新序列化会改变多个成员，不能凭 DCP 二进制差异判断逻辑差异。排除来源位置元数据后，约束语义差异仅为上述真实分频属性，没有删除原约束。

## 打包与回退

Vivado 2018.3 写出位流，USERID 为 `53180500`；Procise 按 JFMQL30TAI676H 转换并关闭 ICAP 后打包。BOOT 内 PL 内容与转换后位流核对一致；FSBL、BL31、U-Boot 与 1 GHz 对照及原已验收镜像逐字节相同。

- 500 MHz BOOT SHA256：`1ccf96fa0d3e422484797cbbfdb13b8156ee8b430aebb9d6e76da706423edff2`
- 同优化 RTL 的 1 GHz 对照 BOOT SHA256：`56889c4376b7ae5104e51a910278ff96e0d4d730ce4b5dc8d838e0bfb5980ecb`
- 上板前原镜像 SHA256：`f6da96abbc0144ce5a48f4fa85aed6dab65067211b8932e8f4e4db87d5110297`

学校服务器连接及工具在构建前重新检查，常见路径无 Vivado/Procise；因此仅本机私有任务目录进行 FPGA 离线处理，没有在板卡上编译模型。任务根目录为 `D:/yzd/tmp/npu-500mhz-test-20261022`。

## 问题处理与边界

初期全量路由/属性审计范围过大，带来内存压力和耗时，已停止本任务进程并保留日志；后续缩小到实际修改的 PLL、相关网络和全部时序检查，不是反复重新布线。首次报告显示行数不同来自 max_paths=5/20 的展示上限，门槛改为核对真实端点总数和目标检查，并重新生成同上限报告。

离线结果消除了当前代理器件模型中的两项最小周期违例，不能代替上板验证、硅片可靠性签核或真实 NPU 内核频率测量。500 MHz 是配置输出频率，不能直接认定 NPU 硬核频率也减半；ASR/LLM、全容量 DDR、温度/电压范围和长期稳定性均不在离线验证范围。

主要来源：任务目录下 `offline-gate.json`、`hardware-invariants.txt`、`constraint-comparison.json`、`timing.rpt`、`drc.rpt`、`route-status.rpt`、`boot-candidate/manifest.json`、`school-preflight-cad.json`、`school-preflight.json` 及各工具日志。背景来源为 `D:/xiangmuwendang/WCIS-FPAI/wiki/PL/FPGA/FPGArt/官方demo时序基线与器件库补丁.md`。
