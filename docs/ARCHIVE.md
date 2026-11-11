# FMQL30TAI 视觉工程归档索引

归档日期 2026-11-11。公开源码基线为 `5a75594564caa498e410cac28e35026d0174affb`。板端交付对应 2026-11-04 整理的 SDI 采集、NPU 人脸识别、H.264 预览和录像版本。

## 源码与验证记录

| 内容 | 入口 |
| --- | --- |
| FPGA 自有 RTL、约束及恢复脚本 | [FPGA 源码说明](../源码/fpga_source/README.md) |
| PS/NPU 应用、预处理、预览与录像 | [PS 源码说明](../源码/ps_source/README.md) |
| 安装器与手动运行流程 | [安装器说明](../FMQL30TAI-Install/使用说明.md) · [板端运行说明](../源码/board_runtime/README.md) |
| 原始模型、板端模型格式与获取步骤 | [模型说明](MODELS.md) · [公开权重](../models/README.md) |
| 原上板版本的验证边界 | [最终实现记录](../源码/logpack/accepted-implementation/) · [源码与恢复核对](../源码/logpack/source-reconcile-20261104/) |
| 完整包清单与外部依赖 | [源码包清单](../源码/filelist.json) · [安装包清单](../FMQL30TAI-Install/MANIFEST.json) · [外部资源](../源码/EXTERNAL.md) |

## 恢复原上板版本

完整交付使用 Vivado 2018.3、配套 JFM_Kits 时序库、Procise 2025.1.1 temp 和目标器件 JFMQL30TAI676H。先取得匹配的运行载荷、iCraft/CustomOp 3.39.0、已布线 DCP 及三个启动组件，再按[交付说明](../源码/README.md)恢复。完整包和外部资源的获取受各自许可约束，详见[许可范围](../LICENSE_SCOPE.md)。

| 恢复文件 | SHA-256 |
| --- | --- |
| `fpga_restore/refclk-final.dcp` | `8e54e4cb42be0164d7925e9d2ef877745d663f79a87f4d8272414543441be2e8` |
| `board_runtime/reference_release/boot/BOOT.bin` | `f6da96abbc0144ce5a48f4fa85aed6dab65067211b8932e8f4e4db87d5110297` |
| `FSBL251210_ddr400_demo.out` | `5501c470e07537a8fb369ae40641c20c16ab403fad558e65e0a4bbf380f2396f` |
| `bl31.elf` | `fdcf0af48a7f9716f73a477c3cc1b4cd90c914fe0e5ad7acc5ab282660802303` |
| `u-boot` | `c4570e3e51128211905bdf20c7b7e0ea9cb7ca1492652a070ebdd985bc213e97` |

此分支固定公开源码。原板卡恢复还需要另存的完整运行载荷和厂商资源。已记录的 FPGA 恢复流程以 DCP 为输入，纯源码重建未完成验证。归档时只做了文件与版本核对。
