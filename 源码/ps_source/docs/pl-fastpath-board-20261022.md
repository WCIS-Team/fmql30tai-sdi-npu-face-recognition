# PL预处理控制优化整板候选构建（2026-10-22）

当前状态：候选仿真、综合、接口及物理保留检查通过；最新完成阶段全部104875条网络连接完整，DDR与完整HP/GP时钟路线保留。仍有WNS=-0.166ns建立时间裕量失败，正在做仅针对LUT的受控位置优化；无可放行的新bit/BOOT，未部署。

本轮承接[PL预处理控制周期优化](pl-reader-fastpath-20261022.md)，目标是在已验收整板实现中接入reader缓存命中快速返回与sampler提前发请求两项改动。日期依据本轮客户端和构建日志的2026-10-22。学校连接检查成功，但命令路径及检查的常用安装位置未找到Vivado/Procise；RTL整板实现使用本机既有Vivado2018.3和Procise，没有模型转换、模型编译或AArch64构建。

## 底板与改动范围

- 采用`D:/yzd/tmp/sdi-refclk-fix-20261020/refclk-final.dcp`，SHA256为`8e54e4cb42be0164d7925e9d2ef877745d663f79a87f4d8272414543441be2e8`。该底板包含已通过板测的双64字节行缓存及完整版SDI U6/U5入口修正；其历史验收见[SDI修正记录](sdi-refclk-fix-20261020.md)。
- 本轮开始只读观察到板上启动ID仍为`8f360a28-0740-4d81-a13f-379a20faf47e`，识别health为ready，摄像头持续输出新帧，未发现`/download.bit`覆盖。没有停止服务、打开第二个SDK所有者或发起硬件计算命令。
- 同一启动的既有BOOT证明记录为`f6da96abbc0144ce5a48f4fa85aed6dab65067211b8932e8f4e4db87d5110297`；本轮尚未重新挂载启动分区读取BOOT字节，不能将历史证明称为本轮新读回。
- 私有工程复制自`D:/yzd/tmp/face-cache-board-20261018/case`，两份待替换旧RTL的SHA与上一轮冻结基线一致。只替换`wcis_pixel_read_axi.v`与`wcis_affine_sampler.v`，保留底板的FAC1行缓存、原仲裁与JPEG。未合入候选公平仲裁、写回确认桥或PL PAD裁图，没有修改模型、阈值、前端和业务权限逻辑。
- 新任务所有源码副本、补丁、缓存、日志和产物均在`D:/yzd/tmp/pl-fastpath-board-20261022`；学校共享工具、Downloads原始案例、项目原case和已安装时序数据库未修改。

背景读取`D:/xiangmuwendang/WCIS-FPAI/wiki/PL/plvid.md`及`SOP/bitproc.md`。前者intro仍写SFace，而模型列表及当前应用采用YuNet/MobileFaceNet，本轮按源码和实际模型接口处理。文档里的旧Vivado版本提示不替代本项目已验证的2018.3流程。

## 综合与接口处理

直接将独立OOC的`wcis_face_preprocess`换入原实现不可行：原工程的跨层次综合已改变内部切点和自动端口。先在私有原工程上下文重新综合，再导出完整`U_adder_top/face`原生DCP，保留范围外DDR、NPU、JPEG、视频及SDI实现。

厂商pre-synthesis钩子重生成私有副本中的MIG DCP、XML、Verilog/VHDL仿真网表与stub，共6个派生文件；其他已登记源码及约束未变。这份新综合的MIG不进入最终局部替换，DDR继续来自原已验收DCP。只读工具保护阻止共享工具库被改写，三份已安装数据库文件SHA保持基线值。

边界处理如下：

1. 候选综合导出1617个端口；现役底板边界为1618个。
2. 两个自动命名输入`busy151_out`、`p_0_in50_out`分别映射到原`busy142_out`、`p_0_in41_out`。逐项比较公共输入的有序外部组合驱动图及输出的范围外接收端，全部一致。
3. 底板还有前次物理提取留下的`wr_owner_reg_0_repN_alias`输入。新综合的完整模块不依赖该输入，增加未使用的兼容端口保留底板接口，不改候选功能逻辑。
4. 处理后的1618个端口名称和方向与底板一致；公共端口契约比较无差异。该检查为结构与接口核对，不是整片形式等价证明。

`interface-comparison.json`记录边界及原生DCP SHA；`candidate-contract.tcl`、`baseline-contract.tcl`保存比较输入，候选驱动锥缓存2436个节点。

## 实际候选源码仿真

使用私有工程中的实际旧仲裁/JPEG/FAC1包装与新reader/sampler运行ModelSim，而非只测当前工作区另一版包装。8组全部通过，包含原厂adder、描述符、CDC、完整像素、背压、换帧及源格式检查：identity、旋转补边、RGB565步长、同址换帧、真实人脸112、1080p检测输入、960×540 RGB565与BGRX。

其中两项仿真作业时间复现上一轮结果：960×540 RGB565为64.229730ms，真实人脸112为4.150140ms；native读/写分别36000/25600和7079/784。计时包含接口与测试端完成检查，不是纯核计数或板端耗时。未据此声称当前摄像头识别已经提速。

## 范围外实现保留

从底板导出116967个范围外非恒定原语的位置/类型、133589条范围外非恒定网络ROUTE、26547条DDR非共享信号ROUTE及178773个静态LUT输入物理绑定。共享HP/GP时钟使用已有`prune_clock_routes.py`：只移除通向旧目标模块的独占末端，保留所有静态负载到源的原路径；HP保留32493个节点，GP保留9254个节点。

替换并读取新模块后，116967个范围外原语名称、类型、LOC/BEL一致；133589条范围外网络和26547条DDR路线逐项相同。布局完成后再次通过相同检查，178773个静态LUT输入物理绑定也一致。布线后检查未通过，不能将前面的中间结果当作最终保留证明。

校验工具首次使用大字典逐名查找/比较，完整设计中开销过大。两次仅停止本任务自己的离线Vivado进程，保留停止日志；未把未完成检查记作通过，也未操作板卡。用相同路线样本定位后，改为一次扫描及Tcl数组查表，校验范围、逐项比较与拒绝条件不变。第三次局部实现使用`assemble_linear.tcl`。

已恢复原项目既有GP/HP寄存器时序例外，并对三组FAC1 mailbox重新施加原8/20ns数据延迟与bus-skew约束；最终还需审核FAC1/JPEG共6组mailbox路径保持有限且正的裕量。未通过新例外掩盖待修路径。

## 布线后的拒绝结果

`assemble_linear.tcl`的布局阶段完成，`placed.dcp`于2026-10-22 01:59:36保存。随后`route_design -preserve -directive Default`执行完成，日志记录耗时2分42秒、0 Error和0 Critical Warning。范围外116967个单元的位置/类型复核仍一致。

但最终范围外ROUTE比较在`User_Ddr_awwdata[271]`上发现第一处文本记录差异，脚本按既定拒绝条件退出1，工具于02:02:22结束。当时（02:02）已无该轮Vivado后台任务；下午的恢复构建另记如下。

这只证明该网络的ROUTE记录不一致，尚未比较实际节点、PIP和端点；不能判断是记录表达变化还是实际物理路径变化，也不能直接认定DDR功能损坏。检查遇到首个差异即停止，因此未完成最终DDR逐网比较，不能声称只有这一条差异或DDR已全部保留。

完整时序、DRC、bus-skew报告及最终routed DCP的写出均安排在该门槛之后，因此本轮尚无这些最终产物。没有绕过门槛生成bit或打包BOOT。已保留`assembled.dcp`、`placed.dcp`和原始日志；失败后的最终内存状态没有另存DCP，后续须从`placed.dcp`重新布线并在比较前先保存标注为unverified的检查点，以便导出全部差异。对话中断后只读核对了上述结果，未重启新构建或操作板卡。

## 下午恢复：固定路线顺序与冲突修复

从`placed.dcp`检查发现，包括`User_Ddr_awwdata[271]`在内的已登记网络`IS_ROUTE_FIXED=0`：保护曾在读取incremental参考之前设置，后续导入清除了固定标志。因此原日志中的“已固定”只表示设置曾执行，不能证明布线时仍生效。

`refreeze_route.tcl`在最后一次导入之后重新施加保护，确认95460条可布线信号已固定，另外38129条为空路线或仅站内连接，保存`refrozen-placed.dcp`。重新布线明确报告固定路线与现有单元引脚冲突。另一次诊断重跑也报告DDR路线与人脸`write_request/m_data_reg[196]/Q`冲突。两轮都出现反复绕线，分别核实并只停止本任务的离线进程；未在板上执行构建或停止正式服务，没有把未完成的布线记为通过。

`fixed-conflicts.json`汇总已报告的17组冲突（包含不同轮次及恒定网络终端），不能当作穷尽清单。局部迁移规划先检查冲突站点中的全部人脸单元，再沿专用CI/CO[3]连接扩展完整CARRY4链；正确规划涉及21个站点、70个单元。试算发现，避开所有静态信号路线的空站点无法容纳完整链，避开DDR路线可放置，但会增加迁移距离。

实际选择更小的修复：保留进位链及其他人脸单元，只迁移DDR冲突站点中的4个mailbox寄存器，目标为空的`SLICE_X119Y188`，该目标站点不落在已登记静态信号路线经过的tile内。对明确报告冲突的非DDR网络，布线前冻结有限例外清单；DDR及所有时钟不允许加入例外。全局GND/VCC树解除旧末端并重布，其他静态路线保持固定。`repair_chain_route.tcl`记录迁移及例外，布线后先保存unverified检查点和诊断，再检查范围外116967个单元、178773个LUT引脚绑定、26547条DDR路线、共享时钟路径与所有未获例外的静态路线。当前正在执行，尚无放行结果。

规划脚本首版因沿恒定网络和非专用进位输入扩展过宽，生成的1696单元方案明确标为`chain-repair-overexpanded-not-used.tcl`，未用于布局或布线。随后排除恒定网络并只沿CI/CO[3]扩展，得到上述70单元备选；最终实际修复仍只移动4个寄存器。

恢复脚本还遇到三项实施问题，均保留日志：整片重新设置`IS_BEL_FIXED`被工具以A6资源已占用拒绝，改为直接比较所有非目标单元的位置；初版只从`protected_routes`挑选冲突网络得到8条，遗漏不在该集合里的模块接口固定路线，随后从全网表按已报告名称核对，冻结24条非DDR信号，其中8条属于原静态路线检查集合；逐别名读取/清空GND/VCC的完整路线字符串开销过大，两次仅终止本任务进程后修正。最终按本机Vivado2018.3的`help route_design`核实，`-physical_nets`仅操作逻辑0/1网络，改成解除所有逻辑常量别名的固定标志、清空顶层常量约束，再一次性解除物理常量树。`help_route-console.txt`保存工具帮助原文。这些是构建脚本问题，不是板端死机或模型编译。

关键本地证据为任务目录内`placed-net-fixed-study.txt`、`refreeze-proof.txt`、`fixed-conflicts.json`、`chain-plan-summary.txt`、`repair_chain_route.tcl`及对应日志。下午过程没有生成新bit/BOOT，也未改变板上启动分区。

## 修复后首次完整报告（14:56）

`repair_chain_route.tcl`已将`m_data_reg[214/196/182/179]`从`SLICE_X116Y166`移到`SLICE_X119Y188`，其他116967个范围外单元及178773个LUT输入绑定在迁移后仍一致，保存`chain-repaired-placed.dcp`。GND/VCC有1543个逻辑别名，通过物理常量树一次解除后处理完成。重新布线用时4分25秒，未再报告之前的固定引脚冲突，命令返回成功；这不等于连接、时序验收通过。

先保存`chain-routed-unverified.dcp`再生成完整报告。最终WNS=-0.401ns、TNS=-34.200ns（170个setup失败终点），WHS=+0.004ns、THS=0；继承的NPU脉宽警告仍为-0.409ns、2个终点。104874条应布网络中104865条完整，另9条是antenna/island残枝：`pl_ra_awdata[12]`及`icore_post.awwdata[0/2/6/8/12/14/18/19]`。因此该轮不可生成放行位流。原始报告保留为`first-route-*.rpt`。

最差建立时间路径从人脸`cfg_reg[6][4]`经`allocation_end`的DSP乘加、参数检查和高扇出CE到`sampler/sy_reg[35]`等寄存器，14级逻辑，数据延迟10.105ns（逻辑5.238ns、布线4.866ns），10ns时钟要求未满足。未据此声称视频压缩或像素搬运变慢。

布线后严格LUT引脚比较发现73个静态LUT的74个输入脚被工具重新映射。`finish_route.tcl`进一步核对这些改变的输入网络均不属于DDR网络；后续必须对比底板的逻辑INIT并复核所有DDR路线，而非仅凭“引脚改了”认定功能错误。初设64个单元的审计范围上限不够，在完整统计73个后调整为96，保留首轮拒绝日志。对未事先允许但ROUTE文本不同的静态网络，先收集全部差异，最终与底板逐项比较实际节点、PIP和逻辑端点；只允许表示变化，不接受未说明的物理改线。

正在从该unverified检查点清理9条已知非DDR残枝，并尝试在失败的GP路径组内仅做critical-pin和routing优化；不使用克隆、重定时、改时钟或新时序例外。后续结果另记，不能把进行中的修复视作通过。

14:55:51再次只读观察板端（`board-during-offline-repair.json`）：启动ID仍为`8f360a28-0740-4d81-a13f-379a20faf47e`，无`/download.bit`，识别health和摄像头stream均为ready；1秒采样间隔的captured计数从1548761增加至1548792。这是采集计数变化，不是NPU完成帧率；PAD状态仍为`not_evaluated`。未部署新位流或修改启动分区。

## 路线清理、局部优化及别名处理（15:24阶段）

`finish_route.tcl`从已保存检查点继续核对，首先确认26547条DDR路线文本均与底板一致，既有静态时钟节点也保留。仅做critical-pin/routing的GP路径优化把WNS从-0.401ns改善到-0.167ns；没有增删单元。`-preserve -directive Explore`在本机2018.3被明确拒绝（虽然通用帮助说明两类选项可组合），检查点和诊断已保留；随后`finish_route_resume.tcl`使用不混用该组合的Explore继续。

Explore最终完整报告为WNS=-0.098ns、TNS=-0.786ns、8个setup失败终点，WHS=+0.004ns、THS=0，继承的脉宽警告不变。原9条antenna残枝消除，但新reader的`cache_word_x`仍有4个`cache_pitch_reg[29/30/6/8]/CE`未接通，应布104874条中完整104873条。该轮仍不放行。中间曾显示更差的hold估计，但完整报告保持时间通过，不能把中间估计当作最终结论。

该阶段范围外单元及已登记静态时钟节点检查通过；引脚重排扩大到117个LUT、157个输入，超过当时96个单元的审计上限而停止。新增的这部分未完成DDR输入归属及真值表核对，不能套用前一轮73/74的检查结果。`explore-*.rpt`保留阶段报告。

进一步发现同一条物理信号有多个层次网络名。只按一个别名解除固定约束/登记例外不完整；当前恢复脚本通过`route_alias_helpers.tcl`展开完整网络段。起始27条物理信号对应141个别名段，不能把141段当作141条独立物理线。加入9条已知清理网络后，再次展开并统一解除这些已批准非DDR信号的所有别名约束；展开时逐段拒绝DDR/时钟交集。此前8条未登记静态路线文本差异仍需在最终物理比较中判定，不能提前认定都是表示变化。

关键负裕量CE网络已定位为`sampler/x[15]_i_1_n_0`和`y[15]_i_1_n_0`，各112个负载。尝试`-force_replication_on_nets`时，工具明确表示不支持post-route模式，未发生复制；保存`replicate_control-unsupported-force-console.txt`。恢复改用本机帮助列明的post-route `-critical_cell_opt`，保护全部非LUT原语，只允许组合控制逻辑优化，并在启动优化前保存`control-ready-placed.dcp`。保留已有完整HP/GP时钟路线及全部寄存器位置，不改变时钟频率或添加时序例外；实际优化结果待记录。

最终审计将对改变映射的静态LUT逐个比较底板的INIT及逻辑输入连接，实际DDR输入映射不允许变化。审计范围上限仅为构建保护，不是硬件安全阈值：在完整统计后扩为512个LUT/2048个输入，真正拒绝条件仍是DDR/时钟交集、逻辑真值表或连接变化、未说明的静态物理改线、连接不完整或时序失败。

## 连接及物理保留闭合（15:44阶段）

`replicate_control.tcl`按完整物理网络展开36条批准的非DDR信号（156个层次段），统一解除所有别名上的约束；不再只处理某一层网络名。HP/GP完整时钟树在寄存器位置确定后固定，禁止后续改变其任何节点或PIP。通过工具支持的post-route `-critical_cell_opt`增加1个LUT，全部非LUT人脸原语名称、类型、LOC/BEL未变；控制驱动清单保存在`control-replication-drivers.tsv`。

随后Default保留布线完成，完整报告：104875条应布网络全部完整连接，0条routing error；原9条残枝及`cache_word_x`的4个CE未连问题均消除。WNS=-0.166ns、TNS=-7.962ns（104个setup失败终点），WHS=+0.004ns、THS=0；建立时间仍未通过，不可放行。

本阶段完整物理保留检查通过：116967个范围外单元未移动或改类型；133589条静态路线逐项核对，25条变化均在36条批准的物理网络范围内；26547条DDR路线原样保留；完整HP/GP时钟节点及PIP相同。检查178773个静态LUT输入映射，112个非DDR输入发生映射变化，对应112个LUT；关闭候选后重新打开已验收底板，逐个比较这些LUT的INIT及全部逻辑输入网络，均一致，改变的输入与DDR交集为0。这是物理映射与受影响逻辑的具体核对，不是整片形式等价证明。

证据保存为`control-closed-preserved-routed.dcp`、`control-closed-preservation-proof.txt`、`control-closed-*.rpt`。当前从此点尝试GP路径组内的LUT位置/引脚/路线优化；全部非LUT人脸单元固定LOC/BEL，完整时钟仍固定。不会把前一阶段保留证明直接用于新检查点：开始新阶段前先归档并移除旧proof，位流门槛也检查proof不得早于对应DCP。尚未生成bit或BOOT，未操作启动分区。

## 当前产物与下一步

任务目录的关键入口与证据：

- `input-manifest.json`、`school-preflight.json`、`board-before-readonly.json`。
- `stage.py`、`staged-sources.json`、两份RTL补丁、`post-synthesis-source-audit.json`。
- `synthesize.tcl`、`full-synthesis-utilization.rpt`、`candidate-face.dcp`、`face-native.dcp`。
- `export_contract.tcl`、`prepare_native.tcl`、`compare_interfaces.py`、`interface-comparison.json`。
- `candidate-simulation/verification.json`及8组原始日志。
- `export_reference.tcl`、`preservation-reference.tcl`、`clock-pruning.json`、`clock-pruned.tcl`。
- `preservation_helpers.tcl`、`assemble_linear.tcl`及其原始日志；两个停止的旧检查日志另存。
- `assembled.dcp`、`placed.dcp`：中间检查点，不能作为已通过最终门槛的位流输入。

后续`optimize_lut_placement.tcl`完成，最终WNS=-0.069ns、TNS=-1.564ns、58个setup失败终点，WHS=+0.004ns、THS=0；继承NPU脉宽警告不变，物理保留检查通过。此前待核对网络已包含在上述最终审计中，不再作为未完成事项。旧版RTL仍未满足建立时间，停止继续调整其布局，未生成bit/BOOT。新阶段改为拆分过长的命令校验逻辑，见[PL命令校验流水化](pl-command-validation-20261022.md)；该新RTL必须重新完成自己的整板验证，不能继承本候选的通过结论。部署与DDR/像素/模型/持续SDI实测尚未开展。
