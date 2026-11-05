# PL 网站预览续作（2026-10-28）

继续 `pl-preview-resume-20261027.md` 的完整分辨率 PL JPEG/UDP 预览任务，工作目录仍为 `D:/yzd/tmp/pl-preview-resume-20261027`。用户明确继续使用板卡原网站入口，不增加其他接收主机。

**本日最终现场状态（17:52 后）：用户确认后已写入并启动 fd5606055c4c 候选，但 PL PHY 身份读取失败、原识别路径触发 `Owned frame guard mismatch`。候选未通过验收，已恢复原 f6da96ab BOOT 和配置并重启；原网站 ready、960×540 PS/VPU 预览与三次真实摄像头检测请求通过，录像 off。PL 预览尚未完成；该候选禁止未经修复再次部署。** 下面早期阶段的“未写启动分区”等表述保留当时状态，不能当作当前结果。

## 已知基线与本日目标

27 日已完成 1920×1080 原生发送 SERDES 仿真、212 个 UDP 包重组和 JPEG 像素检查，本机 UDP/HTTP/MJPEG 回环通过；服务器首次回环失败。这些结果不等于实际 PL 网口、摄像头输入和网站部署验收。

旧增量构建目标已从 −0.590 ns 改为零违例，但该轮布线拥塞并于 27 日 23:03 超时，未产生完整路由检查点。28 日转为使用当前完整源码构建，补齐写帧错误同步与预览状态同步的源级集成证明；不能将旧网表 ECO 当作当前源码综合结果。

## 构建路径修复与排查

首次完整源码构建在厂商前置处理后报缺少 `D:/yzd/renlianshibie/fpga_project/constraints/fmql30tai_full_sdi_refclk.xdc`。实际约束位于当前项目 `D:/renlianshibie/fpga_project/constraints/`；缓存工程使用 `$PPRDIR/../../../../renlianshibie/...`，任务新增 `source-build` 这一层目录后，旧相对路径解析到了错误位置。

`scripts/prepare_pl_jpeg_preview.py` 已将新副本中明确指向本项目根目录的 `$PPRDIR/../.../renlianshibie/fpga_project/` 引用规范为当前绝对项目路径。只重写候选 XPR/复制的 hook 引用，不更改约束内容、板卡引脚、电平、PLL 或安装目录。修复前脚本和首次失败日志保存在任务 `originals/prepare_pl_jpeg_preview-before-relocation.py`、`build-current-source-first-attempt.log`；最新完整补丁继续由任务归档脚本生成。

随后一次工具运行在读取复制的 hook 文件时返回空错误。没有直接归因于文件损坏；独立读取与包含相同前置步骤的精确读取探针均对六个 hook 成功，分别保留 `probe_hook_io.log` 和 `probe_exact_hook_io.log`。失败日志为 `build-current-source-hook-read-failure.log`。再次启动已越过该步骤，开始完整顶层综合；该读取失败原因未证实。

`source-build/source-build-inputs.json` 冻结当前 RTL、候选源码、约束和构建脚本散列，重跑前通过 `verify_source_frozen.py` 核对。首次生成 IP 时厂商流程重建了任务副本内的 MIG；后续重跑复用其完成结果。日志中的安装数据库复制已由 `readonly_tool_guard.tcl` 识别为逐字节相同并跳过，没有写共享安装目录。

01:39:40 完整综合检查点 `source-build/preview-full-synthesis.dcp` 写出，`FULL PREVIEW SYNTHESIS COMPLETE` 与分包缓存单块 RAMB18E1 / 计数最大扇出 13 检查均通过。`build_current_source-receipt.json` 为退出 0、未超时，耗时约 302 秒。`synthesis-critical-comparison.json` 将当前与旧候选的 16 条关键警告逐项比较，消息和计数相同；该比较不能代替时序或板端审核。

本次整板综合用量为 53,965 LUT、72,273 寄存器、207.5/265 BRAM tile、24 BUFG、5/5 MMCM、4/5 PLL；不是预览模块独占用量，也不是完整布线资源报告。`bind_current_implementation.py` 再次核对源码和原生全分辨率仿真的编译源散列，将完整综合 DCP、收据、功能证明和真实布局参考绑定到 `preview-implementation-inputs.json`，随后开始完整源码布局布线。采用 25 日最佳完整检查点作布局参考，目标仍为零违例，参考不能当作已部署证明。

首次完整源码实现被状态同步器检查阻止：约束期待 `status_reg[0/1]`，实际 Vivado 2018.3 综合后的名字为 `status_reg_reg[0/1]`。`source-status-primitives.txt` 从真实综合 DCP 核对两个同步器均有两级 FDCE、初值 0、ASYNC_REG=1 和正确级间接线；未因检查失败就假定寄存器已被优化掉。

`constraints/pl_jpeg_preview_cdc.tcl` 修正为精确匹配实际综合名称，仍要求恰好两级，仅对首级 D 设置异步例外。`audit_source_status_constraints.tcl` 对真实 DCP 的检查通过：两个同步器的第二级数据和本地复位释放各自保留 min/max 检查，导出 XDC 中只有两个对应首级 D 的新增例外。此为未放置的约束审核，第二级 min 裕量仍有 −0.106 ns / −0.006 ns，不能记成时序通过。结果保存 `source-status-constraint-audit.txt`、`source-status-effective.xdc` 与成功收据。此次仅修改实现阶段约束名称，未改 RTL 或时钟，`implementation-constraint-revision.json` 明确记录旧/新散列；原综合输入记录保留，并在重新绑定实现输入后重启布局布线。

该完整源码 Explore 实现完成布局和物理优化：布局估算 WNS −0.168 ns，物理优化估算 +0.002 ns；预览接口、分包缓存和 UDP 寄存边界检查通过。实际布线出现拥塞，冲突曾从 4210 降至约 40–50 但反复未收敛，达到 3600 秒限制后停止自有任务树。`source-build/implementation-explore-timeout/` 保存该轮全部平面日志、报告、完成的布局/物理优化 DCP、输入散列及超时收据；没有完整路由结果，不算通过。

随后使用该轮真实完成的 `ai7030_edif_top_physopt.dcp` 作为新布局参考，准备并启动 Default 路由策略的完整实现。`implement_default_flow.tcl` 从当前根实现脚本派生，唯一策略变化为路由 Explore→Default，原 RTL、时钟、时序例外和最终非负时序要求不变。`default-flow-derivation.json` 与 `implementation-variant-inputs.json` 记录脚本及参考散列，重新绑定到实现输入。采用完成的物理优化结果仅为布局引导，不当作路由或部署证明。

11:23 恢复检查时，该 Default 任务已没有运行进程，日志最后写入时间为 04:06:19，末尾仍有 6 处节点重叠，没有完整 routed DCP，也没有正常结束或超时收据。中断原因尚未确定，不能记成时序通过或确定的 watchdog 超时。`source-build/implementation-default-interrupted/` 保存该轮日志、全部平面实现文件、输入绑定、脚本和 `interruption-observation.json`。

继续检查发现，前置状态报告中旧路由复用后有 5198 条带路由错误的网络；既有释放 hook 只清除共享时钟，普通数据仍保留旧路由。该现象提示尝试清除旧数据路由，尚不能确定它是拥塞的唯一原因。依据本机 Vivado 2018.3 `route_design` 命令文档，新任务脚本 `clear_fabric_routes.tcl` 在原 DDR 所有权检查后，清除非固定普通网络及物理常量网络的继承路由，并逐条检查 DDR 专用路线和固定状态原样保留；清理后要求完整路由仅剩受保护的专用 DDR 网络、路由错误为零，才允许继续。没有修改 RTL、引脚、时钟、时序例外或验收阈值。

`prepare_fresh_flow.py` 从上一策略派生 `implement_fresh_flow.tcl`，仅添加该清理 hook；使用上一轮完成的物理优化 DCP 作为布局参考，再跑完整布局、物理优化和 Default 布线。新脚本、参考、失败证据与派生记录重新绑定后，289 个实现输入散列全部一致，任务由 `implement_fresh_source.tcl` 启动；此处仍是运行状态，尚无路由、时序或板端通过结论。

11:34 新清理 hook 的首轮检查在执行普通路由清理前报 `DDR protection missing: ddr3_addr[0]`。`inspect_ddr_fixed.tcl` 读取该轮真实错误检查点，确认该地址连接属于 INTRASITE，ROUTE 与 FIXED_ROUTE 都是工具表示的 `{}`，本来没有可固定的外部路由；不是实板或 DDR 线路丢失。旧保护集合中还包含这类片内连接，新检查不应将它们当作实际固定线路。修正只排除同时满足 INTRASITE、ROUTE 无节点、FIXED_ROUTE 无节点的条目；其余 DDR 外部路由仍要求固定且清理前后逐字相同。`source-build/implementation-fresh-intrasite-check-failed/` 保存失败日志和检查点，`ddr-fixed-inspection.txt`、成功探针收据及修正后的 hook 重新绑定；293 项输入散列一致后重跑完整实现。该问题是新增审核脚本的分类错误，未修改产品 RTL 或放宽时序要求。

11:52 检查实际子任务日志确认 `FRESH_FABRIC_ROUTE_GATE_PASS PRIVATE_DDR_UNCHANGED=1143`。`preview-fresh-route-status.rpt`：116534 条可布线网络中，1143 条 DDR 专用线路保持原路由及固定状态，其余 115391 条尚未布线，路由错误为零；随后已进入 Default 正式布线。主进程日志因转发很长的命令参数而落后于子任务，后续以 `case/fpai_demo_vivado.runs/impl_1/runme.log` 的最新一轮输出跟踪进度。清理通过不等于最终完整布线或时序通过。

12:16 路由器完成，12:18 实际实现子进程写出完整检查点和报告后正常退出。`ai7030_edif_top_route_status.rpt` 为 116534/116534 条可布线网络全部连接、0 路由错误。最终静态时序报告为 WNS −0.251 ns、TNS −0.453 ns、18 个建立失败端点；WHS +0.029 ns、0 个保持失败。最差路径位于原 `U_adder_top/jpeg/encoder/legacy_output` 写指针至 FIFO 写地址，另有原 GP FIFO 等路径。原 NPU 最小周期告警仍为两项、WPWS −0.409 ns，不算生产级完整时序签核。此次完整路由仍未满足候选生成门槛。

原主进程还在缓慢转发展开后的大体积 `route_design -unroute -nets ...` 命令，不能把主日志滞后当成实际子任务仍在布线。`capture_route_child_completion.py` 先核对实际 `.route_design.end.rst`、`.vivado.end.rst`、最后一轮完整步骤成功日志、源输入散列不变及 CAD 子进程确已退出，再冻结实际检查点、日志和报告到 `source-build/initial-completed-route/`，只停止这次仍在转发的自有父进程。原主进程收据如实保留退出 1、非超时；没有伪记为正常完成。`route-child-completion.json` 写清两者区别。

`finalize_existing_route.tcl` 单独打开实际工程，核对运行管理器状态为 `route_design Complete!`，导出当前全部报告与 `preview-routed.dcp`，12:20:47 正常结束，退出 0、约 120 秒。不可将这次正常导出等同于时序通过。`bind_route_export_and_optimization.py` 将原子任务完成证据、异常父进程收据、正常导出和不可变输入副本加入实现证据链；308 个输入散列一致后，`optimize_current_route.tcl` 从 `initial-completed-route/preview-exported.dcp` 启动文档支持的布线后 AggressiveExplore 物理优化，输出隔离在 `source-build/postroute-explore/`。没有改原完整路由副本、RTL、引脚、时钟或时序例外；等待优化报告，尚未生成 bit/BOOT 或部署。

12:27:33 首轮布线后优化正常结束，约 385.5 秒。`postroute-explore/timing.rpt` 为 WNS −0.007 ns、TNS −0.097 ns、20 个建立失败端点，WHS +0.029 ns、保持失败零；路由仍为 116534 条全部连通、0 错误。最差裕量改善，但失败端点数量并未清零，不能按数值很小或四舍五入记为通过。`failing-paths.rpt` 显示最差路径为原 NPU AW FIFO 的普通 FDCE 写地址驱动至远端 LUTRAM，825 个负载，数据路径约 95.54% 为布线延迟；另有 FIFO 状态和原复位释放路径的 1–5 ps 违例。

`optimize_current_fanout.tcl` 检查该精确驱动为 FDCE、INIT=0，ASYNC_REG 与 DONT_TOUCH 均未设置，负载恰为 825；随后调用本机命令文档提供的 `-force_replication_on_nets`。实际 Vivado 2018.3 明确拒绝该选项用于 post-route 阶段（`Vivado_Tcl 4-265`），约束与设计尚未修改，退出 1、无优化 DCP；失败日志与 `postroute-fanout/target-before.txt` 保留。没有因此手工复制或重接同步寄存器。

第二轮改用支持的 `phys_opt_design -directive Explore`，从首轮完整结果开始，输出 `postroute-second/`。12:36:05 正常结束、约 320.4 秒，建立/保持指标与第一轮相同，没有进一步改善。随后 `prepare_endpoint_repair.py` 保留两轮证据，选择第一轮不可变 DCP，绑定 `repair_remaining_routes.tcl` 与精确输入配置；改按实际失败输入引脚做最多三轮、每轮少于 100 个端点的 `route_design -unroute -pins` / `-auto_delay -pins` 局部布线。该选项按本机命令文档考虑建立与保持条件，受保护 DDR 线路禁止进入目标集合，每轮要求完整路由且错误为零。输出隔离在 `local-route-repair/`，原完整结果不覆盖；等待实际报告，仍未生成 bit/BOOT 或切换服务。

局部端点操作在原 FIFO 的一个打包内部 D 引脚上被 `Route 35-350` 拒绝：该端点缺少可直接取消布线的物理引脚映射。任务约 80.2 秒后退出 1，没有生成优化 DCP；不能称为局部修复成功。失败记录保留后，转用文档支持的整体 `route_design -directive Explore -tns_cleanup`，从原不可变完整结果开始。

12:43:10 第一轮整体 TNS 清理正常结束，约 206.4 秒，`route-tns-cleanup/timing.rpt` 为 WNS −0.005 ns、TNS −0.041 ns、10 个建立失败；WHS +0.029 ns、保持失败零，116534 条网络全连通且 0 错误。原 825 负载写地址路径不再是失败路径。第二轮从这份更好的结果继续，12:54:31 正常结束、约 537.4 秒，指标与第一轮相同，没有进一步改善；分别保留 `route-tns-cleanup/` 与 `route-tns-second/`。

剩余最差路径来自原 AW FIFO 状态寄存器，经 LUT4 驱动 626 个输出寄存器 CE 负载；实际数据路径约 94.16% 为布线延迟。`replicate_fifo_enable.tcl` 核对精确组合驱动为 `gc0.count_d1[3]_i_1`，INIT=`16'h00DF`，未受 DONT_TOUCH 保护；记录四个实际输入来源及规范化完整真值表。目标是组合逻辑复制，不是复制状态或 CDC 寄存器。只释放四条相关普通网络后，工具仍判为 post-route，并再次拒绝原生强制复制；12:58:36 退出，无复制结果。

随后派生真正布线前的版本：按已验证 hook 释放全部普通路由，逐条保留 1143 条 DDR 专用路由，再执行原生 LUT4 驱动复制。审核要求新增单元为等价 LUT4、完整真值表与输入来源一致、626 个原负载集合完全相同，再进行正常物理优化和 Default 布线。首版复用脚本时发现共享 Tcl 全局 `f` 文件句柄会覆盖审核句柄，助手在实际复制/审核前只停止该自有任务，保留非正常停止收据；派生 `replicate_fifo_enable_fresh_v2.tcl` 改用任务专有审核句柄并隔离输出到 `fifo-enable-fresh-v2/`。原最佳完整 DCP 不覆盖，产品 RTL、引脚、时钟和例外未改；等待该轮实际结果。

13:05:27 v2 进入真正布线前阶段，但原生复制仍为零；审核因没有新增副本而正确停止，退出 1。实际日志 `Physopt 32-698` 明确是 LUT 输入网络 `curr_fwft_state[1]` 的 DONT_TOUCH 阻止了下游组合驱动复制，不是工具已完成目标。补读本地 FIFO Generator 仿真网表，多个同版 FIFO 内部状态/标志网络也带此属性；目标 DCP 和报错证明实际属性，不能把其他 FIFO 的实现代码冒充目标 NPU FIFO 的完整内部 RTL。

参照 [AMD/Xilinx UG904 v2019.2 的 Physical Optimization Constraints](https://docs.amd.com/api/khub/documents/eeESP3eiV0LaWhrlmBYX8Q/content)（PDF 页 85），对限制复制的网络属性可以做受控调整；该资料仅作原理依据，2018.3 的实际支持仍以本机工具为准。v3 的 `enable_replication_protection_scope.tcl` 只在这一次下游 LUT 原生复制期间临时关闭三条输入网络段的 DONT_TOUCH，任何上游单元保护均未解除，复制后立即恢复 DONT_TOUCH 并核对 MARK_DEBUG 原值；还逐项比较四个上游单元的 REF、INIT、DONT_TOUCH、KEEP、ASYNC_REG 和所有输入驱动不变。

13:12 实际 v3 审核通过：`VENDOR_PROTECTION_SCOPE_AUDIT_PASS NET_SEGMENTS=3 UPSTREAM_CELLS=4`，新增 9 个 LUT4，按实际输入来源规范化的完整布尔真值表均与原 LUT4 相同，626 个原负载集合完全相同，未删除无关原语。`replication-audit.txt` 明确标为组合副本和负载的有界证明，不是整板形式等价验证。随后常规布线前 AggressiveExplore 物理优化正常完成，检查点保存到 `fifo-enable-fresh-v3/`，开始 Default 布线及 TNS 清理。原最佳完整结果仍保留；尚无本轮最终时序结论、bit/BOOT 或板端部署。

13:48:39 v3 整轮正常结束，约 2317 秒；Default/TNS 实际布线约 33 分 41 秒。最终 `timing.rpt` 的静态分析为建立 WNS **+0.030 ns**、TNS 0、失败端点 0，保持 WHS **+0.029 ns**、THS 0、失败端点 0；116593/116593 条可布线网络全部连接、路由错误零、固定 DDR 网络 1143。路由器最后估算仍显示 WNS −0.031 ns，但本地命令文档说明估算与正式静态分析可不同；后续门槛使用真正的 `report_timing_summary` 报告，没有用估算值或四舍五入替代。

原 NPU 的两项最小周期失败仍为 WPWS −0.409 ns、TPWS −0.479 ns，与原基线相同。报告因此仍写总体 timing constraints 未满足；本轮只解决建立/保持，不声称完整时序签核或生产级验收。没有因此更改 NPU 时钟、工具数据库或降低验收阈值。

`adopt_reviewable_route.py` 再次核对冻结输入、实际正常退出、组合复制审核、原告警不恶化、全连接与总线偏斜后，只在离线任务中采用该正裕量结果。`preview-routed.dcp` 和任务工程的 routed DCP 复制自同一不可变候选，逐项散列相同；先前完整结果保留在 `pre-positive-adoption-export/` 及原专项目录，没有改板。`refresh_candidate_reports.tcl` 13:50:48 正常结束，重新读取候选生成当前时序、利用率、路由、偏斜、CDC 与 DRC 报告。随后依次开始原引脚/时钟/邮箱/DDR 校准审核、20 条源级状态同步路径审核，以及 1143 条 DDR 专用路由和恢复属性的精确比较。审核未结束，不生成 bit/BOOT。

### 最终只读审核与两个审核脚本修正

13:54:08 `audit_current_tx.tcl` 正常结束，实际结构审核通过：9 个邮箱、10 项发送输出 min/max 检查、4 项预览路径 min/max 检查，DDR 校准控制连接有效；274 个原有端口引脚/电平及 NPU PLL 参数、相位和位置与原基线相同。这里只恢复并检查原厂头部四条既有 DRC Warning 策略，没有添加新的降级规则。

首轮状态审核在共享复位首级 `U_pl_preview/network/transmit_fifo/m_rst_sync1_reg_reg` 的 ASYNC_REG 属性上失败。核对实际源文件：`wcis_status_sync.v` 复用未改动的 `sync_reset.N=3`；固定版本 `axis_async_fifo.v` 的 `m_rst_sync1` 运行在 s_clk，是 MAC 复位的源级，配套 `axis_async_fifo.tcl` 只给后续目的级 `[23]` 标 ASYNC_REG。综合将同一时钟、初值 1、CE=1、D=0、同 PRE 的首级共享给状态复位链，不能误把这个源级强行要求为目的同步级。`prepare_status_audit_v2.py` 保留失败证据，唯一角色例外限定为这个实例、这个精确单元和第 0 级；所有其他 ASYNC_REG 要求、三层 FDPE 结构、初值、时钟、CE/D/PRE 接线、首级异步数据例外及 20 条有限非负 min/max 路径检查均保留。v2 退出 0，`SOURCE_STATUS_ROUTED_AUDIT_PASS; TIMED_PATHS=20`。未改 checkpoint、RTL、约束或时序例外。

首轮 DDR 审核已通过 1143 条专用物理路由逐条比较和三条输入网络保护恢复，随后对上游单元整段 Tcl 列表的字符串比较报不一致。16:47:38 的独立诊断逐字段比较四个单元，所有属性与输入驱动均相同。修正为在关闭 checkpoint 前提取明确的引脚 NAME 字符串，并对全部属性/输入字段逐项严格比较，避免跨 checkpoint 对象及嵌套列表表示影响比较；没有删除语义检查。16:53:20 `audit_final_ddr_preservation_v2.tcl` 退出 0，最终 `FINAL_PRIVATE_DDR_AND_SOURCE_PROTECTION_AUDIT_PASS EXACT_ROUTES=1143 PROTECTED_INPUT_NETS=3 UPSTREAM_CELLS=4`。原失败、诊断、派生源码和成功收据全部保留，物理候选散列未变。

### bit、BOOT 和回退审核包

`finalize_implementation_proofs.py` 固化全部成功只读审核，原 `scripts/package_pl_preview.py` 门槛通过；此时仍保留 `production_timing_signoff=false` 和两项原 NPU 周期失败。`generate_reviewed_preview_bit.tcl` 使用同一审核 DCP，在任务工程中生成 bit，16:59:15 正常退出 0、未超时，整轮约 132.6 秒。实际子任务及父进程均正常结束，本轮没有停止生成进程。原厂写位流后置处理正常完成。

`run_procise_package.py` 使用原 JFMQL30TAI676H 打包模板，先核对原 BOOT 确为 f6da96…、三个 PS 启动部件与原成功候选逐字相同，再在隔离任务中打包；Procise 退出 0、约 3.7 秒、完成标记新鲜。`verify_reviewed_boot_candidate.py` 校验 FMSH 文件头、四个分区、PL 载荷逐字匹配本次修补后 bit（32-bit 字节交换及允许的 NOP 后缀），并确认与原厂后置处理的载荷相同；FSBL、BL31、U-Boot 的内容、运行地址和属性与原镜像一致。

最终文件散列：

- raw bit：`277a02613991a595c763e1efd9fbb44eae5441a6ec19744132417fb156068f9f`
- patched bit：`8843a3cc941d8ce8d8ff57c42d2438e9866edf89b2a0bcbc42a42a183a96bde9`
- BOOT（7,023,552 字节）：`fd5606055c4c6b6a6911da1efeea8b56ae7fe3f873537d105a081ab96b6fb9c7`
- 审核 DCP：`3ca92cedc1170def96fefd25baeb1ab69eaf4d3620726d0c3dfa88ca00dbb34b`

候选位于 `source-build/boot-candidate/`。`prepare_candidate_review_bundle.py` 另生成 `pl-preview-candidate-review-20261028/` 和同名 tar.gz，包含候选 BOOT、接收补充包、审核摘要和已再次核对散列的原启动回退文件；包内 12 个部署/证明文件逐项核对。该包不是自动安装器，没有上传或执行部署。

离线实现与打包已完成，实际 PL 网口、PHY 协商、连续摄像头和模型并行请求仍待上板验证。本轮没有写启动分区、重启或切换正式网站。16:46 再探测 113，默认选路仍经过 Meta，SSH 无 banner、网站提前关闭；不能据此判断板卡关机。后续只恢复到 113 的通路，现场复核原启动/备份后，再按 `fpga_project/AGENTS.md` 的启动分区约定请求具体写入和重启确认。

## 网站接收端与连接限制

27 日实测的后台接收主机为 Linux `192.168.1.102`，其网口当时协商为 100 Mbps；正式网站接口仍为 PS/VPU JPEG、960×540。该状态是 27 日取证，不能代替 28 日在线状态。

28 日本机不再连接原 `192.168.1.*` Wi‑Fi；读取的无线地址为 `10.163.51.32/18`，有线地址为 `10.101.16.100/18`。局域网 SSH 入口先出现 banner 提前断开，后续局域网和学校入口 `10.101.54.192:18222` 均超时。按用户“服务器开着，继续重试原入口”重试，并用有线源地址单独发起同一入口连接，仍超时。`connection-status-20261028.json`、`wired-source-probe-20261028.json` 与相关执行输出保留实际结果；没有据此断言服务器关机，也没有改网络设置或凭证。

服务器回放脚本已增加按原生捕获时间戳发送、保留失败接收统计的路径。目的在区分无节奏突发、缓存、超时和其他丢包，原因尚未定位。这份新脚本因连接失败尚未上传执行，不能称为服务器测试已修复。旧隔离接收子进程已随测试退出，没有留下接收常驻服务。

更新后的重放脚本先在本机隔离目录 `paced-local/` 验证：按捕获时间戳用约 31 ms 送出 212 个 UDP 包，真实接收程序完成一帧、JPEG 散列与原生仿真一致，HTTP 快照、MJPEG 和过期检查通过。报告明确标记 `platform=win32` 和 host-loopback；不代替 Linux 服务器或物理网口验证。

11:32 补做连续接收试验 `receiver_continuous_trial.py`：重复同一原生捕获 JPEG 的分片，仅将协议帧号改为递增值，以 100 ms 计划间隔在本机 loopback 发送 100 帧。`receiver-continuous-trial.json` 记录约 9.969 秒内 21200 个 UDP 包、100 次完整重组；逐帧 HTTP 快照散列均相同，拒绝、重复、过期、被取代、中止与无效 JPEG 计数均为零，停发后过期检查通过，接收子进程已退出。使用的是实际根接收源码，未修改产品代码；该试验验证 Windows 软件连续处理，不证明 PL 连续帧生成、板端持续性能或实际网口吞吐。

### 直连恢复与接收位置纠正

用户说明“不转接直接连”，并表示 MobaXterm 已连接。读取 MobaXterm 的保存目标时只提取主机/端口元数据，没有输出凭证或完整配置值；目标为 `192.168.1.113:22`。使用项目已有的该板卡凭证及固定主机密钥直接连接成功，没有经过 `192.168.1.102` 或学校转接。此前未通的转接端口不能用来断言板卡不可达。

`direct-board-preflight-20261028.json` 与 `current-board-software-20261028.json` 核对当前启动为 `3c8751ac-8b6b-4d83-8b9c-57e4f0716ffd`，与 27 日启动不同；现役应用仍为 `/root/wcis-face/apps/camera-pad-speed-20261027`，硬件所有者二进制 SHA256 仍为 `765396731f284fbc8e54d751c7ea9f88e36eb81990c25fab514e85ff5f2b0a4d`。健康接口 ready、硬件准入与模型缓存 ready，预览仍为 PS/VPU、960×540，录像模式 off。没有停止或重启这些服务。

工作中曾错误地把旧桥接草案中的 `192.168.1.102` 视作本次必要接收主机，并在它不可达时提出当前电脑后台接收。这是助手擅自扩展的依赖，不是用户批准的方案。用户明确反对后，取消这两种部署方向，不再连接该主机或准备电脑常驻接收。只保留此前测试证据；没有安装常驻服务、修改本机防火墙或切换正式网站。

当前按同一台板卡实现：PL 编码/发送，板上 PS 接收并向原网站提供 JPEG 流。可以复用现有接收程序和网站状态/视频适配入口，不引入第二台接收主机；正式服务配置仍须等位流和实际网络路径通过后再切换。此路线的网页输出仍经过 PS 网口，不能把 PL 网口千兆等同于完整网页链路千兆。

本任务连接使用 `D:/yzd/tmp/pl-preview-resume-20261027/direct_board.py`，只直连 `192.168.1.113:22`。旧 `stage_test_receiver_host.py`、`inspect_website_host.py` 等 `.102` 脚本仅作历史证据，不再执行；`README-current.md` 写明当前范围，避免续作误用旧草案。

11:28 续作时直连 113 的 SSH 在协议握手阶段提前断开；不据此判断板卡关机，也不更换到 102 或学校转接。继续离线实现并记录直连探测，之前的成功收据仅保留其当时的验证范围。

12:46 本机 `Find-NetRoute` 显示到 113 的默认路径实际经过 Meta 虚拟网卡（198.18.0.1→198.18.0.2），真实有线地址仍为 10.101.16.100；没有读到直连 192.168.1.* 的活动物理接口。普通探测中的“TCP 成功、未收到 SSH banner”不能当成板卡 SSH 已连通。按 [Microsoft Winsock IP_UNICAST_IF 文档](https://learn.microsoft.com/en-us/windows/win32/winsock/ipproto-ip-socket-options)，`probe_113_physical_interface.py` 只对这两个探测 socket 选择实际有线接口 8，并回读确认接口索引；22 与 8091 都超时。没有修改系统路由、VPN、网卡配置或连接其他主机。`direct-113-physical-interface-probe.json` 保留结果；仍不能判断板端在线状态，已询问用户当前 MobaXterm 是否还能执行命令，离线构建继续。

`board-eth0-20261028.txt` 实时核对 PS eth0：支持并通告 1000baseT/Full，对端只通告 10/100，当前为 100 Mb/s 全双工。不是 PS 硬件仅支持百兆；真实网页吞吐仍受现场链路影响，后续需要检查千兆对端和接线。

`board-preview-profile-draft.json` 只记录同板接入草稿：原网站 `http://192.168.1.113:8091`，板上接收 HTTP 地址 `http://192.168.1.113:18092`，UDP 目的也是 113。目的 MAC 从该板实际 eth0 读取，绑定观测启动，并明确要求重启后重查。PL 源地址 192.168.1.240 仍是待检查的计划值，部署会话尚为空；此文件不是可执行的硬件 enable 配置，没有修改现有网络或服务。

### 板卡本机接收验证

通过直连将三个实际接收模块、重放脚本及原生 HDL 捕获放入板卡隔离目录 `/root/wcis-face/candidates/pl-preview-20261028/receiver-trial`。`board-receiver-trial.json`：板上 Linux 按捕获时间戳约 31.9 ms 重放 212 个 UDP 包，重组成一帧 296427 字节 JPEG，SHA256 与原生仿真相同；HTTP 快照、MJPEG 响应和过期关闭检查通过，接收统计 0 拒包、0 丢包。

该试验仅在板卡 loopback 上进行，没有访问 PL/SDK 硬件，也没有接入正式网站。实际 socket 接收缓存为 425984 字节，低于请求的 4 MiB；单帧通过不证明连续、高码率或物理网口稳定性。测试子进程正常退出，没有留下常驻服务。后续仍须完成整板建立/保持与完整路由审核、源码/位流绑定、真实 PL→PS 网络路径、实际协商与持续摄像头预览。

`board-site-pl-capability.json` 进一步核对现役 `serve_photos.py` 与当前根源码散列相同，已有接收地址、浏览器地址和状态/视频路由参数；但现役应用目录缺少 `external_preview.py`。该模块只补到隔离接收测试目录，没有改正式应用。再次板上回放的 `board-receiver-trial.json` 为 `website_adapter_checked=true`：实际适配类可读取接收状态并生成快照/MJPEG 地址，图像散列、过期和接收统计仍通过。这不等于正式网站已切换。

13:17 `prepare_same_board_receiver_bundle.py` 生成 `same-board-receiver-overlay.tar.gz`，六个部署文件逐项核对包内散列。三个接收模块与网站适配模块均与实际板上单帧回环使用文件相同；网络管理工具与已有学校服务器构建收据、当前管理源码散列一致。现役 `serve_photos.py`、`camera_owner_runtime.py` 的预期散列与 27 日正式部署收据一致，所有者二进制预期仍为 76539673…；这些是待现场重查的版本约束，不冒充当前在线复核。

补充包不是完整应用安装包：后续应在核对后的完整现役应用副本中加入缺少的适配模块，沿用已有 `--camera-pl-preview-url` 参数及自动 `pl-preview` 所有者模式。网站仍为 113:8091，同板接收为 113:18092/UDP5004，没有额外接收主机。`manifest.json` 的 activation_ready、bit_ready 都为 false，session 为空，必须实际启动准入后重新生成；没有自动启用、改启动分区或切换正式服务。包和回执位于原任务目录，尚未上传。

`backup_current_boot.py` 按项目既有只读挂载流程读取当前启动分区，复制到本任务回退目录后解除挂载，没有写启动分区。板端及本机回退副本逐项 SHA256 相同：BOOT 为 `f6da96abbc0144ce5a48f4fa85aed6dab65067211b8932e8f4e4db87d5110297`，DTB 为 `e7edf0bc5eb31485962c9bfbefff60c250c9ec14363ccdd41a695173a127d3af`，uEnv 为 `a13c985eb5031d75ec7069333897cae38944ba5fbadd509828b63e6a48408560`。`current-rollback-receipt.json` 绑定当前 3c8751ac 启动，原服务保持运行；这份回退备份不代表新候选已部署。

### 17 时后直连恢复、候选暂存与板端连续软件试验

用户确认能打开 113:8091 后，`fresh_board_preflight.py` 重新直连 `192.168.1.113:22` 成功。本机 WLAN 已回到 `192.168.1.106/24`，当前启动仍为 `3c8751ac-8b6b-4d83-8b9c-57e4f0716ffd`。现役配置与主服务散列分别仍为 `9d081453…`、`a60c2c6c…`；27 个候选应用文件的基础来自核对后的现役应用。网站 ready、硬件准入与模型缓存 ready，原预览仍是 PS/VPU、960×540，录像 off。新收据位于任务目录 `board-resume-20261028/`，不覆盖已冻结的位流/打包证明。

`stage_reviewed_candidate.py` 重做启动分区只读核对、下载回退副本后，确认 BOOT、DTB、uEnv 与此前回退收据逐项一致，解除只读挂载。候选及证明的 14 个文件上传至 `/root/wcis-face/candidates/pl-preview-20261028/reviewed-fd5606055c4c/artifacts/`，板上逐项验证散列。脚本最初使用顶层归档查找而未找到子目录中的接收包，未执行正式修改；改为递归查找后重跑成功，保留实际失败输出。

在同一隔离候选目录，复制现役配置列出的全部应用文件并加入缺少的 `external_preview.py`，共 27 个文件逐项校验，三个相关 Python 模块语法检查通过。备份原配置、网站/查看服务、部署期望文件；另生成候选网站服务与配置草案，仍使用现有单一硬件所有者、PAD 模型和图库参数，仅增加同板 PL 接收入口。`candidate-staging-receipt.json` 明确记录未写启动分区、未改服务、未访问硬件、未重启、未激活。

`inspect_startup_and_stress.py` 在板上独立 loopback 端口执行连续软件试验：重复同一原生 JPEG 捕获，仅增加协议帧号，计划间隔 100 ms，约 9.952 秒接收 100 帧、21200 个 UDP 包。100 次 HTTP 快照散列均为 `59e51e5e…`，拒绝、重复、过期、取代、中止与无效 JPEG 计数均为零，停发过期检查通过，接收子进程已退出。记录为 `board-receiver-continuous-trial.json`；这验证 Linux 板端接收软件，不证明真实 PL 持续编码或千兆 PHY 吞吐。

`prepare_startup_review.py` 读取并备份当前板端 `boot_prepare.py`、`camera-control.json` 和 `deployment.json`。现有网站的 `ExecStartPre` 会只读核对三个实际启动文件、验证应用散列后生成本次启动证明；CameraInterlock 另核对部署期望 BOOT。新候选需要同步更新这些期望，但不能直接改证明中的 boot_id 冒充新启动。已生成四份候选配置/服务草案并记录散列，尚未安装或执行。原准入脚本本身未修改，既有检查不放宽。

当前 PS eth0 再次显示支持 1000baseT，但对端仅通告 10/100，实际仍为 100 Mb/s 全双工。同板方案的网页输出仍经 PS 网口，不能把 PL 口千兆等同于网页全链路千兆。新位流之后仍须核实 PL PHY 实际 1000/full、时钟延迟、源地址占用、新会话和目的 MAC，再验证真实摄像头与并发推理。

下一步的具体范围是以已核验候选替换 BOOT、保留 DTB/uEnv、正常重启并进行原型验收，保留原 BOOT 与配置用于回退。项目 `fpga_project/AGENTS.md` 禁止自行更改启动分区，故本轮完成暂存与回退准备后等待用户明确确认写入和重启。当前尚未部署新 BOOT，正式网站仍使用原预览。

### 用户授权的候选上板、失败与回退

用户在明确 BOOT 是保留原硬件模块的整板候选之后回复“可以”，授权此前提出的写入及正常重启。`deploy_approved_boot.py` 记录具体授权，所有连接仍只到 113。首次 `systemctl stop` 等待 50 秒超时，启动文件尚未写入。现场线程和 socket 检查发现 Python HTTP 包装进程等待空闲连接收包，主线程等待线程结束，原生所有者仍在运行；systemd 使用 `SendSIGKILL=no`，超时本身不能证明 SDK 已关闭。

随后取得原生 PID 306 的真实 `306-owner-stop.json`：exit_code=0、sdk_closed=true、sessions_released=true、camera_pending=false、camera_drained=1、captured=encoded=1741864、camera_requests=1741865。先前 `ss -K` 未列出实际关闭连接；单独排空诊断脚本在读取已退出 PID 时提前失败，未执行其中的信号或进程清理。没有强杀原生所有者，按实际正常停止收据继续。恢复脚本只允许在同一已开始停机事务、录像服务 inactive 且原生正常退出证据齐全时继续，未重新启动旧 SDK 来重做该步骤。

`reviewed_boot_trial_remote.py stage` 获取原硬件锁，保留原 BOOT 的 FAT 分区副本 `PL1028.BAK`，写候选临时文件、fsync、核验后替换 BOOT，逐项验证 DTB/uEnv 未变。原网站/查看/录像服务暂时禁用自启动，新只读准入服务运行原 `boot_prepare.py`，只更新经过审查的 BOOT 期望值，保留实际启动文件核对和应用散列校验。15 分钟未接受回退 timer 已预置，未将候选写入等同于验收。新启动 ID 为 `424cd88b-582f-4d48-8d4e-99ad08022329`；实际只读准入证明确认 BOOT=fd5606055c4c、DTB/uEnv 与原版一致，网络模块 NTP2/capability/1920×1080 均正确。

`post_boot_network_trial.py` 读取新启动的 PS MAC，以三次 ARP 探测检查计划源 192.168.1.240，未见冲突，生成新的非零部署 session。板端隔离接收服务启动后，已有学校服务器构建的管理程序在继承的两把硬件锁下执行一次 enable，返回 exit_code=2、`Expected YT8521 PHY not found`、sdk_closed=true。网络 enable 保持 0，没有发送真实预览，没有进入 PHY 电平/延迟配置或改变板卡电压。接收服务首次等待 8 秒过短，服务随后可访问；后续管理程序的芯片身份失败是另一项实际结果，不能混同接收启动等待。

`read_phy_identifiers.py` 仅在新启动准入、管理程序 SDK 已关闭且排他硬件锁可获得时，按源文件已定义的 NTP2 页映射寄存器，先确认 magic/capability/geometry 与 SDK 读数相同，再只发 Clause22 的寄存器 2/3 读命令。0..31 的地址返回标识值均为 0、完成位有效，未报 turnaround 错误，复位释放位为 1。这里只证明所读管理数据异常，不能据此认定 PHY 损坏、网线故障、板型错误或引脚错误。没有探测 DDR 地址、改引脚/电平、配置 PHY 或重复硬件 enable。

在 PL 发送保持禁用、原应用不变时，`check_new_boot_existing_functions.py` 启动原 PS/VPU 模式验证旧功能。健康与连续采集可用，但第一次摄像头识别请求返回 503；原生所有者在 `command_begin` 阶段记录 `Owned frame guard mismatch`，并写入当前启动硬件隔离标记。停止新的 SDK/识别请求，没有绕过 guard 或把保护错误解释成 NPU 模型推理成功。仅从这条错误不能确定是越界、DDR 数据可见性、仲裁还是其他原因。

因此未切换正式网站到 PL 模式、未接受候选。`recover_approved_trial.py` 在保存失败收据后执行回退：停止服务、取得硬件锁、校验 DTB/uEnv、恢复已核验原 BOOT 与原配置，禁用本轮准入/回退 timer 与接收服务，恢复原服务自启动并正常重启。回退启动 ID 为 `b1419f84-7dfc-4b11-926b-e2f5f2241964`。`rollback-verification.json` 核对当前实际 BOOT=f6da96ab、原应用/主服务散列正确、健康 ready、连续 960×540 PS/VPU 图像推进、录像 off；三次真实摄像头识别请求均通过，耗时约 429/276/260 ms、无人脸、PAD 为 not_applicable，不能当作真人/攻击或多人防伪验收。

回退核验最初比较图库时发现候选试验的空快照是在 eMMC 尚未由网站依赖服务挂载前读取，不能拿它与挂载后的持久图库比较；收据明确标记 `gallery_unchanged_proven=false` 并保留实际当前散列、挂载及访问成功状态。没有执行登记、删除或图库写入请求，不因比较基线错误声称图库丢失，也不补造“内容未变”证明。后续检查复用同次启动已保存的三次成功请求，未为了完成报告再次调用 SDK。

用户回复“路由器网线亮了，板子上的是灭的”时已经回退到原 BOOT。按此记录观察时序，不能把灯状态当作候选期间 PHY 链路证据。`audit_deployed_candidate_mdio.tcl` 只读打开冻结 routed DCP，约 63.5 秒正常退出：MDIO=AF22/LVCMOS18、MDC=AE22/LVCMOS18、RESET=AA13/LVCMOS33；IOBUF 输入实际连接到两级同步器，输出及三态也有实际驱动。这排除静态网表中直接断连/绑常量这一种解释，但不是实板 MDIO 电气或时序证明，没有修改 checkpoint。

本轮最终写入 `candidate-rejected.json`，绑定 fd5606055c4c、两项实际失败、回退收据和当前原 BOOT；部署脚本增加拒绝再次部署该失败候选的检查。冻结位流/打包 manifest 保留生成当时的离线证据，不能替代这份后续失败结论。后续应先定位管理链路全零和原 FAC1/DDR 保护失败，补齐相应验证，再生成新的候选；不在原现场反复试写或放宽硬件准入。

关键新增来源均在 `D:/yzd/tmp/pl-preview-resume-20261027/board-resume-20261028/`：`boot-switch.json`、`post-boot-inspection.json`、`network-enable.json`、`phy-id-diagnostics.json`、`candidate-runtime-fault.json`、`recovery.json`、`rollback-verification.json`、`routed-mdio-audit.txt`、`candidate-rejected.json`，以及同任务目录对应脚本和执行收据。

### 18 时后 DDR 故障收窄与原生模块保留修复（离线）

用户确认实板有两个网口，PS 与 PL 各接一根网线。这是用户提供的接线信息，不替代实测协商。继续只直连 192.168.1.113；本段没有新 SDK 运行、停服务、写启动分区或重启，板卡仍使用回退后的 f6da96ab 原 BOOT。

核对当前 `ps_app/src/wcis_camera_owner.cpp`、`wcis_owner_kernels.hpp`、`wcis_owner_vpu.hpp`，三者散列与 `D:/yzd/tmp/wcis-camera-preview-speed-20261027/native-build-receipt.json` 一致。按真实代码顺序，SDK 分配、填充保护区、`memory.write` 后，`reserve(device)` 在启动 FAC1 之前检查完整缓冲区。因此先前 `command_begin` 保护失败发生在输入写入/读回阶段，不能解释为已经开始裁图或模型推理。只读下载失败进程 521 的 stdout/stderr/fault，未取得该故障进程的正常退出收据；没有重新执行它。此前两次管理程序的 SDK 打开/关闭也可能是混杂变量，尚不能证明单一根因。

`board-resume-20261028/source-delta-vs-case16.json` 对照原案例与候选：MIG stub/simulation netlist 的差异仅生成日期和路径注释。`compare_working_ddr_configuration_v2.tcl` 只读对照实际原版与失败候选的 MIG/NPU DDR 互连范围，约 139 秒正常退出：48978 个共有单元中 10633 个 LOC/BEL 不同，提取的逻辑配置属性没有共有单元差异；另有原版独有 58、候选独有 95 个单元。这是有限范围比较，不是整板逻辑等价证明，也不证明这些位置变化就是故障原因。首个逐单元查询脚本超时的日志保留，未据其作成功结论。

进一步用 `audit_ddr_calibration_regions_v2.tcl` 纠正仅按控制器名称/数量判断的风险：原版有 5 个 IDELAYCTRL、候选有 3 个，但两版实际 64 个 `IDELAYE2_FINEDELAY` 都分布在 X1Y1/X1Y2/X1Y3，数量为 32/8/24，两版这三个区域均有控制器。原版多出的两个控制器在其他区域；自动复制单元名称不能作为物理对应关系。因此没有据此移动控制器、改变校准配置或声称已经定位缺失校准。

参考本项目 `face-cache-preservation-20261019.md`、`face-cache-resume-20261020.md` 的原生 DCP 模块保留流程，开展一次独立离线修复实验，所有产物在 `ddr-native-repair/`，不改冻结失败候选。由实际原版 `D:/yzd/tmp/sdi-refclk-fix-20261020/refclk-final.dcp` 提取完整 MIG，`working-mig.dcp` SHA256 为 b3fcf18f9e892fca1ff8c0db98be776bea26ad051d06341529a2f009049f74d8。与当前候选 opt checkpoint 的 1342 个接口名称/方向逐项一致。原生替换后，1342 个父级接口接线及 116100 个外部原语名称/类型不变；记录了 24449 个 MIG 原语位置与 25357 项 ROUTE 属性，并释放 1191 条应用边界连接供周围逻辑重连。`assembly-proof.txt` 与 `assembled.dcp` 已生成，但下述复核发现线路保留证明无效，这份组装结果不能用于 bit/BOOT。

第一次后续实现 `place_route_accepted_ddr.tcl` 在导入 NPU 增量参考后触发保护检查：一项 MIG 内部 ROUTE 属性发生变化（后续发现原值为空，不能据此声称原物理线路被改动），约 175 秒以错误正常退出，没有执行放置、生成 bit 或打包。保留失败脚本、日志及收据，没有放宽保护。21:49 使用 `place_route_accepted_ddr_v2.tcl` 从同一 `assembled.dcp` 直接放置，取消增量参考；该次因原厂 GT DRC 进程级设置未随 checkpoint 保存而在放置前退出，收据约 46.9 秒、exit=1。第三版只从现有厂商 pre-opt 脚本提取相同的 4 项 030ai DRC 设置，未增加新豁免；该设置不改变实际网表、时序库、引脚或电压。

21:51 复核发现先前组装证明存在实质缺陷：25357 项被统计的 ROUTE 属性全部是空集合，脚本错误地把非空字符串形式的空集合当成有效线路；另外 Vivado 12-3336 明确警告 imported 模块没有 pblock，`lock_design -level routing` 没有锁路由。因此撤销“25357 条原线路保留”结论，`assembly-proof.txt` 中的成功标记不能作为放行证明，`assembly-rejected.json` 单独绑定失效原因与散列。第三版仅为本任务的 CAD 进程已按命令行/PID 核实后停止，尚未产生 placed/routed/bit/BOOT；没有关闭其他任务。此前组装过程的 301 项 critical warning 也保留，不能因退出码 0 忽略。

进一步只读运行 `audit_native_mig_route_import.tcl`，分别检查实际原版和组装结果，比较 `get_nets -top_net_of_hierarchical_group` 与同时带 `-segments` 的查询、实际非空 ROUTE 与 ROUTE_STATUS，区分查询错误和真实导入丢路由。结果必须依据收据更新，不能以当前失效 reference 作通过标准。后续保护基线应在实际原版上建立，要求真实非空线路、来源绑定及导入前后对照，空集合检查失败即停止。

21:54 只读审计正常退出（约 151.5 秒）：两种查询在原版中都得到 19900 项非空 ROUTE，在旧组装文件都为 0，确认真实导出/导入结果没有保留原路由，并非单纯对象查询方式差异。原版全设计 104649 条可路由网络全部连接、0 路由错误；旧组装文件不是此原版。保留 `native-route-audit.txt` 和两份 route-status 报告。

检索厂商公开资料后找到与本机症状吻合的 [Xilinx RapidWright 官方仓库答复](https://github.com/Xilinx/RapidWright/discussions/369)：`write_checkpoint -cell` 的特定导出条件不满足时会丢失路由；答复给出在导出副本中标记 HD.RECONFIGURABLE 的方法。另 [UG905 的 OOC 模块要求](https://docs.amd.com/r/2022.2-English/up905-vivado-hierarchical-design/Build-an-Effective-Floorplan) 说明 imported 路由保留需要 CONTAIN_ROUTING pblock。公开说明作为下一步方法依据，是否适用本机 2018.3 仍以实际开关文件验证为准，没有改工具或实板。

`export_routed_mig_v2.tcl` 只读加载实际原版，在内存中的导出副本设置所需元数据；以原版中有真实节点、非恒定且非模块边界的 18560 条内部路由作为基线。设置元数据后逐条一致，再导出 `routed-export-v2/mig-routed.dcp`，关闭设计并重新打开，全部 18560 条名称及节点字符串逐条一致；约 139.7 秒正常退出，`route-preservation-proof.txt` 明确为仅导出验证，尚未组装、时序或板测。原版磁盘 checkpoint 未改，此元数据操作不是部署局部位流。

22 时前启动 `assemble_routed_mig_v2.tcl`：先重新从实际原版采集原语位置/类型，再以覆盖现有器件的内部 pblock 及 CONTAIN_ROUTING 约束导入新模块，核对原版位置、外部原语/父级接线、所有真实内部路由和实际 fixed 属性。该离线 pblock 不改变板卡引脚、电平或器件。此时结果待实际收据，不能沿用此前无效组装通过标记。

22:00 左右首次真实路由导入尝试 `assemble_routed_mig_v2.tcl` 因 clock-region 对象名称缺少 resize_pblock 所需的 CLOCKREGION_ 前缀而正常报错退出（约 110.5 秒），未导入模块或生成组装文件。第三版改为正确的器件区域表示，保留前一失败收据；不是调整引脚或放宽验证。

22:03 `assemble_routed_mig_v3.tcl` 完成真实路由导入：从原版重新核对基线，1342 个父级接口接线及全部外部原语名称/类型不变，24449 个 MIG 原语的名称/类型/LOC/BEL 与实际原版一致。18560 条非空私有路由在导入后、锁路由后均逐条一致，并逐一检查实际 IS_ROUTE_FIXED=true；未用空值计数代替 routed 证明。保留 `routed-import-v3/assembled.dcp`、`reference.tcl`、`assembly-proof.txt` 和原版物理基线。锁定过程对部分已有占用/空的 FIFO 内部网络仍有 warning，日志完整保留；上述接受仅针对严格实查范围，不能外推到所有接口/共享时钟或整板时序。

22:04 启动 `route_real_ddr_import.tcl`（本任务最多 1200 秒），从新组装文件重新打开后再次检查位置、真实路由及 routed/fixed 状态，放置、物理优化、路由后重复同一检查。使用原厂已有 DRC 设置，没有引入新的增量参考或更改原 BOOT。当前新组装通过仅允许离线实现；真实 PHY、DDR 写读、连续预览与模型同跑仍未验收。

22:04 的整板放置前检查约 51.6 秒正常拒绝：HDPR-16 报 MIG 内有 4 个不可局部重配置的 BUFG，HDPR-49 报导出带来的 HD.RECONFIGURABLE 与已有 HD.PARTITION 同时存在。未放宽或关闭这些规则，未进入放置。此结果表明导出所需的元数据不能直接作为最终整板模式保留，不是否定已经逐条通过的私有路由数据。

`clean_mig_export_metadata.tcl` 首次清理后检查把“已清除的空属性值”误判为仍激活，约 38.7 秒报错停止，未写新 checkpoint；第二版修正空属性表示的检查并打印真实值：HD_RECONFIGURABLE=空、HD_PARTITION=1。位置、类型、18560 条真实路径及 fixed/routed 状态在清理前后均一致，再另存 `routed-import-v5/assembled.dcp`。这是恢复普通整板元数据，没有修改物理线路或跳过 DRC；第三、四版原始产物与失败收据保留。

22:08 启动 `route_real_ddr_import_v3.tcl`，只使用 `routed-import-v5/`：重开时明确拒绝仍有局部重配置标记的文件，并继续所有真实路由/位置/固定状态检查，使用同一原厂 DRC 基线。结果待实际运行收据；没有新 bit/BOOT 或现场部署。此前 `route_real_ddr_import.tcl` 已退出，不再运行。

22:13 对原版与新组装 DCP 内的 XDC 做只读比较，`hierarchy-metadata-xdc-comparison.json` 显示新文件另有 MIG 的 HD.PARTITION=true，而原版导出的 XDC 没有该项。普通模式放置已进入 floorplanning，但报告新 pblock 的 PPLOC 拥塞。此时仅作警告，尚未产生最终路由或时序失败结论；为移除这项额外变量，按本任务命令行/PID 核实后停止本轮 CAD，约 289.7 秒退出，未生成 placed/routed/bit/BOOT。

`clean_mig_import_constraints.tcl` 移除新增的 MIG HD.PARTITION 和本任务 pblock，保留原生导入后已实际固定的私有线路与单元；约 62.5 秒正常退出。真实属性为 HD.RECONFIGURABLE=空、HD.PARTITION=0，18560 条非空 private route 的节点、routed/fixed 状态及 24449 个原语位置/类型在操作前后仍一致，生成独立 `routed-import-v6/assembled.dcp`。前述层级/区域限制未带入此文件，未修改原始参考 checkpoint。

22:14 启动 `guide_full_image_with_accepted_npu.tcl` 独立验证原版 NPU 布局复用，输入仅为 v6 普通整板组装结果和实际原版 f6 DCP，最多 360 秒；只有在逐条真实 DDR 保留检查及 fixed 状态再次通过后才写 `guided.dcp`。早期增量尝试的 reference 为空，不能据其属性变化断言参考导入破坏了真实原版线路；本次以正确的真实路由基线重新判断。结果待实际收据，不是重新运行旧错误证明。`route_real_ddr_full_image.tcl` 仅准备，尚未执行。

22:17:57 NPU 布局复用实验约 199 秒正常拒绝：18560 条私有线路内容仍与原版逐条一致，但 `.../ddr_phy_top0/phy_if_reset` 未同时满足 ROUTED 和 IS_ROUTE_FIXED 检查。现有错误信息未分别打印两项实际值，不能补写成“节点已经变化”或具体固定标志故障。未生成 guided.dcp/guide-proof，未放宽检查或使用这个结果；`route_guided_full_image.tcl` 只准备、未运行。

22:18 从通过清理及真实路由检查的 `routed-import-v6/assembled.dcp` 直接启动 `route_real_ddr_full_image.tcl`，没有导入 NPU 参考、不带新增 MIG 分区/pblock，仍使用放置/物理优化/路由后的严格检查与 1200 秒上限。后续结果待实际收据。失败 guide 不影响 v6 原输入文件。

22:19 `continuation-source-scope.json` 重新校验根目录 21 份预览 staging RTL，均与冻结 `source-build/preview-staging.json` 的 SHA256 一致。本次修复操作为 DCP 导出/导入、任务内集成约束与新增前置检查脚本，未重写根 RTL；现役模型/原生所有者代码没有本轮修改，板端也未切换版本。

22:26 普通整板流程完成放置，`after_place` 严格检查再次通过：24449 个原版 DDR 原语位置/类型及 18560 条真实非空内部路由的节点、ROUTED/IS_ROUTE_FIXED 状态全部保留。约 22:26:59 正常写出 `routed-import-v6/placed.dcp`。放置估算 WNS=-6.147 ns，故在保存布局、进入物理优化后按自有命令行/PID 停止该进程，实际收据约 518.8 秒 exit=1 为本任务主动终止，不能写成路由运行失败或完整实现成功。没有生成 physopt/routed/bit/BOOT。

随后只读 `audit_placed_actual_ddr_timing.tcl` 约 100.7 秒正常退出，再次通过重开布局的 DDR 保留检查。新报告 `placed-timing-summary.rpt` 为放置估算：WNS=-6.147 ns、WHS=-2.540 ns，setup/hold 失败端点分别 10716/7243，原两项最小周期失败仍在。这些值不是完成布线后的实测时序。首个最差路径从相机 read_buf BRAM 到 vout_data 寄存器，计时为 clk_pll_i 5 ns 到 RXOUTCLK 6.734 ns，工具按 0.012 ns 边沿差分析。实际时钟路径经过已有 `rx0_locked ? rx_usrclk : sys_clk_200m` 的选择逻辑及任务复制中的分发 BUFG；当前根 RTL 21 文件散列仍与冻结 staging 一致，不是本轮重写该方程。

`placed-ignored-exceptions.rpt` 显示若干原有跨时钟 false_path 被 reset_path 完全覆盖；时钟检查为 no_clock=0、内部未约束端点=0、generated clock 失源=0、2230 个寄存器引脚有多时钟。这里提示需核对跨时钟约束及导入边界，不能未经逐条依据就加宽 false_path、认定只是误报、或保证重新布线即可解决。当前没有完成原版/冻结候选的对应约束行为比较，不能把具体 reset_path 的来源写成已定位。新布局没有通过时序放行。

22:26 再次只读直连 113 核对：仍为 b1419f84 原版启动，现役应用文件散列一致，网站/硬件准入/模型缓存 ready，PS/VPU 连续预览，录像 off。没有新增识别请求或其他 SDK 所有者。

22:32 用户询问可行性并表达对继续投入的犹豫。此时 CAD 已全部退出，没有布线任务在后台，原版系统保持运行。后续范围正在等待用户选择：暂缓 PL 网口保留现有功能，或再做一次有明确退出条件的定位；本记录不把此选择预先写成授权，也不启动下一轮完整构建。PHY 身份问题和候选 DDR 板端写读均仍未修复验收，不能承诺一定成功或称接近完成。

新增 `scripts/run_admitted_memory_probe.py`，复用已有学校服务器构建且源码可绑定的 `wcis_jpeg --memory-probe`，没有本机重新交叉编译。原构建二进制 SHA256 为 fd156ccd330a2f68526dd526605a0223a6b1330a34de041b61c0817ff2ec6feb，source.tar.gz 与原构建收据匹配，其中 jpeg_runner.cpp 与当前源码逐字节相同。前置检查只访问 SDK 自行分配的一块缓冲区，4 组偏移/分块条件各比较 4147200 字节及第二次读回；不使用猜测物理地址、不启动 CustomOp、不加载模型，也不等同完整 2 GB 容量/长稳验收。顺序改为新启动只读准入→此写读检查→PHY 管理→FAC1/模型。发现数据不一致即隔离本次启动并停止后续操作。

原生旧探针即使发现数据错误也可能返回退出码 0，因此新增解析器同时核对完整覆盖、数据错误、两次读回变化、字节/位分布及 SDK 分配窗口。`tests/test_admitted_memory_probe.py` 的 7 项解析检查通过，并重放 18 日真实成功/失败收据，均作出预期接受/拒绝。它们只证明收据检查，不证明本轮硬件已通过。运行器取得两把排他锁后再次核对启动与隔离标记，原生子进程继承锁，不超时强杀、不自动重试、不停止现役所有者。

`ddr-native-repair/preflight/` 的五个文件及 manifest 已暂存到板上独立 `ddr-repair-preflight` 目录并逐项散列核验，`preflight-staging-receipt.json` 记录 sdk_executed=false、services_changed=false、boot_id=b1419f84-7dfc-4b11-926b-e2f5f2241964。没有在正常运行的原网站旁再打开 SDK。后续版本 `preflight-v2/` 增加可选的已审查运行库目录参数；只读 ldd 检查确认此二进制使用板端默认加载路径即可解析全部库，无须覆盖环境。该版本五文件另存到 `ddr-repair-preflight-v2` 并校验，启动仍 b1419f84、sdk_executed=false、services_changed=false；首版暂存与清单保留不覆盖。

另外准备 `read_phy_identifiers_v2.py`：后续仅在新启动准入、单次 PHY 管理失败且 SDK 已关闭时，先以 32 位 MMIO 检查禁用状态下的 session 寄存器写读并恢复，再读取身份寄存器。旧诊断采用的 Python pack_into 不保证预期的 MMIO 写访问宽度，因此旧全零返回不能直接证明真实 PHY 数据全零。新脚本只做语法检查，未上板执行；若未观察到 busy，也不能把旧完成位当成新命令被接受的证明。进一步补入必须观察到 busy 或完成位清零的实际接受证据、无新增拒写、prior result 同启动以及锁后启动/隔离复核，两个脚本体只做 AST 检查，仍未上板执行。

本机板卡手册第 20 页的 PL 引脚表与当前 XDC 一致，未修改引脚或电平。该页下方原理图标注 PS_PHY_MDIO，不能用它推断 PL PHY 复位是否经过反相。手册只作资料边界，实际 PL PHY 身份、链路与连续预览仍待验证。

关键本地来源：本任务 `board-resume-20261028/ddr-config-comparison.json`、`calibration-regions-v2-*.tsv`、`source-delta-vs-case16.json`、521 日志；`ddr-native-repair/boundary-verification.json`、`assembly-proof.txt`、`accepted-ddr-reference.tcl`、`preflight/manifest.json`、`preflight-staging-receipt.json`；对应提取、组装、实现脚本及退出收据。实际失败候选仍禁止重部署，首版离线 MIG 组装结果也已撤销线路保留证明（后续真实路由版本单独记录），尚无新的 bit/BOOT。21:53 只读直连重新核对原版启动 b1419f84，现役应用散列一致，网站 ready、模型缓存 ready、PS/VPU 连续预览、录像 off；未执行新的识别请求。

## 来源与归档

本地来源：上述任务脚本、冻结散列、构建/探针日志与收据，当前 `prepare_pl_jpeg_preview.py`、`build_pl_jpeg_preview.tcl`、`serve_photos.py`、`external_preview.py`、27 日报告。补充读取 `D:/xiangmuwendang/WCIS-FPAI/repos/FPAI30TAI图像FPGA/README.md`，仅作背景。

本日日期按客户端 2026-10-28；27 日构建结果保留其实际日期。本文同步合并到 `D:/bigfuture/竞赛/记录/2026-10-28.md`，保留已有记录和源文档。
