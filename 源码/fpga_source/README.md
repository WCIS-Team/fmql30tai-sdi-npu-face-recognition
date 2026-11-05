# FPGA 设计资料与 DCP 恢复脚本

本交付包的 FPGA 复现统一采用保存的已布线 DCP。完整操作见 [总说明](../README.md)：读取 `../fpga_restore/refclk-final.dcp`，生成位流，再用 Procise 打包 BOOT。

## 操作入口

| 文件 | 用途 |
|---|---|
| `restore_implemented.tcl` | 在 Vivado 2018.3 中直接打开原上板 DCP，输出位流、报告和 Procise 命令 |
| `package_restored.tcl` | 由生成的 Procise 命令调用，执行 disable_icap 并打包 BOOT |
| `boot/wcis.bif` | 原上板版启动分区配置；三个外部启动组件放在同目录 |

保留整个包的目录结构。恢复时不新建 RTL 工程，不生成 IP，不重新综合、布局或布线。输出位于包根目录 `build-restored/`。

## 设计资料

`rtl/`、`constrs_1/`、BD、XCI、MIG PRJ 和 `PS_AI IP/` 保留供查阅与追溯。`design-files.txt`、`constraints-files.txt` 是设计文件索引。JPEG 第三方许可位于 `rtl/wcis/jpeg_vendor/LICENSE`。AI_Mate.edif 不随包提供；直接恢复 DCP 不需要补入它。

纯源码构建未完成完整实现和板端验证，已从当前交付操作说明中撤下，不作为复现方式或推荐流程。历史实验记录仅供追溯。

DCP 与 BOOT 的历史一致性证明见 [版本核对记录](../logpack/source-reconcile-20261104/README.md)，原实现报告见 [accepted-implementation](../logpack/accepted-implementation)。
