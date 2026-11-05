# 验证记录与历史资料

这些目录用于查证，不参与板端安装。当前 FPGA 复现只采用 [总说明](../README.md) 的 DCP 恢复流程；历史正文中的源码构建命令与未完成尝试不作为交付操作步骤或推荐路线。文件名里的日期和版本属于当次记录，不能单凭旧记录判断板卡当前状态。

| 目录 | 内容 |
|---|---|
| `accepted-implementation/` | 原上板实现的最终报告、准入与证明；DCP 已单独放在 ../fpga_restore |
| `source-reconcile-20261104/` | 源码修正、功能仿真、DCP 恢复及 BOOT 一致性证明 |
| `01-board-runtime/` | 历史板端运行检查 |
| `02-timing-and-drc/`、`03-boot-reproduction/`、`04-project-reopen/` | 时序、BOOT 和工程重开证据 |
| `05-release-receipts/`、`06-frozen-solution-stage/`、`07-stages/` | 发布收据和实验阶段记录，含失败与回退 |
| `source-import-20261104/`、`source-build-20261104/` | 较早的不完整源码尝试，不作为最终版本通过证明 |
| `repro-notes/` | 历史复现操作与限制说明 |

历史正文及日志保留原字节，因此仍可能出现旧目录、旧文件数和旧压缩包名。当前交付结构以根 README 和 filelist.json 为准，旧路径到新路径的规则见 `layout-map.json`。`historical-index.md` 为旧日志包目录说明。

去重后的保留位置见 `duplicate-files.json`：removed 字段记录原始位置，retained 字段指向本包当前保留文件，路径均相对包根目录。未保留的中间候选报告、journal、BOOT 十六进制快照等备份在包外 `D:/yzd/tmp/final-package-cleanup-20261104/`。

本次只整理目录和交付说明，没有重新生成位流、部署或板端功能验收。未完全时序签核等历史限制仍然成立。

当前网页与交付清理核对见 [website-current](website-current/README.md)。本轮旧页面及修改过程记录已归档到包外 `D:/yzd/tmp/delivery-website-final-cleanup-20261104/`。历史发布清单中仍可能记载已归档的旧网页，它们不参与当前安装。

duplicate-files.json 的 files 表示当前相同文件，superseded 表示清理后更新的保留文件，archived 表示本轮已移出包的旧保留位置；archived 项以 archive_path 定位包外副本。

2026-11-04 源码去重：ps_source/release 中 26 份完全重复的发布文件已移出，原件统一保留在 05-release-receipts；保留位置见 duplicate-files.json。源代码和运行文件未改写。
