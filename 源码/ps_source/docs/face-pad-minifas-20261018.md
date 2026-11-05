# 普通摄像头防伪模型原型（2026-10-18）

2026-10-21补充：[真实SDI采样初测](face-pad-camera-20261021.md)已完成真人与手机静态/视频三个短片段；打印未测，尚未校准或接入正式服务，新PL裁图仍未部署。下文为10月18日原型证据。

已复用MiniFASNet官方双模型，在学校服务器完成CPU参考、ONNX导出、等价改写、iCraft编译和AArch64交叉编译，
并在当前FMQL30TAI板卡上实际执行两套NPU模型。新增PL裁图适配RTL通过20组仿真。
**新PL模块尚未接入整板CustomOp/位流；当前板端测试入口使用PS/OpenCV参考裁图。真实SDI防照片效果尚未验收。**
本次范围是独立ModelBackend，没有新增前端、权限调度或开锁动作。

## 复用来源和模型契约

- 上游：[MiniVision Silent-Face-Anti-Spoofing](https://github.com/minivision-ai/Silent-Face-Anti-Spoofing/tree/b6d5f04ad78778917853b25c778acef6d5626d15)。
- 固定提交：`b6d5f04ad78778917853b25c778acef6d5626d15`。许可副本及改编说明在`model_backend/licenses/`。
- `MiniFASNetV2`：`2.7_80x80_MiniFASNetV2.pth`，SHA-256 `a5eb02e1843f19b5386b953cc4c9f011c3f985d0ee2bb9819eea9a142099bec0`。
- `MiniFASNetV1SE`：`4_0_0_80x80_MiniFASNetV1SE.pth`，SHA-256 `84ee1d37d96894d5e82de5a57df044ef80a58be2b218b5ed7cdfd875ec2f5990`。
- 输入为80×80、完整8位BGR、FP32数值0～255；源PyTorch/ONNX是NCHW，编译后软件入口是NHWC。
- 按原图整数`xywh`框扩边，尺度分别2.7和4.0；超边界时整体平移，右/下端点包含在裁图内，再缩放到80×80。
  两尺度在部分示例中受画面尺寸限制，得到相同裁图，不能因此删掉一个模型。
- 各模型输出三个logits；各自softmax后取平均，类别1是模型的活体类别。不是先平均logits再softmax。
  另外两类不擅自命名为特定攻击类型。融合分数未用本摄像头校准，不能解释成安全放行概率。

处理了两个输入陷阱：上游`ToTensor`注释写0～1，实际`functional.to_tensor`不除255，
本实现按实际0～255代码逐元素核对；上游样本JPEG含EXIF方向，默认解码与现役后端忽略EXIF可能得到不同坐标系。
板端入口明确使用忽略EXIF后的原图坐标。示例测试将官方解码像素无损存PNG后再运行，未把另一方向的框直接套入。
SDI原始帧没有JPEG方向元数据，但框仍必须属于同一原帧。

## 学校服务器构建

学校任务：`D:/yzd/tmp/wcis-face-pad-20261018`；本机证据：`D:/yzd/tmp/minifas-pad-20261018`。
所有模型导出、改写、FP16编译和AArch64交叉编译均在学校服务器完成。共享工具只读复用，未修改或停止其他任务。
构建前核实连接、进程、工具；配置任务专用TMP/TEMP/TMPDIR、缓存，交叉编译显式设置PATH、CROSSWIN_TC、
`MSYS2_ARG_CONV_EXCL='*'`。共享Python没有pip，OpenCV/Pillow通过PyPI元数据取得对应wheel，校验SHA后解包到任务`python/`。

实查：Python 3.12.15、PyTorch 2.14.1+cpu、ONNX 1.23.2、ORT 1.31.0、OpenCV 4.10.0。
生成模型自报iCraft v3.39.0，目标zhuge、FP16、MPE 4行2列；板端SDK确认相同几何。
原始V2通过前四阶段，在generate崩溃，退出码`3221226505`。使用已有等价PReLU表达式绕过：

```text
relu(x) + depthwise_center_alpha(x - relu(x))
```

每模型改写33个PReLU，3×3深度卷积只有中心为原斜率；没有重训、更换权重或删除SE、双模型融合。
改写后两模型均通过parse/optimize/quantize/adapt/generate，保留失败及成功日志。
此改写绕过了故障，不能仅凭退出码断定厂商内部崩溃根因。

复跑文件：

- `scripts/face_pad_reference.json`和`fetch_face_pad_school.py`：固定提交、逐文件SHA下载。
- `scripts/prepare_face_pad_school.py`：官方裁图/ToTensor/模型CPU参考及ONNX对照。
- `scripts/rewrite_face_pad_school.py`：等价改写和ORT对照。
- `scripts/compile_face_pad_school.py --variant conv-slope`：五阶段FP16构建，`--icraft-bin`可指定重新核实的工具目录。
- `scripts/build_face_pad_school.ps1 -TaskRoot D:/yzd/tmp/wcis-face-pad-...`：交叉构建`wcis_face_pad`。

Python构建脚本需先上传至学校独立任务根目录，`model_backend/face_pad.py`作为`face_pad.py`放在同目录，
依赖放任务`python/`，源码包位于`cross-source/npu_photo`。脚本拒绝在本机项目路径直接构建模型。

## PL裁图实现

`rtl/wcis_pad_preprocess.v`复用`wcis_affine_sampler.v`和`wcis_pixel_read_axi.v`。
输入完整BGRX原帧及ROI，输出80×80像素流；base/pitch、ROI和frame_id在命令握手时锁存。
拒绝空区域、越界、宽高超8192、存储不按8字节对齐、pitch不足及32位地址范围溢出。
只用完整8位BGRX，不经过RGB565压缩后声称等价。

关键是先在裁图局部坐标夹边，再加原图偏移：直接偏移原仿射坐标只能整帧夹边，小ROI上采样会读到ROI外像素。
base/pitch仍指原始对齐帧，奇数x裁图无需改为错误的偶数边界。半像素逆映射采用Q16.16，固定输出80。
保持valid/ready背压、SOF/EOL/EOF、错误和frame_id；复位必须与AXI互连共享，不能取消在途事务。
若中途读错，即使已有部分输出，也必须在done/error后丢弃整份张量。

当前为独立AXI读端原型，未接CustomOp寄存器、native DDR仲裁、输出写回及原帧租约。
未综合此新模块、未做整板布局布线、未生成bit/BOOT、未重启或更换现役固件。
之前的两行缓存优化源码保留，不能视为随本次NPU测试部署。

## 验证结果

| 检查 | 结果 | 范围 |
|---|---|---|
| 合法框与官方几何 | 200组一致 | 几何，不是防伪准确率 |
| 官方裁图及ToTensor | 3张样本逐元素一致 | 输入复现 |
| PyTorch→ONNX | 12组通过，logits最大差5.53e-6 | 双模型×3样本及黑/白/随机张量 |
| PReLU改写前后 | 12组ORT最大差0 | 有限输入等价对照 |
| 板端NPU | 12次通过，分别204/216项NPU绑定 | 实际设备执行；FP16最大logit差0.06166，预设上限0.15 |
| NPU融合与CPU参考 | 活体分数最大差0.002389 | 不是现场误放率 |
| PAD实际RTL仿真 | 20组通过 | 奇数ROI、小区域、画面边缘、同址换帧、读错/晚到错误、复位、随机背压 |
| RTL实际输出→学校ORT | 3张分类一致，活体分数最大差0.013575 | 仿真像素输入模型；新PL未上板 |
| 独立命令入口 | 3张样本通过，含帧号、原图SHA、框和双模型分数 | OpenCV参考裁图+实际NPU |
| 合同拒绝/融合单测 | 7项通过 | 非法框、缺模型、NaN/Inf、维度及softmax |

Q5插值与`cv2.resize`并非逐字节一致：6份真实示例输入最大通道差1～2，随机纹理最大差4～6，
这不是任意输入的误差上界。不同相机、临界分数仍需检验。
板测每模型约75.8～84.0ms包含会话、前向与输出文件等，不是纯核时间或门锁完整延迟。
独立CLI每次重新加载模型/打开设备，示例约1.70秒，尚未做常驻优化。

| 官方文件 | 板上模型分类 | 活体类别分数 |
|---|---|---:|
| image_F1 | 非活体 | 0.0710 |
| image_F2 | 非活体 | 0.1791 |
| image_T1 | 活体 | 0.9937 |

三张官方演示不是独立测试集，未据此计算现场准确率。
**随机噪声张量也被CPU/NPU模型判为活体高分**：PAD适用于有效人脸裁图，不能据任意图像高分认定存在真人。
调用方必须有同帧有效检测，并独立验证身份、质量和安全性。

## 板端入口及接入边界

候选：`/root/wcis-face/candidates/pad-20261018-7d22c90e30`。板端示例（输出目录须未存在）：

```sh
python3 /root/wcis-face/candidates/pad-20261018-7d22c90e30/src/scripts/run_face_pad.py \
  --bundle /root/wcis-face/candidates/pad-20261018-7d22c90e30 \
  --image /root/wcis-face/candidates/pad-20261018-7d22c90e30/samples/image_T1.png \
  --bbox 106 147 207 213 --frame-id 103 \
  --out /root/wcis-face/candidates/pad-20261018-7d22c90e30/manual-001
```

入口校验模型/执行文件SHA、已验证boot、硬件隔离标记，双模型调用持有现役release的`npu.lock`。
缺模型、输入无效或异常不产生默认活体成功结果；SDK失败留硬件复核标记，不自动重试。
入口同步等待，不强杀在途DMA；SDK输出等待有期限，完整设备卡死恢复尚未验证。
frame_id由调用者提供，SHA绑定实际解码字节，不能自行证明外部框来源，尚无会话抗重放协议。
PS后续应绑定检测/身份/PAD与同脸原帧、当前会话，超时/丢帧/错误/不可用时不得沿用上次通过结果。

前后健康均ready、硬件锁释放、boot一致，现役服务单元和全部人员库校验一致，未改正式服务路径。
后续先接PL输出写回/CustomOp及保留帧契约并完成新位流板证，再用真实SDI采集真人、打印照、静态屏显和视频回放，
分组统计误拒及攻击放行。阈值标定与最终测试采用不同采集数据；在此前只能称模型可用原型。

## 原始证据

学校任务包含`reference-manifest.json`、`reference-parity.json`、`rewrite-parity.json`、
`compile-original.json`、`compile-conv-slope.json`、`compiled-conv-slope/*/generate/`和`npu-build/`。
本机任务包含`school-results/`、`pl-verification/verification.json`、`board-parity.json`、
`cli-verification.json`、`summary.json`、`board-before.json`、`board-final.json`和`final-audit.json`。
源码入口：`model_backend/face_pad.py`、`face_pad_inference.py`、`npu_photo/src/pad_npu_runner.cpp`、
`rtl/wcis_pad_preprocess.v`、`sim/tb_pad_preprocess.sv`及上述脚本。

背景信息站`http://10.101.54.192:18080/`本轮连接被拒绝，发生于认证之前，未读取最新内容。
本记录同日归档至`D:/bigfuture/竞赛/记录/2026-10-18.md`，保留原有记录。
