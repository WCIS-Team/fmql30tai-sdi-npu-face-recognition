# MIG OOC 构建准备修复

2026-10-12，用户在本工程遇到 JFM `[runtcl-1] Not OOC IPs: mig_7series_0`。

## 现场证据

- `case/fpai_demo_vivado.runs/synth_1/runme.log` 显示工程已经打开，失败发生在顶层 synthesis_pre hook 的 `pre_patch_check`，不是 RTL 展开阶段。
- XPR 的 `IPCachePermission` 已经是 `disable`，但 `IPOutputRepo` 仍指向 Downloads 原工程的绝对路径；修复入口将其改到当前副本内。
- case 中确实存在随案例拷来的 `mig_7series_0.dcp`，但 JFM 没有认可当前 IP 的 OOC 构建条件。文件存在不能证明本工程的生成属性、缓存条件和独立综合状态正确。
- 本轮开始前，副本 `.runs` 下没有 MIG 的独立综合运行目录；只有顶层 synth/impl 的失败或未运行状态。
- 之前报告的完整 RTL 展开和两个新增模块综合，不等于厂商 IP 的 OOC 准备完成。这是之前交付的构建准备缺口。

## 当前窗口的修复入口

保持 `case/fpai_demo_vivado.xpr` 打开，在 **Vivado 的 Tcl Console** 中输入（不是 Windows PowerShell）：

```tcl
source D:/renlianshibie/fpga_project/scripts/repair_mig_ooc.tcl
```

脚本只处理 `mig_7series_0`：关闭 IP cache → 启用独立综合 checkpoint → reset/regenerate output products → 创建并运行 `mig_7series_0_synth_1` → 等待成功 → 重置失败的顶层 synth_1。忙时不会再启动同一 IP。

成功标志是 `WCIS OOC REPAIR PASSED`、`WCIS PROJECT PRECHECK PASSED`，以及 Design Runs 中 MIG 的 `synth_design Complete!`。脚本在 MIG 完成后重新调用厂商原来的 `pre_patch_check`，若别的 IP 也有问题会保留原报错。然后再按教程点击 Generate Bitstream。如果再次有报错，应读取新一轮完整日志，不能继续沿用这次的原因。

脚本不改 MIG 的 DDR 参数、引脚分配、工具时序数据库或板卡启动分区。reset/regenerate 会重建本副本中这个 IP 的生成文件；主工程下一轮 JFM hook 会按厂商流程处理它。

## 验证边界

用户的 GUI Vivado 正在打开实际工程，所以没有从另一个 batch 进程同时改它。验证项目在 `outputs/mig_check`，从本工程复制 MIG 后运行同一 `ooc_helpers.tcl` 流程。验证过程及结果在 `outputs/verify_mig_ooc.log` 与 `outputs/mig_check/project/mig_check.runs/mig_7series_0_synth_1/runme.log`。

隔离副本的成功不代表当前 GUI 工程已经修复，也不代表整板综合、布局布线、生成位流或板端 DDR 校准成功；用户还需在当前窗口运行上面的修复入口。

本轮实际完成：MIG 的 `synth_design Complete!`，综合阶段 0 errors／0 critical warnings（仍有 517 条厂商 IP warnings），新 DCP 已生成；随后用相同 JFM 工具包执行隔离项目的原始 `pre_patch_check`，输出 `Pre-patch check finished!` 和 `WCIS ISOLATED JFM PRECHECK PASSED`。对应日志为 `outputs/verify_mig_ooc.log`、`outputs/verify_mig_precheck.log`。
