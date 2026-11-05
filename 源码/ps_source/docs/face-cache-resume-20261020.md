# 双行缓存增量实现续查（2026-10-20）

**结果：新位流已部署并通过两次正常重启回归，最终接受，照片测试服务正常。人脸裁图预处理暖运行耗时降低约40%，双行双线性用例降低约42%。**
上述性能范围是FAC1启动至输出读回/普通文件写入，不是模型或开锁端到端延迟。真实SDI采集与防照片攻击尚未验收。

本轮承接[10月18～19日的保留实现记录](face-cache-preservation-20261019.md)，处理人脸缓存单元与DDR固定实现的布局/布线冲突，不添加模型、前端或编排功能。
任务目录为`D:/yzd/tmp/face-cache-resume-20261020`。以原始日志日期归档，不将本次工作补记为10月19日。

## 输入与现场

- 输入为上一轮的`ddr-pin-restoration-preview.dcp`，文件SHA256记录在本任务`input-manifest.json`。
- 输入已经恢复12个原DDR LUT引脚映射，但含8条错误网络及25条主动释放的待布网络，不能作为位流生成输入。
- 后台读取了`D:/xiangmuwendang/WCIS-FPAI/wiki/SOP/bitproc.md`和`todo/PS-PL_AXI_HP口与复位语义.md`。后者是项目资料对厂商说明的转述，本轮没有重新核验其原始PDF，不把转述升级为新的硬件实证。
- 本轮只运行本机Vivado FPGA实现；尚未开展模型或AArch64构建。
- 本次板端只读检查保存在`board-state-20261020.json`：启动ID仍为`e9983c3a-858a-4aa9-be4d-7af946632243`，照片测试服务ready，当前无隔离标记，硬件锁可取得，`camera_input=false`。这不是新缓存板测。

00:27左右在同一原版启动上重新完成对照验证：4组SDK分配范围内的DDR写读均零错误，CustomOp未启动；
8组FAC1输入各运行11次，共88次像素输出与独立参考一致，原帧完整读回一致；公共Biden照片成功输出12个检测张量和1个特征张量，结果为未登记身份unknown，未修改人员库。
对照文件为`memory-probe-before.json`、`before-verification.json`和`face-before.json`。
预处理暖运行中位数为：1080p检测输入56.746867 ms、人脸裁图10.392906 ms、双行双线性用例1.156812 ms。
这些是原版FAC1启动至输出读回/本地写文件的用例结果，排除设备打开、会话建立、源帧上传与校验，不能当作整个人脸识别延迟或新缓存加速结论。
原版BOOT快照SHA256仍为`e472e96cdf7ce6d82d1f278fda0240b68580e71558c031045210f844865d629b`，DTB与uEnv快照一并保存在本任务。

## 修复过程与验证边界

上次清除BEL固定属性时，目标仍处于有切片资源冲突的原位置，工具报`Cannot use A6 pin since it is in use`。
本轮将操作顺序改为先解除位置固定、执行`unplace_cell`，再清除BEL固定属性，随后尝试将6个寄存器放入各自空闲切片。
00:03左右该步骤实际完成，退出码0：6个寄存器均从`SLICE_X99Y60`移至空闲切片，逐项核对其余全部非恒定原语的名称、类型、LOC及BEL一致。
结果保存为`cache-six-moved-placed.dcp`和`cache-six-register-moves.tsv`。这证明迁移步骤完成，尚不证明布线或时序通过。

任务初始化时曾因Windows路径分隔符替换未匹配而启动旧目录的脚本，发现后只停止该任务自己的Vivado进程，修正为规范路径后重启；未改板端。
后续产物均写入本轮独立目录。

为迁移寄存器导出当前GP时钟实际PIP图，保留其余负载到源的完整路径。
项目工具`scripts/prune_clock_routes.py`检查通过：12541个节点保留12539个，删除2个仅通向目标旧位置的节点，保留4515个其余负载节点。
该结果为图结构检查，仍须由原生布线和静态路径复核确认。

选网交互式布线的第一轮未通过：固定DDR原路线、迁移6个寄存器后，工具仍报告13条网络未布通、17处节点重叠，
并指出`SLICE_X99Y59`内人脸数据LUT输入存在重叠。工具明确警告`-auto_delay`只适合已有布线很少的状态。
本轮不能把它算作完成布线，也不能将工具估算的WNS -5.173 ns作为最终时序报告。
失败检查点为`route_six_cache_registers-failed-unverified.dcp`。

随后从迁移完成、尚未经过该次失败路由的检查点重开，保持相同6个寄存器位置与DDR原路线约束，
改用`route_design -preserve -directive Default`复核默认增量路由，不追加其他单元迁移。
该任务为`route_default_preserved.tcl`，实际结果以下列状态及原始日志为准。

默认增量路由在预清理与初始验证阶段给出了17个不同的`Route 35-341`告警：固定DDR路线与人脸引脚直接冲突，
明确标为unroutable。这说明“仅移动原6个寄存器就足够”的假设不成立；它仍不是此前板上DDR错误根因的证明。
为避免继续无效迭代，停止了本任务该路由进程，没有最终完成标记或最终时序报告；保留原输入与诊断日志。
`fixed-pin-conflicts.json`及`.tcl`保存去重后的17条冲突和日志哈希，此清单不声称穷尽所有潜在冲突。

接着按这17个原切片收集全部人脸原语，共113个，组成17组，保留各组原BEL相对布局，
查找同类型空切片，并排除其引脚节点已由DDR网络占用的目标位置；DDR及其余原语不得随迁。
目标包含寄存器、LUT及复用器，不能将113个统称为缓存寄存器。
迁移源仍为清洁的`cache-six-moved-placed.dcp`，没有采用失败路由留下的中间状态。
相关脚本为`move_conflicting_face_sites.tcl`和`route_conflict_sites_preserved.tcl`。
更新GP时钟图只剪去已迁移负载独占的末端：12541节点保留12494，删除47节点，保留4500个其余负载节点。

第一版113单元迁移完成，其余原语位置与类型核对一致；后续默认路由不再报告原17条冲突，
但新目标`SLICE_X111Y29`内的MUXF7选择端仍与DDR的`switch_start`固定路线冲突，故停止继续迭代该路由。
这暴露出目标筛选的遗漏：单元空闲、外部引脚节点无DDR占用，并不能排除切片内部资源被固定路线占用。
随后对同一批113单元采用更严格目标筛选：导出原DDR信号路线覆盖的全部tile，排除这些tile中的空切片，
同时检查已知失败目标所在tile确实被排除；共享HP时钟另按原静态路径保护，不用它作为全局tile禁区。
该版本为`move_conflicting_face_sites_tileguard.tcl`：原生导出排除了14183个DDR信号路线tile，
已知内部MUX冲突所在tile覆盖检查通过。113个单元重新分组放置完成，其余全部非恒定原语的名称、类型、LOC和BEL一致。
保存到`cache-site-moved-placed.dcp`后，重新执行相同的默认增量路由；此前仅按外部引脚筛选的失败诊断保存在`route-site-pinonly-stopped-console.txt`。

## 当前结果

同一批113单元的整tile避让迁移完成。默认增量路由完成，最终连通性报告为104649个可布网络全部布通、错误0。
路由工具估算setup WNS -0.031 ns、hold WHS +0.002 ns，但随后最终`timing.rpt`及原生时序路径查询为
**setup WNS +0.005 ns、hold WHS +0.004 ns、TNS/THS均0**，估算值不能替代最终签核模型结果。
原版已有2处NPU脉宽告警仍在（最差-0.409 ns），本轮没有消除它们；建立/保持门槛通过不等于量产时序签核。
116930个受保护静态原语名称/类型/LOC/BEL核对一致，18只原静态时钟路径节点及负载保留，
HP 32492个和GP 9253个原静态PIP均保留。
00:36～37左右DDR保留门槛通过：26547条非共享信号ROUTE与原版逐项一致，19676条跨切片路线显式固定，
6871条为切片内部或空ROUTE记录；共享HP时钟保留原静态节点。之前恢复的59条路线另核对实际节点与PIP集合一致，12个原DDR LUT引脚映射保留。
结果保存为`preserved-routed.dcp`与`preservation-proof.txt`，原生任务退出码0。
最终接口/约束审计通过：第二缓存银行512个寄存器，未混入公平仲裁；37个CSR读返回复用器身份/类型一致；
6组mailbox分别保持8/20 ns最大延迟要求，均为有限且正的裕量；5个DDR校准控制器输入连通。
最终检查点上的初始6个及分组113个迁移位置均与记录一致，113个目标均位于DDR信号禁区tile之外。
位流生成完成，BOOT打包验证FSBL、BL31及U-Boot三段与原版逐字节一致，PL段与新bit有效载荷匹配。

## 位流与板端试启动

- 新BOOT SHA256：`f48397d08b1ccb1c950adafcebe5e36678154e73fa1d19792150aa5ddccd8ad1`。
- 处理后的bit SHA256：`710c96b3fee92037e1f3dd1f3354689ef3389b37c378813c03405905c0811f09`。
- 保留原BOOT备份`CPR1020.BAK`，试启动期间启用独立240秒回退定时器；这依赖Linux能够启动，不等于断电或完全无法启动时的恢复保障。
- 第一次新启动ID：`4e9dfe39-e7b3-4d03-9ea3-b776d19c0827`。
- 第一次回归通过：4组有界DDR写读零错误（CustomOp启动前）、88次像素比较及原帧读回一致、模型13个输出与原版一致、RGB565/BGRX各2帧JPEG解码/计数/源校验通过且编码字节与原基线一致。
- 第二次新启动ID：`809c6b12-c379-4216-88eb-dba4e113da57`，完成相同回归并通过。两轮合计176次专用像素比较；各轮4组有界DDR写读零错误，13个模型输出一致，JPEG编码字节与原基线一致。
- 并行脚本首次因全局配置仍记录原版启动确认号而拒绝执行，尚未启动硬件。为本轮测试复制独立配置，仅在两轮回归通过且当前启动号一致后写入副本的确认号；保留原脚本的启动、隔离、应用文件及模型校验，不提前更新全局确认号。
- 使用已校验SHA的原并行检查器，仅替换其配置读取路径，在本任务目录运行副本；复用学校已构建的原二进制，未重新编译或改动共享候选目录。
- 随后1组串行/重叠配对覆盖YuNet和MobileFaceNet，共4次命令通过，2次重叠均取得卷积输出ready时JPEG仍busy的原生证据，NPU输出、JPEG字节、完整原帧及正常退出核对通过。这是有界并行回归，不是新的长期吞吐基准。
- 全部通过后执行最终接受：核对SD中新BOOT、原DTB/uEnv、原服务单元、人员库、应用文件和实时FDT；更新已验证启动号，关闭本轮回退定时器。
- 接受后只读核对通过：当前启动为第二次新启动，照片服务active/ready，无当前隔离标记，硬件锁可取得，回退定时器disabled；人员库、应用文件、服务单元和实时FDT均与本轮开始时一致。

记录依据为`timing-gate.json`、`hardware-audit.txt`、`boot-candidate/manifest.json`、`deployment.json`、
`first-round-proof.json`、`second-round-proof.json`、`parallel-after-verification.json`、`accepted.json`和`final-verification.json`。

## 实测效果与限制

每个用例每次启动运行11次，第一轮作预热，其余10次取中位数。完整8用例数据及各输入/输出哈希在`performance-comparison.json`。

| 用例 | 原版 ms | 新版第一次 ms | 新版第二次 ms | 耗时变化 |
|---|---:|---:|---:|---|
| 人脸裁图 `face_obama` | 10.392906 | 6.229060 | 6.239180 | 降低约40.0% |
| 双行双线性 `two_row_bilinear` | 1.156812 | 0.669710 | 0.669770 | 降低约42.1% |
| 双行且更换源帧 | 1.165738 | 0.670285 | 0.667365 | 降低约42.5%～42.8% |
| 1080p检测输入预处理 | 56.746867 | 56.347845 | 56.298715 | 变化不足1%，不据此认定明显加速 |

计时排除设备打开、源帧上传/校验、fsync及后续NPU/权限/开锁过程，不能把约40%的裁图耗时下降写成整个人脸识别或门锁延迟下降40%。
本轮没有硬件DDR请求计数器，不能由这些耗时倒推出实测读取次数减半。
两次正常重启不等于断电冷启动、全2 GB DDR容量扫测或长期稳定性签收；本轮DDR范围为SDK分配的有界缓冲区。
新位流只接受双行缓存，公平仲裁与PAD裁图未混入；`camera_input=false`，普通SDI防照片/手机回放仍没有新增验收证据。
此前整片候选DDR错误的根因仍未确定。本候选保留原DDR实现后通过预检，是本候选的验证结果，不能改写10月18日失败记录或直接证明其根因。

## 关键来源

- 本任务`move_six_cache_registers.tcl`及其日志、`cache-six-gp-graph.tcl`、`cache-six-gp-pruning.json`。
- 上轮`ddr-pin-restoration-preview-route-status.rpt`、`ddr-original-pin-reference.tcl`。
- 本任务`board-state-20261020.json`。
- `move_conflicting_face_sites_tileguard.tcl`、`ddr-forbidden-tiles.tcl`、`route_conflict_sites_preserved.tcl`及最终原生报告。
- `audit_and_generate.tcl`、`build-input-proof.json`、`timing-gate.json`。
- `check_parallel_after.py`、两轮回归证明、`performance-comparison.json`、`board-state-accepted.json`及`final-verification.json`。
