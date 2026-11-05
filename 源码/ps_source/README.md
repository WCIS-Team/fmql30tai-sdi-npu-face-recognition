# PS 业务源码与开发资料

本目录用于开发；已编译程序、模型和安装入口在 [board_runtime](../board_runtime/README.md)。FPGA 设计资料在 [fpga_source](../fpga_source/README.md)，FPGA 恢复统一按 [总说明](../README.md) 使用 DCP。

| 入口 | 用途 |
|---|---|
| `ps_app/` | 相机采集及 PS 原生程序，构建入口为 CMakeLists.txt |
| `npu_photo/` | 人脸/PAD 推理、业务服务、网页和原生后端 |
| `model_backend/` | 模型后端辅助逻辑 |
| `lan_stream/` | 视频流、H.264 预览和相关测试 |
| `scripts/`、`tools/` | 开发、构建、诊断和发布工具；历史工具执行前须核对环境和路径 |
| `tests/`、`sim/` | 软件测试和硬件接口验证材料 |
| `include/`、`rtl/`、`constraints/`、`patches/` | 原开发工程的配套接口及历史实现参考；仅供查阅；FPGA 恢复使用外层 fpga_restore 中的 DCP |
| `docs/`、[PROJECT_HISTORY.md](PROJECT_HISTORY.md) | 工程文档与历史验证范围 |
| [发布历史](../logpack/05-release-receipts/) | 发布收据与历史快照，仅保留一份 |

保留原工程内部相对结构，以免破坏 CMake、导入和测试引用。历史文档中的旧绝对路径、outputs 路径和“当前状态”仅指当时记录，不表示交付包带有对应中间产物或板卡现状。源码区不携带编译输出和 Python 缓存。

原生 PS 程序需要 AArch64 工具链、iCraft/CustomOp 3.39.0 与配套依赖。历史交叉编译说明见 [构建记录](../logpack/repro-notes/04-校机交叉编译复现.md)，安装与新 BOOT 配置以 board_runtime 的当前说明为准。

当前网页仅按 [网页源码与运行入口](docs/website-current.md) 修改；release/ 仅保留历史索引，发布文件集中于 logpack/05-release-receipts；旧首页模板已移出交付包。
