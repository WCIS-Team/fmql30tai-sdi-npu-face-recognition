# 原上板 FPGA 实现资源

`refclk-final.dcp` 是保存的已布线设计，不是源码副本，也不是可以随意清理的缓存。当前恢复原上板位流依赖它。

SHA-256：`8e54e4cb42be0164d7925e9d2ef877745d663f79a87f4d8272414543441be2e8`。

按 [总说明](../README.md) 在 Vivado 中运行 `../fpga_source/restore_implemented.tcl`，随后用 Procise 打包 BOOT。生成结果放在包根目录 `build-restored/`；交付前应将生成结果移到包外。

配套最终报告在 [logpack/accepted-implementation](../logpack/accepted-implementation)，恢复与 BOOT 字节一致的历史证明在 [版本核对记录](../logpack/source-reconcile-20261104/README.md)。当前交付仅提供此 DCP 恢复流程。历史未完成的源码构建尝试不作为复现入口。
