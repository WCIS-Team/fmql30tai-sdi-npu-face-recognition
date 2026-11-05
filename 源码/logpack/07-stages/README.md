# stages 精选（2026-11-04）

`submission/evidence/stages` 共 12 个实验阶段、原始 1863 MiB。体积构成（实测）：

| 类别 | 体积 | 性质 |
|---|---|---|
| `.rpt`（各阶段中间候选的时序报告，19–26 MiB 一份） | 888 MiB | 过程留痕；最终那份时序报告已在 `02-timing-and-drc/timing.rpt` |
| `.tcl`（`preservation-reference.tcl` 等重布线状态保全脚本，内含数万条 cell/net 名） | 357 MiB | **工具输入**，不是证据输出 |
| `case/` 目录拷贝、失败候选的构建目录等 | ~617 MiB | 中间产物 |
| **结论层（`*.json` / `*.md`：verification、proof、receipt、acceptance、audit、计划说明）** | **0.6 MiB / 109 文件** | **证据核心** |

因此本目录按「结论层全留 + 代表性时序报告 + 冻结解全量」挑选：

| 目录 | 内容 | 说明 |
|---|---|---|
| `00-stage-conclusions/<stage>/` | 12 个阶段**全部**结论层文件（102 个） | 每轮的验收/证明/审计收据，证明每轮都真的做过、记过、判过（含失败与回退） |
| `01-frozen-solution/sdi-refclk-fix-20261020/` | **全量 55 文件** | 冻结解（板上现役 BOOT 所依据的布线结果）的来源阶段，含完整时序报告与首次布线结果 |
| `02-npu-period-review/npu-min-period-20261022/` | 全量 13 文件 | 两条 NPU 最小周期告警的厂商核查材料，支撑「未完成完整时序签核」的诚实结论 |
| `03-stage-timings/<stage>/` | 其余 9 个阶段各 1 份代表性时序报告（最大 `.rpt`） | 证明每个阶段都真的跑过实现，而不是只写结论 |

## 各阶段与现役的关系

| 阶段 | 结论 |
|---|---|
| `sdi-refclk-fix-20261020` | **现役硬件来源**：10-20 SDI 参考时钟修复后冻结的布线结果，即 `refclk-final.dcp` |
| `npu-min-period-20261022` | NPU 最小周期告警厂商复核；按用户选择保留 1 GHz，两项最小周期失败未消除 |
| `face-pl-integration-20261015` | PL 与人脸首次集成并板测通过 |
| `pl-jpeg-board-20261016` | PL JPEG 板测通过（后被 540p H.264 方案取代） |
| `face-pl-cache-20261018` / `face-pl-20261015` | 缓存与识别基础实现 |
| `face-cache-board-20261018` / `face-cache-preserve-20261018` / `face-cache-resume-20261020` | 人脸缓存系列实验；部分候选实测失败后回退，原始日志保留以证过程 |
| `pl-command-validation-20261022` | PL 命令校验流水化，生成候选后按要求暂不上板 |
| `pl-fastpath-board-20261022` | PL 快路径板测候选，WNS −0.069 ns，未采用 |
| `pl-preview-resume-20261027` | PL 预览续作与后续复核；10-28 候选实板未通过，已回退原 BOOT，**该候选不得未经修复重部署** |

## 未包含

- 上述各阶段的中间构建目录、`case/` 拷贝、失败候选的时序报告（除每阶段保留的一份）——随全量包备份，哈希见 `submission/filelist.json`。
- `preservation-reference.tcl`（357 MiB 合计）——重布线状态保全工具输入，非证据输出。
