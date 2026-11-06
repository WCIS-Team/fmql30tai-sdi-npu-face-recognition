# 第三方来源、版权与许可边界

核对日期：2026-11-06。此文为来源索引与条款摘要，不替换各组件的原许可，也不授予额外权利。核对范围是当前公开树的主要模型、复用组件和安装器依赖，不是对全部历史、训练数据或二进制内部依赖完成的法律审计。

## 原创代码与第三方内容分开授权

anxianji11-pixel 的署名覆盖其原创贡献，不覆盖上游模型、复用源码、厂商 IP、其他贡献者的作品。`HA4FPAI.sh` 为 takomitkm 的贡献；不能由其他人替其放弃版权或更换许可。

anxianji11-pixel 有权授权的原创代码和配套文档已采用根目录 [MIT License](LICENSE)，具体范围见 [LICENSE_SCOPE.md](LICENSE_SCOPE.md)。已有第三方文件级条款继续有效。公开可见不等于所有文件都可以任意使用或商用；GitHub 平台的查看/fork 权利与软件再利用许可并非同一件事，参见 [GitHub 许可说明](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)。

原创部分采用 MIT 不会把本目录中的第三方内容统一重许可，也不意味着整个模型和硬件系统不受限制。需按文件来源明确例外。

## 模型及模型参考代码

| 组件 | 版权/来源 | 许可与本项目边界 |
|---|---|---|
| YuNet 的 OpenCV Zoo 模型目录 | Shiqi Yu / OpenCV Zoo | 该目录声明 MIT；分发相关文件或实质部分须保留版权及许可。未经修改的原始权重已随 [models/](models/README.md) 提供，并保留原许可。见 [固定版本 README](https://github.com/opencv/opencv_zoo/blob/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_detection_yunet/README.md) 与 [LICENSE](https://github.com/opencv/opencv_zoo/blob/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_detection_yunet/LICENSE)。 |
| MobileFaceNet 预训练权重 `w600k_mbf.onnx` | InsightFace v0.7 `buffalo_sc` | **预训练模型仅限非商业研究**，不是 MIT 权重。本仓库不镜像其原权重或编译产物，提供上游获取与校验步骤；目前未核实到足以支持本仓库公开镜像的明确再分发授权，这不等于断言所有再分发都被禁止。上游明确将手动下载和自动下载都纳入其模型政策。商业使用须另行确认授权；转换为 ONNX/FP16/NPU RAW 不会自行消除上游限制。见 [官方模型政策](https://github.com/deepinsight/insightface#license)。 |
| InsightFace 五点对齐参考 | InsightFace `utils/face_align.py` | 上游代码声明 MIT，与模型政策分开。本项目参考提交为 `81929474ec02e54e3655f6841bced800009c592d`；实现及参考范围见 [face_geometry.py](源码/ps_source/model_backend/face_geometry.py) 和 [历史说明](源码/ps_source/model_backend/README.md)。不得把 MIT 代码许可推导成所有权重可商用。 |
| MiniFASNetV2 / MiniFASNetV1SE 及裁图参考 | MiniVision；裁图参考作者 Zhu Ying | 固定提交 `b6d5f04ad78778917853b25c778acef6d5626d15` 的上游仓库提供 Apache-2.0。本地 `face_pad.py` 已标注改编来源；保留 [许可全文](源码/ps_source/model_backend/licenses/Silent-Face-Anti-Spoofing-APACHE-2.0.txt) 与 [修改说明](源码/ps_source/model_backend/licenses/NOTICE.md)。两份未经修改的 PTH 已随 [models/](models/README.md) 提供，附原始 Apache-2.0 许可。已核对固定提交文件树及 README，未发现权重目录另设许可或上游 NOTICE 文件；分发依据是该仓库许可，不以本表保证训练数据或人像权利。 |

完整模型名、下载入口与 SHA-256 见 [模型说明](docs/MODELS.md)。这些模型不是本项目自主训练成果；适配、等价改写和编译也不应表述为拥有原始模型的全部版权。

## mjpegZero：不是纯 Apache-2.0

来源为 [Leonardo Capossio / bard0 design 的 mjpegZero](https://github.com/lcapossio/mjpegZero)，固定提交 `90bc0c46d2c2c4bda1020113f306a5f17dcc5f2f`。

- FPGA 副本：[源码/fpga_source/rtl/wcis/jpeg_vendor](源码/fpga_source/rtl/wcis/jpeg_vendor/)，含 [来源与文件哈希](源码/fpga_source/rtl/wcis/jpeg_vendor/sources.json)。
- 开发参考副本：[源码/ps_source/rtl/vendor/mjpegzero](源码/ps_source/rtl/vendor/mjpegzero/)。
- 两份 LICENSE 均包含 **Apache License 2.0 + Commons Clause v1.0**；部分源文件首行 SPDX 写 Apache-2.0，但紧接着已有 Commons Clause 声明，不能只读第一行。

本项目随附的 [完整条款](源码/fpga_source/rtl/wcis/jpeg_vendor/LICENSE) 对商业使用增加限制，并要求相关商业使用联系权利人取得许可；不是可以无条件商用的标准 Apache-2.0。保留 Commons Clause 通知和版权声明。是否进入某次位流需要查看该次构建输入，源码存在并不证明已部署，但源码再分发本身仍须保留条款。

这项限制不会因为与自有代码放在同一仓库就自动把所有原创文件变成同一许可；但含它的衍生实现或分发物不能仅贴自有 MIT/BSD/Apache 标签就消除限制。若要发布不受此条款限制的产品，需要取得覆盖用途的授权，或替换相关实现并核对产物。

## 安装器随附的 Python 库

以下信息取自两个平台实际随附的 `.dist-info/METADATA` 与 LICENSE，不是只依据包名猜测。文件位于 [FMQL30TAI-Install/vendor](FMQL30TAI-Install/vendor/)；下载 wheel 的版本和哈希见 [dependencies.json](FMQL30TAI-Install/licenses/dependencies.json)。该 JSON 是来源清单，不是许可证全文。

| 库 | 版本 | 随包声明 |
|---|---|---|
| Paramiko | 3.5.1 | LGPL-2.1-or-later（源码头允许 2.1 或更新版本） |
| bcrypt | 4.2.1 | Apache-2.0 |
| cffi | 1.17.1 | MIT |
| cryptography | 44.0.3 | Apache-2.0 OR BSD-3-Clause |
| pycparser | 2.22 | BSD-3-Clause |
| PyNaCl | 1.5.0 | Apache-2.0 |

Paramiko 在此以独立 Python 模块和源码分发，其 [LGPL 全文](FMQL30TAI-Install/vendor/windows-amd64/paramiko-3.5.1.dist-info/LICENSE) 和版权头必须保留；[对应上游源码](https://github.com/paramiko/paramiko/tree/3.5.1) 可用于版本核对。使用 LGPL 库不自动要求整个安装器采用 LGPL，但修改库、再分发库或改变打包方式时须履行相应源码和用户替换/修改权利等义务；不能移除许可后当成自有代码重发。

二进制 wheel 还可能包含 OpenSSL、libsodium、libffi、Rust 依赖等，须保留其包内附带的通知；上表不是所有嵌入依赖的完整物料清单。后续重新打包需按实际二进制再核对，不把顶层包的许可当作每个内部依赖的统一许可。

## 厂商资源和运行环境

FMSH、AMD/Xilinx、iCraft 的 SDK、IP、受限案例和启动资源按各自授权使用。本公开仓库将列明资源排除；不因文档给出文件名、构建方式或私有仓库地址而授予再分发权。`.gitignore` 不会自动清除已提交历史，也不是授权证明。

运行时还依赖厂商 Linux、FFmpeg、OpenCV 等组件。它们的义务取决于实际版本、构建选项和分发形式；当前未分发的系统包不能被本项目的原创代码许可覆盖。仅用 GCC 编译或在日志出现 GPL 文本，也不能直接推导出所有输出程序必须采用 GPL。

## 本次许可选择的边界

已发现有商用限制的模型与 RTL，以及 LGPL 库；因此不能声称整仓“无第三方限制”。这也不等于原创代码被自动强制改成 GPL。本次只给有权授权的原创贡献采用 MIT，同时保留上述组件的独立条款、署名和例外。

尚未取得其他贡献者同意的内容已从本次授权范围排除。MIT 不要求衍生软件公开源码，但须保留其要求的版权和许可声明；不得据此删除第三方署名、Commons Clause 或 LGPL 等原有条件。

公开示例照片、人员特征库和录像也不是软件许可授予的人像或个人信息使用权；不应随源码上传真实人员库。PAD 未校准的技术边界与版权许可是两回事，获得许可也不代表通过安全或准确率验证。
