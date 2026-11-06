# 模型来源、下载与使用

核对日期：2026-11-06。本文针对本 GitHub 公开源码版；本地完整交付包和公开仓库不是相同的文件集合。

## 公开仓库包含什么

仓库含推理调用、前后处理、模型改写及编译脚本、历史验证文档，以及 [models/](../models/README.md) 中三份原始权重（YuNet、MiniFASNetV2、MiniFASNetV1SE）及各自原许可。MobileFaceNet 原权重与所有板端模型 JSON/RAW 不随仓库提供。`.gitignore` 排除了整个 `reference_release/`，连同配套 BOOT、运行程序及模型一起排除。

原始 `.onnx` / `.pth` 是重建模型的输入；FMQL30TAI 服务加载的是与配套位流和 iCraft 运行时匹配的 `*_ZG.json` + `*_ZG.raw`。下载原始模型、安装 Python 包、编译 C++ 程序均不能代替模型适配和 NPU 编译。

## 四个模型及其来源

| 模型 | 原始文件 | 本项目输入与用途 | 原始来源 |
|---|---|---|---|
| YuNet | `face_detection_yunet_2023mar.onnx` | 640×640 BGR 补边图；人脸框和五点关键点 | [OpenCV Zoo 固定快照](https://github.com/opencv/opencv_zoo/tree/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_detection_yunet) |
| MobileFaceNet | `w600k_mbf.onnx`，来自 `buffalo_sc.zip` | 五点对齐的 112×112 RGB，数值 `(x-127.5)/127.5`；512 维特征 | [InsightFace v0.7 发布页](https://github.com/deepinsight/insightface/releases/tag/v0.7) |
| MiniFASNetV2 | `2.7_80x80_MiniFASNetV2.pth` | 同帧人脸框扩边 2.7 倍，80×80 BGR，0～255 | [MiniVision 固定提交](https://github.com/minivision-ai/Silent-Face-Anti-Spoofing/tree/b6d5f04ad78778917853b25c778acef6d5626d15) |
| MiniFASNetV1SE | `4_0_0_80x80_MiniFASNetV1SE.pth` | 同帧人脸框扩边 4.0 倍，80×80 BGR，0～255 | 同上 |

YuNet 的固定快照是此次核对的下载锚点，不冒充最初下载时的提交；该文件的 Git LFS SHA-256 与项目原始模型记录一致。不要改用上游新默认版本或 INT8 变体。MobileFaceNet 只取上述识别模型；本项目检测器是 YuNet，不是 `buffalo_sc` 包中的另一个检测器。

MiniFASNet 两个输出各做 softmax 再取平均；类别 1 是上游定义的活体类别。它不是经过本场景校准的“安全概率”。具体裁图和融合契约见 [PAD 说明](../源码/ps_source/docs/face-pad-minifas-20261018.md)。

## 下载原始权重

先阅读 [版权与许可](../THIRD_PARTY_NOTICES.md)。特别是 InsightFace 权重：上游声明仅限非商业研究；本文不额外授予模型使用或再分发权，也不认定任何竞赛、赞助或商业演示自动符合该范围。

**最快获取方式：** 下载本仓库 ZIP 或克隆仓库，三份可分发的原始权重已在 [models/](../models/README.md) 中。运行 `python models/verify.py` 校验它们。以下列出全部四个模型的上游下载地址，供补齐 MobileFaceNet 或核对来源。

需要把四个文件集中用于重建时，将本仓库三份权重复制到仓库外的独立模型目录，再把合法取得的 `w600k_mbf.onnx` 放到同一目录。内部学校服务器重建使用 `D:/yzd/tmp/<task>/`，不要写入共享 SDK；不要将 MobileFaceNet 或未审查的编译载荷提交到公开仓库。

1. **YuNet**：[下载实际 ONNX 文件](https://media.githubusercontent.com/media/opencv/opencv_zoo/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_detection_yunet/face_detection_yunet_2023mar.onnx)，保存为 `face_detection_yunet_2023mar.onnx`。同时保留上游 [MIT LICENSE](https://github.com/opencv/opencv_zoo/blob/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_detection_yunet/LICENSE)。该模型为 232589 字节；以 `version https://git-lfs...` 开头的短文本只是 LFS 指针，不是权重。
2. **MobileFaceNet（未随仓库提供）**：先确认用途符合 [上游模型政策](https://github.com/deepinsight/insightface#license)。从 [v0.7 的 buffalo_sc.zip](https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_sc.zip) 下载并解压，找到 `w600k_mbf.onnx`，复制到独立模型目录。下面校验的是解压后的 ONNX，不是整个 ZIP。
3. **MiniFASNetV2**：[下载固定版本权重](https://raw.githubusercontent.com/minivision-ai/Silent-Face-Anti-Spoofing/b6d5f04ad78778917853b25c778acef6d5626d15/resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth)。
4. **MiniFASNetV1SE**：[下载固定版本权重](https://raw.githubusercontent.com/minivision-ai/Silent-Face-Anti-Spoofing/b6d5f04ad78778917853b25c778acef6d5626d15/resources/anti_spoof_models/4_0_0_80x80_MiniFASNetV1SE.pth)。两份 PTH 的参考代码必须配套同一提交，许可见 [Apache-2.0 副本](../源码/ps_source/model_backend/licenses/Silent-Face-Anti-Spoofing-APACHE-2.0.txt)。

如需要 PAD 的代码、依赖清单和样本，已有 [固定版本下载脚本](../源码/ps_source/scripts/fetch_face_pad_school.py) 与 [逐文件校验清单](../源码/ps_source/scripts/face_pad_reference.json)。须把两者放在学校服务器 `D:/yzd/tmp/wcis-face-pad-<task>/` 同一目录再运行；该脚本拒绝其他目录，不是通用的本机安装器。

下载后，在四个文件所在目录运行下列 PowerShell 校验。缺文件或内容不符会停止；不要为了通过检查而改掉预期哈希。

```powershell
$ErrorActionPreference = 'Stop'
$expectedModels = @{
    'face_detection_yunet_2023mar.onnx' = '8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4'
    'w600k_mbf.onnx' = '9cc6e4a75f0e2bf0b1aed94578f144d15175f357bdc05e815e5c4a02b319eb4f'
    '2.7_80x80_MiniFASNetV2.pth' = 'a5eb02e1843f19b5386b953cc4c9f011c3f985d0ee2bb9819eea9a142099bec0'
    '4_0_0_80x80_MiniFASNetV1SE.pth' = '84ee1d37d96894d5e82de5a57df044ef80a58be2b218b5ed7cdfd875ec2f5990'
}
foreach ($modelEntry in $expectedModels.GetEnumerator()) {
    $actualModelHash = (Get-FileHash -LiteralPath $modelEntry.Key -Algorithm SHA256).Hash
    if ($actualModelHash -ne $modelEntry.Value) { throw "模型校验失败：$($modelEntry.Key)" }
    Write-Output "校验通过：$($modelEntry.Key)"
}
```

原始 YuNet/MobileFaceNet 哈希由项目本地 `photo_reference/models/manifest.json` 补录；PAD 哈希与仓库已有 `face_pad_reference.json` 一致。网络失败、权限失败或哈希不符不代表可以换任意同名镜像。本次重新从固定上游下载了随仓库提供的三份权重，并与上述历史哈希逐一核对；没有重新下载 MobileFaceNet，也没有运行模型推理。

## 从原始模型到板端模型

历史通过版本为 iCraft 3.39.0、zhuge、FP16、1 core、4 行 2 列。编译前仍须核对目标板与 SDK，不能沿用旧设备状态。

| 阶段 | 现有源码或记录 | 要保留的条件 |
|---|---|---|
| YuNet 导出与等价改写 | [export_yunet_logits.py](../源码/ps_source/npu_photo/export_yunet_logits.py)、[fuse_yunet_object_heads.py](../源码/ps_source/npu_photo/fuse_yunet_object_heads.py) | PS 执行末端 Sigmoid；六个 cls/object 分支合并，并保留固定 640 输入的边界修正 |
| MobileFaceNet 改写 | [rewrite_prelu.py](../源码/ps_source/npu_photo/rewrite_prelu.py) 的 `--conv-slope` | 用中心为 alpha 的深度卷积实现 PReLU 等价式；不能用早期失败变体代替 |
| 两个人脸模型编译 | [compile_face_models_school.py](../源码/ps_source/scripts/compile_face_models_school.py) | 选择对应改写输入，执行 parse → optimize → quantize → adapt → generate |
| PAD 导出、改写、编译 | [PAD 重建步骤](../源码/ps_source/docs/face-pad-minifas-20261018.md) | 固定上游版本，CPU/ONNX 对照，PReLU conv-slope 改写后 FP16 编译 |
| 同输入数值和板端验收 | [人脸模型历史验收](../源码/ps_source/docs/face-redeploy-20261015.md) | 对比输入、框、关键点、特征及身份结果；编译成功不能替代板测 |

这些是工程实现入口，**不是已经验证的“干净克隆后一条命令重建”流程**。部分改写脚本依赖 `photo_reference/`、历史 `outputs/` 和参考样本；公开仓库没有全部中间输入。`build_face_npu_models.py`、`continue_school_face_models.py` 还保留旧绝对路径和早期工具配置，不能照文件名直接运行。重建者须先准备隔离源码副本、参考输入和合法工具环境，再调整任务路径并复做等价性验证。不得仅把 `.onnx` 改名为 `.raw`。

## 安装与运行

### 只有公开仓库

可阅读和修改源码，直接取得随仓库提供的三份原始模型，按上游政策另行获取 MobileFaceNet。上板还缺少配套运行载荷、已编译模型、厂商 SDK/工具及位流；因此不能直接运行安装器并期待成功，也不能仅安装 `insightface` 或 `onnxruntime` 就得到本项目的 NPU 服务。

需要向有权提供资源的项目维护者或厂商取得匹配资源。私有源仓库的存在不代表任何读者都有访问或再分发权限。包中 `filelist.json`、`MANIFEST.json` 是完整包的历史清单，公开版刻意缺失受限文件；不要删减校验项目来伪造完整性通过。

### 已取得合法、完整且匹配的运行包

选择其中一个入口，不能把两套目录混合：

1. **安装器完整包**：依照 [FMQL30TAI-Install 使用说明](../FMQL30TAI-Install/使用说明.md)，准备 CPython 3.8、配套编译容器和可启动的板卡。运行 `sh install.sh` 或 `python3.8 install_py38.py`。它编译 PS 程序，使用包内模型，不负责重新下载或编译模型。
2. **手工板端运行包**：依照 [board_runtime 安装步骤](../源码/board_runtime/README.md)，上传完整运行目录、安装依赖、填写本板分区 UUID，执行 `render_install.py` 生成安装树，安装并启动服务。不要照抄历史 IP、分区名或 UUID。

完整包应包含以下模型配对及其元数据；相对位置从运行包根目录算起：

```text
reference_release/
  identity/
    models.json
    models/yunet_ZG.json
    models/yunet_ZG.raw
    models/mobilefacenet_ZG.json
    models/mobilefacenet_ZG.raw
  pad/
    pad-models.json
    MiniFASNetV2_ZG.json
    MiniFASNetV2_ZG.raw
    MiniFASNetV1SE_ZG.json
    MiniFASNetV1SE_ZG.raw
```

安装完成后检查 `http://板卡IP:8091/api/health` 和 `/api/camera/status`：模型就绪、相机会话有效且帧号持续增加，再用自己有权使用的人脸图片登记并验证识别。主站为 8091，预览为 8092，录像为 8093。修改模型还涉及预处理契约、人员特征库指纹、阈值和服务配置，不能只替换一个 RAW 文件。

本页补充来源与操作边界，未执行新的模型编译、安装、重启或板端验收。历史成功记录仅证明对应版本及用例；尤其不能外推为已完成 PAD 安全认证或真实场景准确率评估。
