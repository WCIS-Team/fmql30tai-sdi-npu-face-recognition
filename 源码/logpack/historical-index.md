# 日志包导引（2026-11-04）

官方包 `wcis-official.tar.gz` 之外的运行与验证日志。挑选原则：**支撑最终主张的原始记录**——现役版本怎么验收的、冻结实现的时序门怎么测的、BOOT 怎么证明逐字节可复现、工程怎么证明能重开，以及今天用官方包实测的板端证据。被回退实验的大体量过程日志（`evidence/stages` 约 1.87 GB）不在本包内，随全量包另行备份，哈希见 `submission/filelist.json`。

| 目录 | 内容 | 支撑的主张 |
|---|---|---|
| `01-board-runtime/` | **今天（11-04）板端实测证据**：自产 BOOT 的 SHA-256、块设备与 eMMC UUID、四个 systemd 服务状态原文、`/api/health` 与 `/api/camera/status` 原始 JSON、30 秒帧号连续采样（30 fps）、photo/storage 服务日志、本次开机 DHCP 全过程、dmesg 中 NPU/eMMC 行、实际运行中的单元内容与人员库计数 | 「按提交包 README 部署后，系统在真板上跑起来并持续供帧」 |
| `02-timing-and-drc/` | 冻结实现（10-20 SDI 参考时钟修复）的原始报告：`timing.rpt`（18.2 MB 完整时序）、`timing-gate.json`、`drc.rpt`、`bus-skew.rpt`、`route-status.rpt`、`candidate-proof.json`、`package-gate.json`、`accepted.json`、`build-and-board-manifest.json`、构建日志 | 「时序门结论的原始出处」（建立 +0.005 ns / 保持 +0.004 ns / 脉宽 2 条 NPU 厂商遗留告警，未完成完整签核） |
| `03-boot-reproduction/` | 用包内 `refclk-final.dcp` 重生成位流与 BOOT 的全过程：`bitgen.log`、`bitgen.jou`、`rtl-synthesis.log`、`package.log`、`boot-compare.json`、`portable-boot-compare.json`（重打包 BOOT 与提交版逐字节一致的证明）、`rtl-sim-summary.json` | 「§四 位流与 BOOT 可复现，且逐字节一致」 |
| `04-project-reopen/` | 工程重开检查：`restore-open.log`、`reopened_route_status.rpt`、`reopened_utilization.rpt`、`verification.json`、Vivado 源码编译顺序 | 「提交的 Vivado 工程能被重新打开」 |
| `05-release-receipts/` | 四个现役发布记录（`540p-r2`、`preview-h264-live-20261103`、`recording-idle-20261031`、`vision-voice-handoff-20261103`）的验收收据、清单、来源映射与回滚件 | 「现役软件是哪一版、验收结论与散列是什么」 |
| `07-stages/` | **12 个实验阶段的精选日志**：全部结论层收据（102 个 json/md）、冻结解来源阶段全量、NPU 周期厂商核查全量、每阶段 1 份代表性时序报告（详见其内 README） | 「每个阶段都真的做过、记过、判过（含失败与回退）」 |
| `06-frozen-solution-stage/` | 冻结解来源阶段（10-20 SDI refclk 修复）的原始构建日志与证明：布线计划、console 原始输出、`capture.log`、候选证明等 | 「冻结 DCP 是怎么来的」 |

## 复核方式

- `01-board-runtime/` 内的 BOOT SHA-256 应为 `f6da96abbc0144ce5a48f4fa85aed6dab65067211b8932e8f4e4db87d5110297`，与 `submission/reference_release/boot/BOOT.bin` 一致。
- 其余各目录的文件散列可在 `submission/filelist.json` 中按相对路径核对（包内路径前缀 `submission/`）。
- 本包只做复制与去重，未修改任何原始日志内容。

## 未包含的内容及原因

| 未包含 | 原因 |
|---|---|
| `evidence/stages/` 其余约 1.87 GB | 主要是被回退实验（PL 预览续作、人脸缓存保全等）的原始 Vivado 日志与 26 MB 级中间时序报告；对复现无用，但**证明过程诚实（含失败与回退）**，随全量包备份 |
| `implementation_baseline/boot-candidate/boot-image-dump.txt`（20 MB） | BOOT 的十六进制人工快照，现由 SHA-256 取代；随全量包 |
| 各 IP 的 OOC 综合产物 | 可由 `.xci` regenerate，随全量包 |
