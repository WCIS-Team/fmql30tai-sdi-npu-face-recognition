# NPU 1GHz最小周期失败的厂商依据核查（2026-10-22）

## 用户选择与当前结论

用户要求消除两项Min Period失败，并明确选择**保留1GHz，先查厂商依据**。本轮未消除失败，也没有把它改成豁免或签核通过。已经定位到厂商网表和所交付器件模型之间的具体不一致，但尚缺厂家对实际FMQL30TAI时钟能力及模型适用性的说明。不能通过修改我们的人脸RTL，或更改时钟约束文本就证明该问题得到解决。

现有1GHz候选的DCP、bit、BOOT、安装库均保持不变；未连接板卡、上传、加载、重启或修改启动分区。原候选仍是离线原型，不是完整时序签核。

## 本地正本与重新取证

背景读取`D:/xiangmuwendang/WCIS-FPAI/wiki/PL/FPGA/FPGArt/官方demo时序基线与器件库补丁.md`。其中1GHz来源与现有EDIF参数一致，但该页将实际连接写成CLKOUT1；直接读取当前`fpga_project/case/rtl/edif/AI_Mate.edif`和候选路由DCP，实际连接均为**CLKOUT0**。以正本网表与当前DCP为准，未改写背景文档。

`D:/yzd/tmp/npu-min-period-20261022/audit.tcl`只读打开原19:50候选`preserved-routed.dcp`，核对：

- `PLLE2_ADV`实例为`U0_ps_ai_peripheral/ZGolo/u_AI_Mate_top/clkrst_wrapper_u0/AI_CORE_CLK/inst/plle2_adv_inst`，固定在PLLE2_ADV_X1Y3。
- 输入周期5ns、反馈倍频5、输入分频1、CLKOUT0分频1。自动生成的`clk_out1_AI_CORE_CLK_ST`周期1.000ns；没有用户人为指定的慢周期来掩盖真实配置。
- CLKOUT0连接`clkout1_buf/I`，BUFG固定于BUFGCTRL_X0Y20；BUFG输出唯一可见FF负载为`ai_core_clk_locked_reg/C`。该FF的Q没有可见负载。
- PLL的LOCKED还直接连接BIST的`start_d1_reg/D`及状态机组合输入`current_state_i_1/I0`。**可见FF负载少不等于PLL/BUFG可删除**；厂商转换后与NPU硬核的时钟关系尚未取得正式依据。不能从代理网表可见扇出推断真实NPU时钟可任意删改。

原先两项失败的具体对象、类型与数值仍见`pl-command-validation-20261022.md`和原`legacy-clock-audit.json`：BUFG/I要求1.409ns而实际1.000ns，裕量-0.409ns；PLLE2_ADV/CLKOUT0要求1.071ns而实际1.000ns，裕量-0.071ns。它们是最小周期失败，不是人脸像素数据路径的建立/保持时间失败。

## 器件库是否漏装

`inventory_models.py`比较本机实际安装模型与`C:/Users/anxianji/Downloads/20260916/JFM_Kits/JFM_Kits/ip_patch/030ai`的原始文件，六项SHA256全部一致：

|内容|本机文件|交付包文件|
|---|---|---|
|逻辑/时序模型声明|`data/parts/xilinx/zynq/devint/zynq.lib`|`030ai/zynq.lib`|
|物理布局模型|`data/parts/xilinx/zynq/devint/zynq.padr`|`030ai/zynq.padr`|
|路由/时序数据库|`data/parts/xilinx/zynq/devint/zynq.rtd`|`030ai/zynq.rtd`|
|网格模型|`data/parts/xilinx/zynq/devint/zynq.xng`|`030ai/zynq.xng`|
|站点映射|`data/parts/xilinx/zynq/devint/Sitemap2.xml`|`030ai/Sitemap2.xml`|
|器件专属模型|`data/parts/xilinx/zynq/devint/zynq/xc7z030/xc7z030.paspd`|`030ai/xc7z030ai.paspd`|

这里只排除了这六份模型与现有交付包不一致的情况，不等于证明整个工具环境全部正确，也不等于这版交付模型已经针对1GHz完成硅片表征。交付包`ip_patch_version.log`为`5.3.2.1_100AI_LV`，不能单凭这个标识确认030ai专属时序适用版本；`time_check.txt`确实为空，不能当成时序豁免说明。本轮不替换安装文件、不编辑数据库数值。

当前版本仍为Vivado2018.3、代理器件xc7z030ffg676-2；原报告Speed File为`-2 PRODUCTION 1.11 2025-11-03`。所有六项对应路径、字节数和完整哈希在`model-inventory.json`。

## 查阅资料的边界

直接读取了交付的`30TAI使用教程.pdf`、`悟净开发板硬件使用手册V1.0_集创赛.pdf`、`FPAI_DEMO说明.pdf`，对应页摘录与源文件哈希见`vendor-evidence.json`。已查材料没有给出两项Min Period的正式豁免、修正库或其限值对FMQL30TAI的适用说明；这不是对所有厂商内部资料是否存在的断言。

公开资料同时核对：

- [复旦微FMQL30TAI产品页](https://www.fmsh.com/fpga/products/chip/fmql30tai.html)：页面的最高1GHz明确列在处理器系统下，不能用作NPU这路PLL/BUFG的1GHz时序背书。
- [复旦微FPAI架构页](https://www.fmsh.com/fpga/fpai/architecture.html)：是产品系列架构说明，不能替代特定030ai模型和两项端点检查的适用证明。
- [AMD PLLE2_ADV原语说明](https://docs.amd.com/r/en-US/ug953-vivado-7series-libraries/PLLE2_ADV)：输出分频参数决定实际输出频率；它解释代理原语语义，不是FMQL30TAI的硅片频率保证。

此前对“用户侧改不了”的说法也应细化：SDK不能设ZG330频率，不意味着离线网表属性在技术上不可编辑；但**可编辑不等于厂商支持，也不证明修改后硬核兼容**。

## 已终止的独立降频实验

在用户选择到达前曾启动隔离的`divide2_experiment.tcl`，尝试在内存副本将实际PLL输出分频由1改2，不改时序约束。用户明确保留1GHz后，仅终止了命令行同时匹配本任务目录与`divide2_experiment.tcl`的本任务CAD进程。实验退出码-1，尚未得到自动生成时钟/完整时序结果，**未写出实验DCP、bit或BOOT，不能称500MHz消除了违规**。原1GHzDCP/BOOT及旧门槛内全部输入的SHA256重新核对均未变。降频路线不继续，不作为候选。

学校连接本轮复核成功，已检查常见路径仍无Vivado/Procise，也未发现相关运行任务；因此只读CAD核对在本机私有目录完成。没有模型导出、转换、板端编译或推理。

## 可交给厂商的核对材料

`D:/yzd/tmp/npu-min-period-20261022/vendor-review-packet/`已经整理：具体问题清单、PLL属性、实际直连端点、厂商时钟单元EDIF片段、原/候选时序失败明细、六项库哈希和源文件校验清单。材料只在本地准备，未发送给任何人。

需要厂商提供的关键回答是：**当前1.409ns/1.071ns限值是否适用于JFMQL30TAI676H；如不适用，哪一版正式模型/网表/实现方法能在保留1GHz时正确完成检查，以及其器件、电压、温度和工具版本范围。**

拿到依据后才能选择修正器件模型或采用厂商支持的时钟实现，再重新出完整时序报告。当前状态为`unresolved_vendor_clock_basis`，`timing_violations_removed=false`、`deployed=false`、`production_timing_signoff=false`。不以反复布线、降低DRC严重性、删除无明显负载的PLL或放宽min-period来替代缺失依据。

关键来源：本任务`core-clock-topology.txt`、`pll-properties.rpt`、`clocks.rpt`、`audit-console.txt`、`model-inventory.json`、`vendor-evidence.json`、`school-preflight.json`与原候选`timing.rpt`。工作日期按2026-10-22，归档同步到`D:/bigfuture/竞赛/记录/2026-10-22.md`。
