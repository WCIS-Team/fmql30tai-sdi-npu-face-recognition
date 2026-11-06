# fmql30tai-sdi-npu-face-recognition

FMQL30TAI（FMQL30TAI676 悟净）平台上的 **SDI 采集 + NPU 人脸识别** 工程：板端安装器、PS/NPU 应用源码、FPGA 源（我方 RTL）、以及构建与复现记录。

> **这是公开源码版，不是可直接上板的完整安装包。** Git 中已附带 YuNet 和两个 MiniFASNet 的原始权重及各自许可；MobileFaceNet 需按上游条款另行下载。仓库仍没有编译后的板端模型、配套 BOOT、SDK deb 或 DCP。克隆成功不代表安装资源齐全；历史文档中的“随包模型”“一键安装”针对另行准备的完整包。

## 模型、下载与运行入口

| 用途 | 模型 | 上游 |
|---|---|---|
| 人脸框与五点关键点 | YuNet，`face_detection_yunet_2023mar.onnx` | OpenCV Zoo / Shiqi Yu |
| 身份特征与余弦比较 | MobileFaceNet，`buffalo_sc.zip` 内的 `w600k_mbf.onnx` | InsightFace |
| RGB 防伪辅助分数 | MiniFASNetV2 + MiniFASNetV1SE，80×80 双模型 | MiniVision Silent-Face-Anti-Spoofing |

- [直接下载随仓库提供的三份原始权重](models/README.md)：含原许可、来源清单及离线校验工具。
- [模型来源、固定文件、下载和 SHA-256 校验](docs/MODELS.md)：说明原始 ONNX/PTH 与板端 JSON/RAW 的区别，以及现有构建脚本的适用范围。
- [安装前需补齐的资源与运行步骤](docs/MODELS.md#安装与运行)：公开版缺什么、完整包从哪里安装、怎样确认模型就绪。
- [第三方版权与许可边界](THIRD_PARTY_NOTICES.md)：特别注意 InsightFace 权重的非商业研究限制、mjpegZero 的 Commons Clause 和 Paramiko 的 LGPL。

这些是上游预训练模型；本项目的工作是模型适配、预处理、板端推理与系统集成，不宣称训练了这些基础模型。PAD 分数尚未完成面向本摄像头和场景的安全标定，不能直接作为开锁许可。

## 来源与署名

- **作者 / 维护者**：anxianji11-pixel（https://github.com/anxianji11-pixel ，WCIS-FPAI 的 contributor）
- **来源仓库**：https://github.com/WCIS-Team/WCIS-FPAI （原目录 `repos/fmql30tai-sdi-npu-face-recognition`）
- **上传说明**：本仓库由 **takomitkm 代 anxianji11-pixel** 建仓并上传；anxianji11-pixel 的署名仅覆盖其原创贡献，第三方组件及其他贡献者的权利保留。（`HA4FPAI.sh` 由 takomitkm 本人提交，见其提交记录。）
- **组织**：WCIS-Team

## 内容说明（公开版：厂商内容用 .gitignore 排除，原件仍在本地）

本公开仓库按以下规则排除厂商受限资源，同时保留项目代码、文档及带原许可的第三方组件。`.gitignore` 是打包排除规则，不是对所有文件权属的证明。被排除（仅本地保留）的包括：

- 上海复旦微电子（FMSH）标注 *Confidential* 的 `sdi / display / gp / adder_op / utils` 等 RTL 源码
- AMD/Xilinx `processing_system7` 专有 IP 及生成 IP（`rtl/ip`）
- iCraft 3.39.0 板端 SDK 二进制（`*.deb`）与 iCraft SDK C++ 头文件
- Vivado 实现检查点 `*.dcp`
- 完整运行载荷（`reference_release`，其中也包含项目使用的第三方模型）及 SDK（`sdk`）

有权访问者可向项目维护者确认私有源仓库 WCIS-FPAI 中的配套完整工程；厂商资源仍须通过合法授权渠道取得。公开仓库不提供这些资源的下载授权，也未提供可替代完整载荷的公共下载包。

## 目录

- `FMQL30TAI-Install/` —— 板端安装器源码、部分 payload、校验及依赖清单；完整安装载荷未公开
- `源码/ps_source/` —— PS 侧应用与 NPU 模型后端源码
- `源码/fpga_source/` —— FPGA 工程：约束、Vivado 工程、我方 `rtl/wcis/` RTL（厂商 RTL 已排除）
- `源码/logpack/` —— 构建 / 复现记录与时间线
- `源码/board_runtime/` —— 板端运行时脚本
- `HA4FPAI.sh` —— 从 HA4FPAI 最新 Release 安装 `.deb` 的便捷脚本（takomitkm 提交）

## 许可

**anxianji11-pixel 有权授权的原创代码和配套文档采用 [MIT License](LICENSE)**，允许商用、修改和再分发，须保留版权及许可声明。具体适用范围和第三方例外见 [LICENSE_SCOPE.md](LICENSE_SCOPE.md)，作者与贡献范围见 [NOTICE.md](NOTICE.md)。其他作者的独立贡献不由本次声明代为授权。

第三方代码、模型和厂商资源不因本项目选择某种许可而改变原条款。完整索引见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。其中 **mjpegZero 是 Apache-2.0 + Commons Clause v1.0，并非纯 Apache-2.0**；InsightFace 的 MIT 代码许可也不等于其预训练权重许可。
