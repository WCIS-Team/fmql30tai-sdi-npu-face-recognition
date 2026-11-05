# 双行缓存：保留原版静态实现的增量替换（2026-10-18～19）

截至2026-10-19 16:03（Asia/Shanghai），本轮停止追加试探性离线修复：路由、setup/hold、静态位置及静态时钟检查曾有通过结果，
但同一候选未通过DDR路由保留检查；恢复DDR原实现的后续版本也未完成验收。**没有部署新的位流或BOOT，没有新缓存的板上性能结论**。
此前整片重建候选的DDR预检失败及回退事实保留于[原试验记录](face-cache-board-20261018.md)。
该次DDR错误根因尚未确定；本轮验证“仅替换人脸模块、保留其余实现”的路线，不把实现差异直接当作根因。

独立任务与原始证据：`D:/yzd/tmp/face-cache-preserve-20261018`。
工作日期按产物、日志及板端验证记录划分；跨午夜的工作分别归档，不能全部记为10月18日。
本地补充来源为`D:/xiangmuwendang/WCIS-FPAI/wiki`下的`SOP/bitproc.md`、
`SOP/BOOTbin位流替换手术.md`、`todo/PS-PL_AXI_HP口与复位语义.md`及厂商时序基线说明。
这些文档为背景材料；实际器件、工具、地址映射及部署判断仍以本工程与实测为准。

## 2026-10-18：建立可替换边界与原版复现基线

### 实现方法与遇到的问题

以已经过板测的`D:/yzd/tmp/pl-jpeg-board-20261016/jpeg-board-routed.dcp`为底板，
从缓存候选中提取原生模块DCP，避免再次重建DDR/NPU/视频/JPEG整片电路。
缓存RTL仍为`wcis_face_customop.v`的双64字节行缓存版本，SHA256为
`d9cd41923dffaab3e3f48e4a38f02449b90079f45b34e56719acb501a35f54bf`。
本轮没有混入公平仲裁或PAD裁图，也没有修改前端、编排层、模型和板卡管脚。

最初尝试替换整个`U_adder_top`，两版均有1876个边界引脚，但两对输入名因综合优化而不同。
对公共寄存器切点、LUT真值表及输入顺序进行结构比较，51项组合锥一致后才允许映射。
EDIF导出再导入会把转义标量引脚误读为总线，改用原生DCP；解除原生布局时先unplace再清BEL固定属性，
避免LUTRAM位置约束冲突。这些是受限结构检查，**不是整片形式等价证明**。

用原版完整布线DCP直接生成bit，设置原版USERID `32'h53180205`并执行厂商`disableICAP`后，
原版与复现版的5,980,460字节配置有效载荷逐字节一致，差异0；bit头中的生成日期不同。
这证明本轮找到的离线生成路径能复现原配置，不等于新模块已经上板。

### 原位流基线与边界

在回退启动`e9983c3a-858a-4aa9-be4d-7af946632243`上取得新的对照材料：
有界DDR写读4组零错误；8组输入、每组11次，共88次FAC1预处理与独立像素参考一致，原帧读回一致；
公共测试照片的12个检测张量及1个特征张量SHA保留为NPU对照。没有修改正式人员库。
这些结果属于原位流，不能标成新缓存验收。

### 关键证据

- `boundary-equivalence.json`、`native-ports-verification.json`。
- `baseline-identity-reproduction.json`、原版及复现bit。
- `board-before.json`、`board-state-before.json`、`memory-probe-before.json`。
- `before-verification.json`、`face-before-summary.json`。

## 2026-10-19：缩小替换范围，定位共享时钟旧分支

### 面向人脸模块的替换

整个CustomOp替换涉及JPEG布局，进一步缩小为`U_adder_top/face`。
两版有1617个公共引脚；候选额外输入`wr_owner_reg_0_repN_alias`来自复制的LUT3。
核对INIT `8'hB8`及三个有序输入切点，与原版已有`choose_wr`组合信号一致，才连接这个输入。
两只时钟输入也通过5个公共寄存器角色核对，未发现GP/HP时钟口互换。

原生人脸DCP SHA256：`8edae71cbf3fe74f3dd24b4c3087edccff4381a13a0d7b2ad49d6044dd603db6`。
静态保护对象为116930个非恒定原语，逐项比较名称、类型、LOC与BEL，包含原DDR、NPU及JPEG。
仅允许外部CSR读返回树的37个MUXF7/MUXF8重新放置，相关108个非恒定网络允许重布；与DDR网络交集为0。
全局0/1恒定网络另行释放重布，不能描述成“所有旧布线逐节点不变”。

人脸模块使用原版作为增量参考，复用报告列出8311个复用单元、1117个新增单元、426个非法位置被放弃；
426是工具另列统计，不能直接当作第三个互斥类别相加。
保存的增量布局检查点中，116930个受保护静态原语的位置、类型保持一致。

### 布线冲突与解决方向

最初保留全部旧时钟节点，导致新模块无法使用旧人脸模块已经闲置的时钟末端。
完整布线报告存在3个错误网络：两只共享时钟有引脚冲突、未布通及悬空分支；另有一个NPU控制网天线。
试移6个寄存器及2个相伴LUT后，报错寄存器名称改变，但仍落在相同6个共享Site CLK位置；
报告中的Antenna Nodes进一步确认，继续逐个移动寄存器不能消除旧分支冲突。
这些失败检查点均未进入位流生成或部署。

一次按5183个旧目标独占时钟逻辑引脚执行原生清理的任务，在运行中断后没有完成标记或检查点；
不能当作清理成功。改为导出原版实际PIP图，并检查每只时钟均是一棵单源树：
定向PIP方向必须正确，双向PIP按唯一的源到负载路径定向，拒绝环、多父节点和未连接负载。
对全部静态时钟负载回溯到原时钟源，只保留这些原有路径。

| 时钟 | 原节点 | 保留节点 | 删除的旧目标专用节点 | 静态负载节点 |
|---|---:|---:|---:|---:|
| `hp_clk` | 33082 | 32493 | 589 | 12431 |
| `ps_clk_out` | 12049 | 9254 | 2795 | 3261 |

图结构检查通过，不代表工具已接受重建的FIXED_ROUTE，也不代表硬件稳定。
后续必须核对：全部静态负载及原路径保留；其余16只全局时钟保留；26547个非共享DDR信号网络布线完全一致。
共享HP时钟仅放弃通向被替换旧模块的专用末端，这与最初“连闲置旧末端也全保留”的条件不同，明确记录此变化。
另一个NPU控制网络只允许在DDR交集为0时单网重布，不允许重放置NPU逻辑。

14:47的最终路由报告已为0错误、104649个可布网络全部连通；时序仍有2个建立违例，
最差-0.118 ns，hold为+0.004 ns，因此本版被验收门槛拒绝。
违例位于原视频缩放数据寄存器到写FIFO BRAM的路径，不能因为本轮未验收SDI就加例外掩盖它。
后续仅尝试重布该路径1～2个非DDR数据网络，保持单元位置、时钟及DDR内部网络保护；
不得将尝试中的单网修正写为已经完成的时序闭合。

清理方法已整理为项目工具`scripts/prune_clock_routes.py`，解析Tcl列表数据而不执行输入中的Tcl命令。
`tests/test_prune_clock_routes.py`的6项检查覆盖保留共享主干、删除旧专用分支、双向PIP定向、
拒绝反向定向PIP、拒绝断开/成环/缺失负载及输入数据不执行命令。
工具用实际原始导出重新生成的参考SHA为`171888bc2e6eb7340c8dc8cbf87c1facb495116684f304166c87c22f6308d23e`，
与本轮原参考逐字节一致。工具输出仍需原生CAD检查，不能独立生成可部署结论。

14:55，只重布`frame_to_ps_inst0/ch0_write_data[15]`一条数据网络的最短路径版本，
最终路由错误0，WNS +0.005 ns、WHS +0.004 ns，TNS/THS均0。
此前自动延迟模式的两次尝试反而变差（-0.159/-1.422 ns），已拒绝，未进入打包。
静态116930个单元名称/类型/LOC/BEL保持一致；18只静态时钟的既有路径、静态负载均保留，
另核对HP 32492个、GP 9253个原静态PIP连接开关，均保留。

随后逐网DDR检查拒绝该版本：59条非恒定网络的ROUTE与原版不同。
进一步打开原版与候选，实际比较节点、PIP、驱动端与接收端，结果为：**59条均有物理路径变化，
端点均相同；不是文本顺序差异**。涉及读/写数据、校准逻辑等，不能只称作外部接口变化。
这59条网络的IS_ROUTE_FIXED在两份检查点中均为0；静态位置保护与原有保留命令并没有确保这些路线被冻结。
该发现解释本轮保留门槛失败，仍不能据此断言它是此前整片候选DDR板测失败的根因。

恢复原路由资源前的所有权查询，找出23条占用网络：18条在人脸模块内，另5条为明确命名的NPU/JPEG/视频数据网络。
后续尝试只重布这23条网络、不移动逻辑单元，并显式固定非共享DDR信号路线。
恢复后仍有47处资源重叠，已停止重复不收敛的离线路由，改为导出冲突及引脚映射；尚未形成通过版。
一次恢复脚本生成时发生变量被外壳展开的问题，已在离线检查中发现并停止相应任务，直接修正脚本，未涉及板端。

以上证据分别在`repair_sdi_shortest.log`、`sdi-shortest-routed-unverified.dcp`、
`ddr-route-difference-analysis.json`、`ddr-route-physical-differences.tcl`、
`ddr-restoration-blockers.tsv`及`preview_ddr_restoration.tcl`。不得把unverified检查点作为部署输入。

### 原有时序例外的恢复与限制

替换对象后，原版基于寄存器对象列表的跨时钟例外没有自动覆盖新对象。
恢复前先核查原版实际生效结果，而不是仅凭XDC文本增加豁免：
原版一条legacy GP→HP路径为False Path、slack为inf；同域复位恢复检查为+4.217 ns。
重新施加原版`case/constrs_1/ai7030.xdc`第13～16行后，两份完整路径正文均保持一致。
因此恢复这4条已有命令，同时保持6组mailbox数据捕获的独立延迟约束和可见性。
该核查覆盖代表性路径，**不是全部CDC安全签收**，也不消除既有NPU脉宽告警。

### 当前状态与后续验收

进一步核查2011个逻辑引脚，发现12个LUT的23处物理引脚绑定发生变化，尽管单元位置、类型和INIT一致。
将这12个LUT作为一组解除放置、恢复原引脚映射后，重新放回原LOC/BEL，原映射恢复完成；
但后续选网布线仍报告17处重叠，不能据此认为DDR保留问题已解决。

最后的离线预览检查点`ddr-pin-restoration-preview.dcp`保留原DDR引脚映射，
报告8条错误网络，涉及`SLICE_X99Y60`的DDR输入及同位置6个缓存寄存器的时钟、复位和数据连接。
该检查点还主动释放了25条待重布网络，属于中间态，不是可生成位流的结果。
“缓存寄存器与原DDR引脚在切片内资源上冲突”是本轮定位方向，尚未经过修复成功验证，
更不能当作此前整片候选板上DDR错误的确定根因。

最后仅尝试迁移这6个缓存寄存器；脚本在清除BEL固定属性时被工具拒绝：
`Vivado 12-1405: Cannot use A6 pin since it is in use`，退出码1。
因此迁移、后续布线和最终验收均未完成。失败脚本、日志与未验收检查点保存在任务目录，
分别为`move_six_cache_registers.tcl`、`move_six_cache_registers-console.txt`和
`move_six_cache_registers-failed-unverified.dcp`。16:03确认没有本任务Vivado进程继续运行。
本轮多次扩大离线修复分支导致耗时过长，现结束这些尝试，不自动追加新的布局或路由方案。

2026-10-19 15:43～44左右只读复核：板端仍为`e9983c3a-858a-4aa9-be4d-7af946632243`，
照片测试服务ready，当前启动无隔离标记，硬件锁可取得。现有服务报告`camera_input=false`。
新候选没有通过全部离线门槛，未生成可验收的新BOOT，未进行新位流板测。
该状态证据为`board-state-20261019-1543.json`；后续16:03停止的是本机CAD尝试，未改变板端启动文件。

若以后重新开展本优化，仍须依次检查路由错误/天线/未连接为0、setup/hold、静态位置与DDR布线、打包分区一致，
再实际试启动；有界DDR预检通过后才测试FAC1像素、NPU输出及JPEG，任何硬件失败立即回退。
两次正常重启的验收不等于断电冷启动、完整2 GB DDR扫测或长期稳定性验证。
缓存优化也不能证明普通SDI摄像头的防照片效果，真实采集及PAD攻击验收仍独立进行。

### 关键本地来源与原始证据

- 项目：`rtl/wcis_face_customop.v`、`scripts/readonly_tool_guard.tcl`、`docs/face-cache-board-20261018.md`。
- 任务：`face-interface-proof.json`、`clock-port-equivalence.json`、`face-incremental-reuse.rpt`。
- `clock-pin-repaired-routed-unverified.dcp`及其失败路由/时序报告，`shared-clock-site-representatives.tsv`。
- `export_clock_graph.tcl`、`clock-graph.tcl`、`prune_clock_graph.py`、`clock-graph-pruning.json`。
- `original-exceptions-proof.json`及original/reapplied两组路径报告。
- `route_face_pruned_clocks.tcl`、`board-state-resumed-20261019.json`。

Tcl路由查询语义参考[AMD UG835：get_nodes](https://docs.amd.com/r/en-US/ug835-vivado-tcl-commands/get_nodes)，
实际调用同时按本机Vivado 2018.3帮助核对；厂商参考器件命令语义不能代替FMQL实板验证。
