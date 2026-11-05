# PL 预览状态跨时钟修复（2026-10-25）

## 范围与依据

接续 `pl-jpeg-bram-chunk-20261025.md`。1080p PL JPEG/UDP 整板候选的首次完整路由虽然连通，但后路由优化仍为建立 −0.422 ns、保持 +0.026 ns，不能作为可用位流。未生成 bit/BOOT，未访问或部署板子；NPU 仍保留原 1 GHz 配置。

本轮目录为 `D:/yzd/tmp/pl-status-cdc-eco-20261025`，输入为上一任务真实生成的 `case/fpai_demo_vivado.runs/impl_1/ai7030_edif_top_postroute_physopt.dcp`。不重新综合/布局整片，在已有检查点上增加 11 个触发器，局部修复两处单比特状态信号。此工作不代表全部原厂跨时钟路径已排查完毕。

## 实现过程

原厂 `frame_read_write_largebuf.v` 在摄像头 `write_clk` 中产生粘滞溢出标志 `wr_wfifo_err`，同域立即抑制 FIFO 写入，但其五个写帧控制消费者直接位于 `mem_clk` 域。`frame_fifo_write.v` 在检查 FIFO 状态时使用该标志，成为本次路由最差建立路径。新模块 `rtl/wcis_status_sync.v` 复用已固定版本的 `sync_reset`：三级异步置位、同步释放复位链，随后两级单比特状态同步。只同步五个存储侧消费者；源域溢出反馈、立即写入抑制和原 GP 统计接线保留。

另一路 125 MHz MAC 欠载事件直接进入 150 MHz `sticky_errors[1]`，原后路由裕量为 −0.302 ns。现先在 125 MHz 源域将事件保持为粘滞电平，再经同样同步链送入 150 MHz 诊断寄存器，避免只同步短脉冲而漏记事件。`rtl/wcis_pl_jpeg_preview.v` 已更新；视频/JPEG/UDP 数据通路、引脚和 PLL 参数没有因此修改。

状态同步适用于保持足够时间的单比特电平，不用于像素、地址或其他总线。ECO 只对新增同步链的首级 D 和三级复位链 PRE 入口设异步例外，后级数据和本地复位释放继续计时，没有放宽原时钟或旧数据路径。准备脚本已补充复制新模块；源级预览约束增加首级 D 的精确识别，并保留本地状态级 CLR 的时序检查。尚未以这些新源完成整板重新综合；旧候选源码有冻结副本，不能把旧综合结果当作新源综合结果。

`prepare_source_equivalent.py` 在任务 `equivalent-source/` 保存原厂写帧模块的对应源级修改、当前预览顶层与同步模块，并生成补丁/散列。原始案例及上一任务冻结源保持不变。ECO 后仍需要按真实原语接线核对，不能把“准备了对应 RTL”表述为已完成整板形式等价验证。

## 已完成验证

- `status-summary.json`：32 组数字时钟/相位组合，覆盖源域单周期事件保持、状态同步、清除和复位恢复。没有模拟模拟电路亚稳态。
- `writer-summary.json`：24 组组合，使用实际原厂 `frame_fifo_write.v`、`level_cross.v`，以及与原厂源相同的粘滞溢出产生方程，覆盖正常帧、溢出中止、下一正常帧恢复、再次溢出和恢复。检查空 FIFO 不发读突发、突发长度/计数和完成信号；没有证明 DDR 视频数据正确或板端结果。
- `control/summary.json`：12 个复位相位的预览控制回归通过，保留 PLL/视频源/PHY 替身边界。

## 实现工具问题与当前边界

第一轮 ECO 选位要求同一时钟区域整块 slice 空闲，该区域没有满足条件的位置，因此在新增原语前退出。第二轮只检查 FF 空闲，但原 LUT5/LUT6 的局部输入资源仍可阻止 FF 接入，放置失败。第三轮选择全芯片范围真正空闲的 slice，11 个新 FF 放置完成；保存的 `status-cdc-placed.dcp` 可继续使用。此前 140,865 个原语的名称、类型、LOC 与 BEL 向量保持一致，六个被移动的消费者在 `eco-ledger.txt` 中逐个列出。

随后逐引脚交互路由遇到两类问题：字符串列表必须先解析为真实 pin 对象；交互最短延迟/快速路由会出现与既有非固定走线的重叠。早先把 `-delay` 解释为数值参数不准确，已按安装版 `C:/Xilinx/Vivado/2018.3/doc/eng/man/route_design` 核对并更正：它是最短延迟模式，数值目标另由 `-max_delay/-min_delay` 指定。失败日志完整保留，不产生路由完成收据。

随后从保存的放置检查点执行 `resume_status_route.tcl`，使用 `route_design -preserve`。输入检查点有 116,577 条完整网络，12 条未布线、9 条部分缺少连接；本次 route_design 耗时约 3 分 3 秒，116,598 条可布线网络全部连通，路由错误为 0。真实 `status-cdc-routed.dcp`、报告和完成标记已生成，原有原语 LOC/BEL 保持一致。完整时序建立为 −0.189 ns（224 个失败端点）、保持 +0.029 ns（0 个失败），没有达到生成候选的门槛。

在此检查点上执行一次 `AggressiveExplore` 后路由物理优化，约 2 分 57 秒，得到 `status-cdc-postopt.dcp`；建立改善至 −0.176 ns（215 个失败端点）、保持 +0.029 ns，路由仍全部连通。既有 NPU 脉宽最差 −0.409 ns、2 个失败端点保持单列，不能称为生产时序签核。

`audit_status_topology.tcl` 已核对两个同步器的原语类型/初值、全部输入连接、五个写帧消费者、单个欠载消费者和三个必须保留的立即源域消费者，结果为 `STATUS_TOPOLOGY_AUDIT_PASS`。同步链后级及本地复位释放共有 20 项 min/max 检查，均保留计时且不为负，最小 +0.134 ns；首级 D 的例外从有效导出 XDC 和 False Path 报告核对。诊断脚本曾把空 SLACK 属性当作有约束路径，已核对报告中的 `Slack: inf / Timing Exception: False Path` 后修正，未改变设计约束。工具的 `report_exceptions` 导出/筛选参数组合不兼容导致的诊断失败日志也保留，不记作设计功能失败或审核通过。

完整负裕量端点清单显示 215 个端点来自 17 个时序起点，涉及旧摄像头数据/复位、NPU UI/HP 复位、MIG 内部复位及少数互连路径。因此没有仅凭“摄像头备用时钟较快”就降低时钟或放宽约束。下一独立候选 `D:/yzd/tmp/pl-critical-fanout-eco-20261025` 尝试对实际控制锥内的寄存器作相同初值、相同 C/D/CE/复位输入的复制以分担负载，不增加逻辑周期，保持全部时钟频率；仍须真实放置/路由和独立接线核对，不能将正在进行的尝试记作成功。保护为 DONT_TOUCH 的原厂网络不强行改写。

根目录准备脚本新增显式 `--synchronize-frame-error`，只修改新的候选副本，记录补丁与散列；对已有候选与当前根源码不一致的情况拒绝覆盖。源级实现/约束检查 hook 同步覆盖新写帧同步器。已完成 Python 语法检查，尚未运行整板新源综合，不能替代上述网表 ECO 的证据。

## 来源与归档

实现与测试来源：上述任务的 `prepare_source_equivalent.py`、`frame-error-cdc.patch`、`source-equivalence-inputs.json`、三项仿真收据、`apply_status_eco.tcl`、`resume_status_route.tcl`、`eco-ledger.txt` 及历次工具日志。当前修改源为 `rtl/wcis_status_sync.v`、`rtl/wcis_pl_jpeg_preview.v`、`sim/tb_status_sync.sv`、`sim/tb_frame_error_cdc.sv`、`scripts/verify_pl_preview_control.py`、`scripts/prepare_pl_jpeg_preview.py` 和 `constraints/pl_jpeg_preview_cdc.tcl`。

日期依据为本轮聊天日期 2026-10-25。同步合并归档到 `D:/bigfuture/竞赛/记录/2026-10-25.md`，保留当日其他来源块。
