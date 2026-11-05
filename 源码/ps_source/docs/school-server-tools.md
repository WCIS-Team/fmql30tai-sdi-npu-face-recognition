# 学校服务器工具与目录盘点

日期：2026-10-13。实际通过 SSH 登录学校 Windows 服务器检查，项目写入限定在 `D:/yzd/tmp/wcis-fpga-20261013-62670b32`。已有工具、环境和其他项目均只读使用。

## 可以直接复用的已验证工具

| 内容 | 位置 | 实际验证 | 可用于 |
|---|---|---|---|
| Arm GNU GCC/G++ 10.3.1 | `D:/yzd/tools/cross/gcc-arm-10.3-2021.07-mingw-w64-i686-aarch64-none-linux-gnu/bin` | 已编译并链接本项目 aarch64 Linux 程序 | 板端 C/C++ 交叉编译 |
| CMake 4.4.4 / Ninja 1.13.2 | `D:/yzd/MSYS2/mingw64/bin` | 版本命令和本次构建通过 | 构建配置、编译调度 |
| Bash 5.3.20 / Git 2.56.0 | `D:/yzd/MSYS2/usr/bin` | 版本命令通过；Bash 已执行构建脚本 | 脚本与版本管理工具入口 |
| iCraft/CustomOp 3.39.0 kit | `D:/yzd/WCIS/crosswin/kit` | 包配置版本为 3.39.0.0，本次已链接其库 | aarch64 iCraft 应用开发 |
| OpenCV C++ 4.5.5 / YAML | `D:/yzd/WCIS/crosswin/kit/ModelzooDeps/aarch64/Static` | CMake 找包、实际静态链接通过 | 图像和配置文件处理 |
| 板端内核 UAPI | `D:/yzd/WCIS/crosswin/uapi` | 已作为本次交叉编译的头文件输入 | Linux 驱动接口头文件；不代表每个接口已上板测试 |

非交互 Bash 默认 PATH 当次未包含 mingw64/bin，因此一开始 `cmake`/`ninja` 命令未找到；工具文件实际存在。构建脚本为该进程显式加入工具链和 mingw64/bin，不改全局环境。

## Python：安装、启动与运行分开记录

共找到 13 个 python/python3.exe 路径（包含同一套 MSYS2 解释器的别名）。这些路径均执行 `--version` 成功。

| 环境 | Python / 关键包 | 实际运行结论 |
|---|---|---|
| `D:/yzd/qwen3/venv` | Python 3.12.15；NumPy 1.26.4、PyTorch 2.14.1+cpu、ONNX 1.23.2、ORT 1.31.0 | NumPy/PyTorch CPU 加法、ONNX 图检查和 ORT CPU 小图推理通过 |
| `D:/yzd/asr/onnx/env_export` | Python 3.12.15；NumPy 2.5.3、PyTorch 2.14.1+cpu、ONNX 1.23.1、ORT 1.20.1 | 同上，通过；没有执行音频程序 |
| `D:/yzd/asr/onnx/env_ort1.18` | Python 3.12.15；NumPy 1.26.4、ORT 1.18.1 | ORT CPU 小图推理通过 |
| `D:/yzd/asr/onnx/env_ortonly` | Python 3.12.15；NumPy 1.26.4、ORT 1.24.4 | ORT CPU 小图推理通过 |
| `D:/yzd/asr/onnx/env_ort1.17` | Python 3.12.15；NumPy 2.5.3、ORT 1.17.1 | **ORT 导入失败**，运行时明确报告 NumPy 1.x/2.x ABI 不兼容；没有修改该共享环境 |
| `D:/yzd/asr/onnx/env` | Python 3.12.15；NumPy 2.5.3、ORT 1.20.1、SciPy 1.18.1 | 解释器启动和包元数据检查；包运行未测 |
| `D:/yzd/asr/onnx/env_ort1.21` / `env_ort1.22` / `env_punc` | Python 3.12.15；分别 ORT 1.21.0 / 1.22.0 / 1.24.2 | 解释器启动和包元数据检查；包运行未测 |
| `D:/yzd/asr/onnx/py/cpython-3.12.15-windows-x86_64-none` | Python 3.12.15，pip 26.2.1 | 解释器启动与元数据查询通过 |
| `D:/yzd/asr/python` | Python 3.13.16 | 解释器启动与标准库元数据查询通过 |
| `D:/yzd/MSYS2/ucrt64/bin/python.exe`（另有 python3.exe） | Python 3.14.8 | 解释器启动与标准库元数据查询通过 |

“当时 Python 进程数为 0”是构建前的进程快照，**不是没有 Python，也不代表以后可以不检查现有任务**。CPU 小图验证不代表 Qwen、ASR 或任意业务模型已经验证。

## D:/yzd 中的主要目录

| 目录 | 本次观察与使用边界 |
|---|---|
| `MSYS2` | shell、构建工具、原生 x64 编译器、Python 等；原生 x64 gcc/g++ 只发现文件，未编译自测 |
| `tools/cross` | 已验证的 Arm Windows 交叉工具链 |
| `WCIS/crosswin` | kit、UAPI、源码、参考构建脚本、既有产物；本次只读，不运行会清理其 build/kit 的总脚本 |
| `WCIS/fdw` | 厂商资料目录；不凭目录存在宣称所有工具都能运行 |
| `asr` | 音频相关源码、模型、ONNX 和多套 Python 环境；本次仅解释器与小型 CPU 通用运算验证 |
| `qwen3` | CPU/CUDA 形态的模型目录、ONNX 文件和已验证 CPU Python 环境；CUDA 文件存在不代表 GPU 可用 |
| `llm` | assistant、qwen2、qwen3、router 子目录；不启动业务程序 |
| `.opencode` / `agenttmp` / `_work` | 程序、代理任务、工具及素材缓存目录；只观察目录，不执行未知入口 |
| `proxy` | 代理相关目录；不读取凭据或更改设置 |
| `rclone-v1.75.1-windows-amd64` | 发现目录，未做同步或网络操作 |
| `deploy1012` / `tmp_tunnel_stage` | 发现既有目录；未更改 |
| `tmp` | 用户指定本项目缓存根；所有本次工程上传、源码、结果、日志和编译临时文件在任务子目录 |

目录扫描深度为 2，常规程序/模型扫描为 4，Python 与指定工具根追加至 5/6；不能据此宣称查完所有深层文件。在这些扫描中没有发现可直接调用的 Vivado、Procise 或 Windows iCraft CLI，**不据此断言整台服务器未安装它们**。无管理员权限、无 WSL、无 GPU 为用户提供的限制，本次没有提权或安装这些能力。

## 本次编译产物

服务器：`D:/yzd/tmp/wcis-fpga-20261013-62670b32/build/wcis_sdi_reference`。

本机副本：`D:/renlianshibie/fpga_project/outputs/ps_app/wcis_sdi_reference`，4,671,984 B，SHA256 `ea8135622061745f67dacae1e9bc5a0d46f8c0b7c86735ae16bff3bb5c4bb46d`。

已经证明是 ELF64/AArch64，在板端核对传输校验、解析全部动态依赖，并成功执行 `--help`。没有打开 NPU/摄像头会话或进行推理；没有替换 BOOT。板端实测 libc6 为 2.31-0ubuntu9.18、libstdc++6 为 10.5.0，iCraft/CustomOp 为 3.39.0。

配套程序仍是原 YOLOv5 SDI 参考通路＋可选帧率控制，不是新人脸模型业务完成证据。FPGA BOOT 候选的时序仍未通过。

日志：本机 `outputs/school_inventory.log`、`outputs/school_runtime_checks.log`、`outputs/school_build.log`、`outputs/ps_app/board_loader_check.json`；服务器元数据与构建日志保存在任务目录内。
