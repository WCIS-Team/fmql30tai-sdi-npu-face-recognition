# fmql30tai-sdi-npu-face-recognition

FMQL30TAI（FMQL30TAI676 悟净）平台上的 **SDI 采集 + NPU 人脸识别** 工程：板端安装器、PS/NPU 应用源码、FPGA 源（我方 RTL）、以及构建与复现记录。

## 来源与署名

- **作者 / 维护者**：anxianji11-pixel（https://github.com/anxianji11-pixel ，WCIS-FPAI 的 contributor）
- **来源仓库**：https://github.com/WCIS-Team/WCIS-FPAI （原目录 `repos/fmql30tai-sdi-npu-face-recognition`）
- **上传说明**：本仓库由 **takomitkm 代 anxianji11-pixel** 建仓并上传；内容作者身份与版权归 anxianji11-pixel。（`HA4FPAI.sh` 由 takomitkm 本人提交，见其提交记录。）
- **组织**：WCIS-Team

## 内容说明（公开版：厂商内容用 .gitignore 排除，原件仍在本地）

本公开仓库不纳入厂商机密 / 授权内容，仅保留我方自有代码与文档。被 `.gitignore` 排除（仅本地保留）的包括：

- 上海复旦微电子（FMSH）标注 *Confidential* 的 `sdi / display / gp / adder_op / utils` 等 RTL 源码
- AMD/Xilinx `processing_system7` 专有 IP 及生成 IP（`rtl/ip`）
- iCraft 3.39.0 板端 SDK 二进制（`*.deb`）与 iCraft SDK C++ 头文件
- Vivado 实现检查点 `*.dcp`
- 厂商预编译运行时 / 引导载荷（`reference_release`、`sdk`）

需要含厂商内容的完整工程，请见私有源仓库 WCIS-FPAI。

## 目录

- `FMQL30TAI-Install/` —— 板端安装器（脚本、payload、校验、依赖清单）
- `源码/ps_source/` —— PS 侧应用与 NPU 模型后端源码
- `源码/fpga_source/` —— FPGA 工程：约束、Vivado 工程、我方 `rtl/wcis/` RTL（厂商 RTL 已排除）
- `源码/logpack/` —— 构建 / 复现记录与时间线
- `源码/board_runtime/` —— 板端运行时脚本
- `HA4FPAI.sh` —— 从 HA4FPAI 最新 Release 安装 `.deb` 的便捷脚本（takomitkm 提交）

## 许可

我方代码见各文件头。第三方组件见 `FMQL30TAI-Install/licenses/dependencies.json` 与 `源码/ps_source/model_backend/licenses/`（例如 Silent-Face-Anti-Spoofing：Apache-2.0；mjpegzero JPEG 编码器：Apache-2.0）。