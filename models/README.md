# 随仓库提供的原始模型

这里直接提供三份未经修改的上游权重。下载整个仓库（Code → Download ZIP）或 `git clone` 即可得到，无须 Git LFS，也无须另装 Python 包才能下载。单独下载时打开对应文件并选择 **Download raw file**，不要保存 GitHub 网页。

| 文件 | 字节数 | 许可 |
|---|---:|---|
| [YuNet ONNX](yunet/face_detection_yunet_2023mar.onnx) | 232589 | [MIT，保留 Shiqi Yu 的版权声明](yunet/LICENSE) |
| [MiniFASNetV2 PTH](minifasnet/2.7_80x80_MiniFASNetV2.pth) | 1849453 | [Apache-2.0，Minivision](minifasnet/LICENSE) |
| [MiniFASNetV1SE PTH](minifasnet/4_0_0_80x80_MiniFASNetV1SE.pth) | 1856130 | [Apache-2.0，Minivision](minifasnet/LICENSE) |

三份文件总计 3,938,172 字节。固定上游地址、完整 SHA-256 和许可路径见 [manifest.json](manifest.json)。它们保留各自原许可，不是作者原创模型，也不因根目录 MIT 而统一改用 MIT。

## 校验与下一步

在仓库根目录运行（Python 3.8 或更新版本，仅用标准库，无须安装依赖，不会联网或加载模型）：

```shell
python models/verify.py
```

返回码 0 代表三份文件的大小和 SHA-256 均匹配；缺失或不匹配返回 1。这只是文件完整性检查，不是模型推理测试。

这些 ONNX/PTH 用于模型研究、适配和重建。PTH 应配合 [上游固定提交的模型定义](https://github.com/minivision-ai/Silent-Face-Anti-Spoofing/tree/b6d5f04ad78778917853b25c778acef6d5626d15/src/model_lib) 使用；不能把本目录直接复制到板端 `reference_release/`，也不能改扩展名充当 NPU 模型。上板仍须使用匹配的 JSON/RAW、位流、运行程序和 SDK。具体见 [模型下载、转换及安装说明](../docs/MODELS.md)。

## 为什么缺 MobileFaceNet

`w600k_mbf.onnx` 来自 InsightFace 的 `buffalo_sc`，上游声明预训练模型仅限非商业研究，不能套用其代码的 MIT 许可。当前未核实到足以支持本仓库公开镜像的明确再分发授权，所以不在这里上传原权重或其转换产物；这不是断言所有再分发都被禁止。

符合上游使用范围的读者可按 [官方下载与校验步骤](../docs/MODELS.md#下载原始权重) 获取。下载链接不会消除使用限制，竞赛用途也不能自动视为合规。其他用途或公开镜像须向权利人确认，联系入口见 [InsightFace 官方许可说明](https://github.com/deepinsight/insightface#license)。

## 再分发依据与边界

- YuNet：固定快照的 [目录 README](https://github.com/opencv/opencv_zoo/blob/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_detection_yunet/README.md) 明确该目录所有文件采用 MIT。本目录保留许可全文与版权声明。
- MiniFASNet：两份 PTH 均位于固定提交 `b6d5f04ad78778917853b25c778acef6d5626d15` 的 `resources/anti_spoof_models/`；该仓库根 LICENSE 为 Apache-2.0。核对该提交文件树及 README，未发现权重目录另设许可或上游 NOTICE 文件，因此依据仓库许可随附原权重与许可全文。权重字节未修改；本说明和校验工具是项目新增内容。
- 核对日期为 2026-11-06。上述依据不代表已审计训练数据、人像权利或所有使用场景，也不授权分发厂商 SDK、位流和运行时。完整边界见 [第三方声明](../THIRD_PARTY_NOTICES.md)。
