# PL命令校验流水化（2026-10-22）

## 问题依据

上一阶段的reader/sampler控制周期优化通过独立测试，但整板路径暴露出从配置寄存器经过64位存储范围计算、参数校验到sampler寄存器使能的长组合路径。不能用独立模块时序通过代替整板时序通过。

`D:/yzd/tmp/pl-fastpath-board-20261022/control-closed-preserved-routed.dcp`已完成连接及静态物理保留核对，WNS仍为-0.166ns。随后`optimize_lut_placement.tcl`的最终`timing.rpt`显示WNS=-0.069ns、TNS=-1.564ns、58个建立时间失败终点；WHS=+0.004ns、THS=0。继承的两处NPU脉宽警告仍为-0.409ns。停止继续对该旧RTL反复调整布局；两版均未生成可放行bit/BOOT，也未部署。

此前实现流程确有额外重复：增量导入会清除固定路线标志；部分物理网络的层次别名没有一起处理；旧版工具拒绝了部分优化选项。这些脚本问题引发重复加载和检查，不能将总耗时归因于布线。已测的一次实际布线约4分25秒，其余时间包含工程加载、物理保留审计、时序报告及修复。

## RTL变更

本轮在保留reader/sampler优化的基础上，只额外修改`fpga_project/rtl/wcis_face_preprocess.v`：

- 外部命令接受时一次锁存几何参数、帧号、格式、基地址与步长，后续上游修改命令不会改变已接受的请求。
- 使用IDLE、CHECK、SEND阶段，将原来的存储范围校验结果寄存，再交给sampler。64位范围、对齐与步长判定公式保持一致，不新增时序例外或降低时钟频率。
- 每个命令增加两个时钟周期；100MHz下为20ns。逐像素采样与搬运循环没有因此增加周期。
- 两个新增阶段都可被复位中止；复位之前尚未交给sampler的命令不得发出AXI请求或像素输出。

私有冻结源码与构建入口在`D:/yzd/tmp/pl-command-validation-20261022`，此前源码保留为`src/wcis_face_preprocess-before.v`，未改原案例或安装数据库。

## 验证与当前边界

本轮实测：

- `preprocess-simulation/verification.json`：原23项预处理用例通过，含像素金模、命令接受后上游字段变化、异常参数、总线错误、复位及反压。
- `reset-simulation/verification.json`：新增CHECK/SEND阶段复位中止的2项用例通过，并验证下一条正常命令可完成。
- `candidate-simulation/verification.json`：使用候选实际封装的8项集成回归通过，包括1080p、960×540两种格式和112×112对齐。仿真耗时不等同板端延迟。

测试入口变更同时落在`sim/tb_face_preprocess.sv`与`scripts/verify_face_pl.py`。上述25项加8项是不同层级测试，不代表整板时序或上板通过。

新版整板上下文综合于16:20完成，导出`candidate-face.dcp`、`candidate-backend.dcp`等检查点。虽然部分IP检查点报告可复用，当前工程迁移和综合重置仍触发了MIG等依赖综合，这也是额外开销，不能声称整轮只综合了人脸模块。`post-synthesis-source-audit.json`核对416个暂存文件，仅6个MIG自动产物发生变化；文本产物归一化任务路径和生成时间后完全一致，约束和IP配置未变。MIG二进制DCP被重建，不声明其二进制或DDR功能等价；最终整板仍从原已验收底板导入，只替换face，不采用此次重新生成的MIG实现。

## 原生边界与增量实现

`export_contract.tcl`导出的外部驱动逻辑图/接收端清单显示，综合器将原配置输出16/17/18各32位合并成一组96位端口，并改变了另外2个自动端口名。`match_boundary.py`按唯一的外部连接签名得到98项映射；不靠相近名字猜测位序。原生封装重建96个输出位的端口，内部网络及原语保持不变，额外保留原底板中未使用的兼容输入。`interface-comparison.json`核对1618个端口的名称/方向及外部连接，差异为0；不是整片形式等价证明。端口调整期间发现本机工具不能逐位重命名总线，且删除连接端口前必须断开连接；这些修复只重新打开人脸小检查点，没有重新综合整板。

`implement.tcl`从原已验收`refclk-final.dcp`替换face，并只在人脸范围复用`control-closed-preserved-routed.dcp`的布局参考。首次增量导入后116967个模块外单元位置/类型检查通过，但旧的全路线相同检查拒绝了`U0_ps_ai_peripheral/S_AXI_HP2_WDATA[6]`；该信号已在上轮批准的非DDR调整清单中。保留`first-import-check-rejection-console.txt`，将检查改为严格DDR一致、模块外路线只允许已批准清单内变化。该首次导入状态未及时保存，实际引发一次重复加载；随后补上导入后立即保存的`imported-unverified.dcp`及`resume_imported.tcl`，后续检查失败不再需要重新综合或重新做增量导入。

16:28只读板端快照`board-during-command-validation.json`：启动ID仍为`8f360a28-0740-4d81-a13f-379a20faf47e`，无`/download.bit`，识别/摄像头均ready；1秒采集计数增加30，不能称为30fps识别。PAD仍`not_evaluated`，未部署新版位流或修改启动分区。新版整板实现仍进行中，尚无新版bit/BOOT或上板结论。

## 首次新版布线与位置冲突定位

新版首次完整布线用时1分42秒。完整时序报告为WNS=+0.005ns、TNS=0、WHS=+0.004ns、THS=0；继承的两处NPU脉宽告警仍为-0.409ns。连接报告仍有4条不完整网络：105185条应布网络中105181条完整，不能生成位流。`first-route-*`保留该阶段的报告、DCP及物理保留证明；该证明不包含连接完整或时序签核的含义。

该阶段116967个模块外单元保持原位，26547条DDR路线相同；完整核对133589条模块外路线，25条变化均在批准的非DDR范围内。检查178773个静态LUT输入映射，159个LUT的171个输入发生重排；与DDR交集为0，逐个LUT的INIT及逻辑输入连接与底板一致。静态时钟节点保留。批准范围归一为49条物理信号、225个层次别名，不能把别名数当成独立信号数。

`repair_connections.tcl`仅解除并重新布4条失败信号，没有改源码或综合。该尝试于16:55结束，仍有连接错误；原始结果归档为`second-route-*`。新的诊断明确报出4个引脚与固定路线占用冲突，包括原有JPEG指针、NPU FIFO及DDR局部路线。单纯解除失败网络自己的固定标志不能释放这些占用，因而不继续重复相同重连。19:30恢复工作时已无该CAD进程，并非一直运行到19:30。

## 九单元位置修复

19:30后再次核对学校服务器：仍无发现的Vivado/Procise工具，历史预检保留为`school-preflight-before-site-repair.json`。`relocate_conflicts.tcl`复用已有的整位置移动和进位链闭包方法，按4个明确冲突引脚展开为4个位置、9个单元，均为人脸范围内寄存器，不涉及进位链。其余原语名称、类型、LOC/BEL在移动前后逐项相同。

目的位置排除所有DDR信号路线经过的整块tile，并排除DDR信号端点所在tile，以覆盖局部引脚/复用资源。原先自行设定的64范围内搜索对`SLICE_X12Y92`无解；保留`site-plan-local-window-rejection-console.txt`后扩大到器件范围，取符合条件的空位，未放松DDR排除条件。最终移动：

- `SLICE_X112Y185`内6个geometry_hold寄存器到`SLICE_X112Y191`。
- `SLICE_X115Y171`的geometry_hold[313]到`SLICE_X119Y189`。
- `SLICE_X12Y92`的cfg_reg[18][2]到`SLICE_X10Y15`。
- `SLICE_X109Y186`的cfg_reg[9][10]到`SLICE_X113Y191`。

具体BEL及原语类型见`conflict-register-moves.tsv`；移动计划在`conflict-relocation-plan.tcl`。只解除目标相关信号及目的tile内明确经过的非DDR信号，连同既有范围归一为92条物理信号/813个别名；逐段拒绝DDR、时钟和常量交集。共享时钟重新保留原静态路径，常量仅按两个物理树处理。迁移后先保存`conflict-relocated-placed.dcp`，随后完成下述布线与完整门槛检查。

## 最终离线候选（19:50完成）

位置修复后的布线用时1分46秒，105185条应布网络全部完整连接，routing error为0。路由器中间估计曾有WNS=-0.031ns；完整`report_timing_summary`为WNS=+0.005ns、TNS=0、WHS=+0.004ns、THS=0，以完整报告为准，没有为此再运行局部时序优化。原两处NPU脉宽告警仍为-0.409ns。

最终`preservation-proof.txt`：116967个模块外单元保持类型、LOC/BEL；133589条模块外路线逐项核对，41条变化全部在92条批准物理信号范围内；26547条DDR路线完全一致。178773个静态LUT输入核对，165个LUT的177个输入发生物理重排，与DDR交集为0；重新打开原已验收底板，逐个比较对应INIT及逻辑输入网络均相同。只手工移动上述9个人脸寄存器，没有复制逻辑。新DCP为`preserved-routed.dcp`，SHA256为`a97084dd6df95d10b3d0e67a914de717fa71963d3d58363aae2885f233f1652e`。

`audit_generate.tcl`与`gate.py`额外确认：

- 96个reader缓存标签寄存器存在，预处理时钟保持10ns；原第二缓存银行512个寄存器保留。
- 从优化后的原生backend导出寄存器名字/类型，再与实际整板逐项对照：状态寄存器3个、合法性结果寄存器1个、描述符寄存器345个一致。先前按名字正则直接统计的检查未通过；改为只统计FF并比较优化后源清单，不重做综合或布线，拒绝日志保留为`pipeline-inventory-check-rejection-console.txt`。
- 原静态HP/GP时钟PIP分别32492/9253条均保留；6组face/JPEG跨时钟邮箱路径为有限正裕量，8ns/20ns约束保持；bus-skew无失败。
- 5个IDELAYCTRL的复位/参考时钟有驱动；SDI参考时钟引脚仍为U6/U5；未包含未请求的公平仲裁器。
- 最终DRC无Error/Critical Warning，原REQP-44/46/52/56仍沿用已验收原型的Warning设置，并非新增加的豁免。源码、配置、独立测试、接口契约和检查点哈希核对通过，证明不得早于对应DCP。

重新打开手工放置后的DCP时，工具报9次`Netlist 29-72`：优化跟踪属性`REUSE_STATUS=ReusedXDC`不在本机枚举中，工具按消息丢弃/默认该属性。原始消息保留在`audit_generate-console.txt`及`candidate-summary.json`，未修改安装数据库或用降低该消息严重性隐藏它。此后未做新的布局/布线；源寄存器清单、时钟/邮箱等硬件核对通过，`write_bitstream`成功，其bitgen阶段汇总为0 Critical Warning/0 Error。该工具元数据问题仍如实保留，不能把bitgen局部汇总写成整个工具流程毫无告警。

`fastpath.bit`于19:50生成，USERID为`53180206`。随后Procise按`JFMQL30TAI676H`转换并禁用ICAP，打包`boot-candidate/BOOT.bin`。`verify_package.py`核对BOOT内PL有效载荷与此次转换后位流一致，FSBL、BL31、U-Boot三分区与本地原已验收BOOT完全一致。参考BOOT的依据是此前同启动ID记录及本地校验，未在本轮重新挂载/读取板端启动分区。

- 候选BOOT SHA256：`56889c4376b7ae5104e51a910278ff96e0d4d730ce4b5dc8d838e0bfb5980ecb`。
- Procise转换后候选bit SHA256：`d20e760fba4a8b067789aedd463ca7de675299f95417751a5ce941455830b513`。
- 原始Vivado bit SHA256：`45141758a9b489456a81e1da6bcc87b92b36ac52e5da5a3ab5f2230ac10d4837`。两种bit含义不同，不混用其校验值。

产物入口：`D:/yzd/tmp/pl-command-validation-20261022/boot-candidate/BOOT.bin`、同目录`manifest.json`，以及上级`timing-gate.json`、`hardware-audit.txt`、`candidate-summary.json`。离线状态为`offline_candidate_ready`；`deployed=false`、`board_verified=false`、`production_timing_signoff=false`。建立时间裕量很薄且继承NPU脉宽告警，不宣称生产裕量或完整安全验证。

19:50:49只读复查并保存`board-after-offline-candidate-1950.json`（同名最新状态别名`board-during-command-validation.json`也已更新）：启动ID仍`8f360a28-0740-4d81-a13f-379a20faf47e`，无`/download.bit`，识别/摄像头均ready，1秒采集计数增加31；这不是模型识别帧率。PAD仍`not_evaluated`。未上传、加载或部署新版BOOT/位流，没有上板提速、防伪或DDR容量的新结论。

本轮重新核对学校服务器连接成功，未发现可用Vivado/Procise命令或已检查常见安装目录，因此FPGA CAD在本地私有任务目录运行。未在板端编译模型，未操作板端启动分区。

本轮已按原生边界核对、增量实现和分阶段检查点完成离线构建。后续部署需要独立安排停流、启动镜像切换及重启，再做原有DDR/像素金模、模型输出和持续SDI对照；当前不能将候选包生成视作这些板测已经完成。项目约定禁止自行修改启动分区，本轮停在可审阅的离线候选。

## 离线收尾（20:50，按用户要求暂不上板）

本轮复查`D:/xiangmuwendang/WCIS-FPAI/wiki/PL/plvid.md`，其intro仍写YuNet+SFace，模型列表则已划去SFace、列出MobileFaceNet；不据此改动现役模型。此阶段没有连接板卡、修改RTL、重新综合/布线、生成新的bit或BOOT，也没有部署。下面所有检查仍针对19:50的同一候选。

### 旧NPU时钟告警的精确核对

前文“脉宽告警”沿用了Vivado的`Pulse Width Checks`报告分组名；两项实际检查类型都是**Min Period（最小周期）**，不是已定位的占空比或窄脉冲故障。`scripts/audit_timing_compatibility.py`分别解析原底板和候选报告的64个表、1254条检查，逐项核对失败的时钟、周期、类型、器件引脚、参考引脚、要求值、实际值、裕量及位置，不再只依赖失败数量和最差裕量。

两项均属于`clk_out1_AI_CORE_CLK_ST`，周期1.000ns：

|对象|类型|要求周期|实际周期|裕量|
|---|---|---:|---:|---:|
|`AI_CORE_CLK/inst/clkout1_buf/I`，BUFGCTRL_X0Y20|Min Period|1.409ns|1.000ns|-0.409ns|
|`AI_CORE_CLK/inst/plle2_adv_inst/CLKOUT0`，PLLE2_ADV_X1Y3|Min Period|1.071ns|1.000ns|-0.071ns|

完整对象前缀为`U0_ps_ai_peripheral/ZGolo/u_AI_Mate_top/clkrst_wrapper_u0/`。两份报告的失败明细与汇总完全相同，证据为`legacy-clock-audit.json`。原`gate.py`与`timing-gate.json`保留，新增审计作为额外门槛，没有追溯性宣称旧门槛原本就会逐项比较。`sim/test_audit_timing_compatibility.py`的12项测试全部通过，包括失败数量/最差裕量未变而失败对象、类型、要求值变化，以及缺行、截断、NaN、建立时间失败等拒绝路径。

这只能证明候选没有改变这些已知失败，不是厂商豁免。FMQL目标与兼容代理器件的时序模型差异是一种待厂商依据核实的可能解释，不能据此认定无害；未改NPU时钟、安装数据库或新增时序例外。完整时序签核仍为false。

### 冻结候选的真实双核并发回归

复用已有`sim/tb_recording_parallel.sv`与JPEG软件参考实现，通过`scripts/verify_frozen_recording_parallel.py`直接编译冻结`case/rtl/wcis`和`case/rtl/adder_op`，不使用工作区尚未入候选的公平仲裁/写回确认逻辑。测试副本增加种子和慢速内存反压参数；产品RTL不变。全部源文件哈希与候选集成回归一致，并在测试结束后再次核对。

|输入格式|反压条件|完成帧数|两帧双核忙重叠周期|JPEG系数最大差|
|---|---|---:|---|---:|
|RGB565|原正常随机延迟，种子623eebf7|2|6926 / 6974|1|
|RGB565|慢速DDR，种子d1cebeef|2|7642 / 7948|1|
|BGRX|原正常随机延迟，种子623eebf7|2|6928 / 6980|1|
|BGRX|慢速DDR，种子d1cebeef|2|10072 / 10450|1|

慢速条件将读返回延迟从0–15周期扩大到0–127周期，并提高读/写接受反压。每组真实FAC1、JPG1同时运行，检查人脸每个输出像素、帧ID、读写请求反压保持、访问范围、输出首尾保护、容量不足错误及忙时配置拒绝，并独立解码JPEG、比对软件参考量化系数。证据为`concurrent-simulation/verification.json`及四份原始日志。64×16是该JPEG回归的仿真尺寸；8帧有限作业完成不等于全分辨率持续吞吐、板端稳定性或固定优先级仲裁的公平性证明。并发测试对象是FAC1和JPEG，不是NPU模型双核并发。

### 可移植离线候选与回退包

`D:/yzd/tmp/pl-command-validation-20261022/release-offline/`包含22个有哈希清单的文件及`release-manifest.json`：

- `candidate/BOOT.bin`仍为`56889c4376b7ae5104e51a910278ff96e0d4d730ce4b5dc8d838e0bfb5980ecb`，包含本轮Procise转换后的bit；不重生成产物。
- `rollback/BOOT.bin`取自本地此前已验收的SDI修正版，SHA256为`f6da96abbc0144ce5a48f4fa85aed6dab65067211b8932e8f4e4db87d5110297`；不是更早的厂商原版。
- `verify_bundle.py`为`scripts/verify_offline_release.py`的副本，仅在本地读取文件，校验文件集合/大小/哈希、三个PS分区一致以及bit/BOOT有效载荷对应。包中不提供刷写、挂载、SSH或重启程序；哈希检查是完整性检查，不是数字签名认证。
- `evidence/`保留封装、接口、物理审计及回归记录。`prepare_offline_bundle.py`在打包前重新核对原门槛所列产物、DCP、固定源码及测试日志哈希。

整包只读校验通过，见`offline-bundle-verification.log`。另在任务私有副本做8项校验器测试：完整副本通过；损坏BOOT、PS内容改变且更新哈希、bit/BOOT不一致且更新哈希、多余文件、缺失BOOT、错误宣称板测通过六项均被拒绝；恢复后完整副本再次通过，见`bundle-negative-tests.json`。没有用错误包接触板卡。

本包是BOOT级回退材料，不是完整启动盘镜像；未重新读取板上DTB/uEnv，也未确认当前启动介质能否在线下恢复。历史`/dev/mmcblk0p1`不能直接当作下一次写入目标，旧软件回退计时器也不能覆盖Linux启动前死机。后续上板前需要确认实际启动源及可用的线下恢复途径，再安排停止采集、部署与验收。用户要求做完再上板，故此阶段保持`deployed=false`、`board_verified=false`、`production_timing_signoff=false`，不继续连接或操作板卡。此前真人/手机实拍初测不等于防伪验收，PAD仍未接入正式放行。

## 关键来源

- `D:/yzd/tmp/pl-fastpath-board-20261022/optimize_lut_placement-console.txt`、`timing.rpt`、`preservation-proof.txt`。
- `D:/yzd/tmp/pl-command-validation-20261022/src/`、`staged-sources.json`、`input-manifest.json`、`school-preflight.json`。
- 同目录的三份`verification.json`、`synthesize.tcl`、`synthesize-console.txt`及`case/fpai_demo_vivado.runs/`原始日志。

工作日期依据本次2026-10-22构建与验证日志；记录同步合并到`D:/bigfuture/竞赛/记录/2026-10-22.md`。
