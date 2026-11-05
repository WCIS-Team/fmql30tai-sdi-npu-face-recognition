# PL编码实测、识别输入搬运优化与写回确认（2026-10-21）

识别输入优化已部署到正式8091服务，保持VPU预览。真实SDI的1080p短测中，PL JPEG约20.63fps，VPU约29.34fps，因此没有把正式960×540预览改成PL编码。新增PL写回确认逻辑通过仿真与独立综合，默认关闭，尚未生成或部署新位流。真实防照片采样见[同日采样记录](face-pad-camera-20261021.md)。

本轮仍为ModelBackend实现与验收，没有新增页面、权限调度或开锁动作。背景同时读取`D:/xiangmuwendang/WCIS-FPAI/wiki/PL/plvid.md`；intro的SFace表述与实际YuNet+MobileFaceNet不一致，采用已部署模型和源码契约。以下日期按本机聊天日期，板端时钟不用于工作日期归档。

## 真实摄像头PL JPEG与VPU对照

新增`ps_app/src/wcis_encoder_trial.cpp`，通过显式CMake选项`WCIS_BUILD_ENCODER_TRIAL`构建独立有限测试程序。复用现有厂商SDI、固定MMIO、iCraft原帧上传及既有JPG1核；相机线程仅使用预分配映射，SDK仍由唯一主线程持有。VPU包装器增加960×540和1920×1080几何及质量参数，旧调用默认保持960×540。

先正常停止并排空正式所有者，再以1920×1080 RGB565采集；6组配对使用同一原始帧，随后各进行约6秒持续编码。检查源帧读回、帧号、保护区、传输次数、JPEG完整解码与分辨率，完成后关闭SDK并恢复正式服务。该试验未同时运行NPU。

| 指标 | PL JPEG | VPU JPEG |
| --- | --- | --- |
| 持续编码窗口 | 124帧/6.010秒，20.63fps | 177帧/6.032秒，29.34fps |
| 配对端到端中位耗时 | 46.14ms | 26.49ms |
| 分段中位耗时 | 原帧上传3.93ms，编码及轮询41.75ms，读回0.18ms | RGB565转NV12等准备16.79ms |
| JPEG字节数中位 | 139206 | 101866 |
| 原始帧对解码图PSNR中位 | 36.75dB | 27.96dB |

两端均设置质量75，但PL为4:2:2、VPU输入NV12为4:2:0，量化参数也不等同；这些数值不能当作等画质压缩效率结论。持续窗口不是硬件极限或长稳保证。现有PL核固定1920×1080，不能直接给它960×540缓冲；没有用补零或放大后的画面冒充同尺寸比较。

总计采集/编码408帧，409次相机请求，末帧排空一次，SDK正常关闭。保留VPU正式预览的依据是这次实际链路结果；进一步换PL需先实现匹配预览尺寸的编码配置并单独验收，不能从“PL有JPEG核”推导它一定更快。

## 减少识别输入的中间搬运

旧路径是PL结果读回为BGRX文件，Python读取并转换为FP32临时文件，再由原生程序读取并构造HostTensor。新路径在同一个原生所有者里，把已完整验证的PL结果直接转换成模型HostTensor并立即执行NPU：

```text
相机原始帧 → 保留的同帧PL DDR → FAC1缩放/五点对齐
  → 完整可读校验 → 原生内存构造FP32 HostTensor → NPU
  → 输出及同帧收据 → Python后处理
```

这仍包含PL结果读回到PS和SDK上传模型输入，不是PL到NPU零拷贝。YuNet保持640×640、NHWC BGR、FP32原始0～255；MobileFaceNet保持112×112、RGB及`(v-127.5)/127.5`。模型、权重、登记库、匹配阈值和五点规则未更改。

新增`ps_app/src/wcis_prepared_input.hpp`及`npu_photo/native_forward.py`。原生完成收据绑定唯一所有者、角色、帧号、帧租约令牌和一次性前向令牌；跨所有者、跨角色、跨帧或重复消费会拒绝。保留旧文件路径用于对照。正式开关为`serve_photos.py --camera-native-inputs`。

640检测输入不再生成大型BGRX/FP32临时文件；112对齐像素仍可供原有可视化和图像验收使用。NPU输出仍读取并验证，未删掉源帧和输出检查。融合前向的耗时计入预处理请求，结果中的`fused_forward_in_prepare`与`fused_in_preprocessing_rpc`明确这一归属，不能把很短的Python `forward`调用单独当作模型耗时。

### 构建与对照

每次学校构建前重新检查连接、工具和运行进程；源码、构建、日志、环境缓存均位于独立任务。未在板端编译模型或C++。

- 编码试验学校任务：`D:/yzd/tmp/wcis-camera-preview-pl-encoder-7a3da627`；二进制SHA256 `aafb5ad784865a142c39c2d9f8cd58bf26fd6bc79c302936815659ed89a21ba1`。
- 最终识别程序学校任务：`D:/yzd/tmp/wcis-camera-preview-native-input-e9dc8442`；二进制SHA256 `7d7072abd4825bbbefd006d4dbbccb518929c05973d8b2a43830b985d4c5eab8`。
- 单人、双人、无人脸图片的实际原生FP32输入与原NumPy输入逐字节相同；额外覆盖每个通道0～255所有字节取值，不等于穷举所有图像。
- 同一所有者内交替旧/新路径，共18组配对，检测输出、特征输出哈希、检测框、身份及相似度均一致。生产模式无`input.f32`或验证用FP32文件残留。

| 固定照片6组配对中位 | 旧路径 | 原生输入路径 | 缩短 |
| --- | --- | --- | --- |
| 单人 | 705.81ms | 622.97ms | 11.74% |
| 双人 | 828.17ms | 734.05ms | 11.37% |
| 无人脸 | 385.32ms | 296.77ms | 22.98% |

另20次真实摄像头请求均通过PL保留源帧全量一致检查；停止时955帧采集/编码相等，956次请求，末帧排空一次，SDK正常关闭。

8093隔离人员库验收通过同帧JPEG哈希、推理期间视频推进、0/1/2人照片、登记/识别/删除、坏图400、多脸登记422及第5路视频503。候选空闲29.75fps、混合测试28.60fps。随后正常排空候选并切换正式服务。

正式8091复测10次单脸摄像头请求全部成功，中位HTTP459.61ms；空闲29.78fps，混合识别29.06fps，最长帧间隔70.49ms。帧率在板端HTTP接收处计数，不是电脑浏览器经网络收到的帧率；本机直连超时，实际管理经已核验校园跳板连接。预览帧率不是识别完成率；不同场景不能直接比较为提速比例。

## PL写回确认候选

此前板测发现DONE已返回但CPU首次读回仍有未写像素，故保留当前正式软件的A5初始化回读、DONE/错误/帧号/像素数检查、输出完整可见轮询及故障隔离。

新增`rtl/wcis_native_write_commit.v`，在没有原生DDR B响应的接口上，为FAC1/JPG1写请求增加同地址、按有效字节掩码的读回匹配，匹配后才向客户端确认；失败不确认、不继续覆盖在途请求。普通读响应保留所属客户，AR/AW受背压时保持稳定；超时后仍保持已发出的AR并排空晚到响应。原厂adder保持原先接受契约，不附加验证延迟。

这是一种数据可见性收据，不是DDR控制器写响应，也不能仅凭相同旧字节证明所有在途写均已排空；FAC1现有软件新一轮A5边界及保护检查仍不可删除。每个64字节写增加读回会消耗带宽，吞吐代价尚未上板测量，因此`VERIFY_NATIVE_WRITES`默认0，没有直接换正式固件。

- 单元覆盖延迟可见、掩码、普通读仲裁、AW/AR背压、无法写入、超时后晚到响应、共享复位及adder旁路。
- 延迟DDR模型重现旧实现的早DONE/像素未写问题；启用后5组FAC1用例通过，包括旋转、边界、RGB565奇数pitch、同址换帧和真实112×112人脸。
- 实际FAC1与JPG1并行，2种像素格式各2帧，保护区及JPEG黄金系数差≤1；公平仲裁三模式回归通过。
- 默认关闭验证桥的原厂adder/FAC1回归中，5组通过；额外`detector_1080p`大帧仿真达到300秒墙钟上限而未完成，不能记作通过或功能断言失败。板端现役大帧路径的本轮软件验收已通过，但不能替代新RTL的大帧回归。
- Vivado2018.3独立综合：392 LUT、744寄存器、0 BRAM、0 DSP。100MHz约束下综合估计WNS6.375ns；未约束板级I/O且没有布局布线，不能当作整板时序收敛。
- 这轮未修改case、引脚、时钟、GT或工具时序库，未生成新的整板bit/BOOT，未重启或写启动分区。

## 正式部署与证据

应用：`/root/wcis-face/apps/camera-native-20261021`。控制文件：`/root/wcis-face/candidates/pl-preview-backend-20261021/native/owner-current.json`。正常停止当前所有者后，可从同目录`formal-backup`、`http-before-config.json`以及保存旧服务单元正文的`http-before.json`恢复切换前配置/服务单元，不能同时启动旧独立采集服务。

启动ID仍为`8f360a28-0740-4d81-a13f-379a20faf47e`，BOOT SHA256仍为`f6da96abbc0144ce5a48f4fa85aed6dab65067211b8932e8f4e4db87d5110297`，DTB/uEnv不变。正式PAD接口继续报告`not_evaluated`；独立采样结果没有自动变成开锁许可。

本地证据目录：`D:/yzd/tmp/pl-preview-backend-20261021`，含`encoder-build-receipt.json`、`verification.json`、`native-build-receipt.json`、`native-verification.json`、`http-verification.json`、`formal-promotion.json`、`formal-verification.json`、`commit-sim/summary.json`、`commit-ooc/`、`arbiter-regression/`与采样记录。验证脚本：`scripts/verify_native_write_commit.py`、`verify_jpeg_customop.py`、`verify_face_customop.py`、`verify_recording_arbiter.py`。
