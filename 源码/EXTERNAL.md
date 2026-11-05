# DCP 恢复所需外部资源

当前 FPGA 复现流程只使用原上板版已布线 DCP。操作见 [总说明](README.md)。

| 资源 | 用法 |
|---|---|
| Vivado 2018.3 与配套器件支持 | 打开 `fpga_restore/refclk-final.dcp` 并生成位流 |
| 配套 JFM_Kits / 30TAI 时序库 | 按《30TAI使用教程》第一章准备与原实现匹配的工具库 |
| Procise 2025.1.1 temp | 选择 JFMQL30TAI676H，按生成的命令执行 disable_icap 和 BOOT 打包 |
| FSBL251210_ddr400_demo.out、bl31.elf、u-boot | 放入 `fpga_source/boot/`，保留随包 `wcis.bif` |

三个启动组件应与历史恢复验证使用的版本一致：

| 文件 | SHA-256 |
|---|---|
| FSBL251210_ddr400_demo.out | `5501c470e07537a8fb369ae40641c20c16ab403fad558e65e0a4bbf380f2396f` |
| bl31.elf | `fdcf0af48a7f9716f73a477c3cc1b4cd90c914fe0e5ad7acc5ab282660802303` |
| u-boot | `c4570e3e51128211905bdf20c7b7e0ea9cb7ca1492652a070ebdd985bc213e97` |

组件校验来源为 `logpack/source-reconcile-20261104/boot-component-hashes.json`。历史核对的厂商补丁日志发布日期为 `2026/02/05`，时序库报告为 `PRODUCTION 1.11 2025-11-03`；工具库文件校验值见 `logpack/source-reconcile-20261104/tool-library-hashes.json`。

DCP 恢复不要求另行提供 AI_Mate.edif，不执行 BD/XCI 输出生成、IP 综合或综合实现钩子。

板端安装使用随包 `board_runtime`，要求厂商 AArch64 Linux；安装依赖见 [板端运行说明](board_runtime/README.md)。PS 程序开发所需 AArch64 工具链、iCraft/CustomOp 3.39.0、Modelzoo 依赖和内核 UAPI 属于独立的软件构建环境，不是 DCP 恢复的前置步骤，历史环境记录见 `logpack/repro-notes/04-校机交叉编译复现.md`。

电脑摄像头登记的可选本机入口需要 Python 3（仅标准库）；它与 FPGA 恢复、板端交叉编译无关。手机系统拍照和已有照片上传不需要此入口。
