# 大帧回归、算子耗时与PL/NPU重叠试验（2026-10-22）

本轮补齐了上次未完成的409600像素大帧回归，完成NPU算子及PL分段计时，并在现役位流上验证了NPU处理帧A、FAC1预处理帧B的有界重叠。12组串行/重叠配对全部通过，但组合窗口只缩短约4.42%～5.10%，没有据此替换正式服务。没有新增模型、修改权重、放宽校验或生成/部署新位流。

背景同时读取`D:/xiangmuwendang/WCIS-FPAI/wiki/PL/plvid.md`，intro仍写SFace，模型列表与实际应用采用YuNet+MobileFaceNet；按现役模型、源码与本轮实测判断。日期按客户端2026-10-22；10月21日数据仅作为历史背景，以下表格为本轮新测。

## 大帧超时的处理与验证

上一轮Icarus的`detector_1080p`达到300秒电脑墙钟上限，尚无功能结论。本轮保留所有RTL和黄金像素，先优化测试内存模型：同一64位字按字节掩码合并写入，减少重复数组事件；增加进度计数和可选CSR轮询间隔。轮询间隔仅影响测试端查询DONE的频率，未改变PL算法、时钟比例、随机DDR停顿、输出比较或协议断言。

改用已安装的ModelSim SE-64 2020.4运行同一测试。全部工作库、日志和产物放私有任务目录；为未声明时间单位的原厂模块指定默认`1ns/1ps`，未修改case或工具安装目录。初次库路径调用方式和时间单位问题已在独立任务配置中修正，保留诊断日志。

| 大帧模式 | 像素数 | native读 | native写 | 测试结束仿真时间 |
| --- | --- | --- | --- | --- |
| 原生写接受模式，验证桥关闭 | 409600 | 43200 | 25600 | 43.198141ms |
| 写回确认桥开启，即时可见内存 | 409600 | 68800 | 25600 | 43.326031ms |
| 写回确认桥开启，接受后100个HP周期才可见 | 409600 | 278544 | 25600 | 53.250991ms |

三种均逐像素与黄金输出一致，检查原厂adder、非法描述符无DDR副作用、运行中描述符不可变、帧号/像素数、输出字节掩码、GP响应保持及native背压稳定。前两模式完整6组回归全部通过；延迟模式额外覆盖完整1080p源到640×640输出。ModelSim大帧实际运行约10～11秒；该电脑耗时不是硬件速度。

延迟模式第一版测试在等待原厂adder最后一笔写时遇到测试平台事件竞争：阻塞计数先达到16，而`write_pending`的非阻塞赋值尚未生效，过早检查最后一个结果。等待到下一HP下降沿后再检查posted队列排空，完整大帧通过。未通过修改adder完成契约或跳过结果比较绕过问题。

重跑原写回单元、旧早完成复现、5组FAC1及实际FAC1/JPG1两格式双帧回归均通过。Icarus大帧两任务在同一候选已由ModelSim完成验证后停止，记为冗余仿真取消，没有记为功能通过或RTL故障。

这也量化了桥的代价：即时可见时增加25600次64字节读，即1,638,400字节；人为延迟时多次重读会放大流量。这是特定仿真内存模型的事务数，未测得新桥的实际DDR带宽占用，不能外推整板吞吐。桥仍默认关闭，原有软件A5初始化、完整可见校验及故障隔离继续保留。

## NPU算子与分段计时

在`ps_app/src/wcis_owner_kernels.hpp`增加显式诊断开关，复用原厂`icraft_utils.hpp`的`timeProfileResults()`及`getForwards()`接口，记录每个节点的SDK total/memcpy/hard/other毫秒归因。将会话创建、后端配置、apply、forward调用、输出等待、导出和复位分开；FAC1另记录初始化验证、描述符、等待DONE、完整读回和输出文件写入。原有校验、优化开关和模型算法不变。

`CameraOwner(..., profile=False)`默认关闭，只有显式诊断请求启用；融合输入路径会将同一开关传入对应NPU前向。统计收集在输出ready后进行，没有另外打开SDK或启动SDK工作线程。

学校构建前重新检查连接、工具与进程，独立任务`D:/yzd/tmp/wcis-camera-preview-native-input-47ab6410`交叉编译成功，二进制SHA256为`50ab57d242f9c904d8ef5fbada7520c3d0a3106a74cab77717d3aaa706e61ba1`。未在板端编译，未修改共享SDK、停止其他任务或重建共享kit。

先取得正式服务的单人/双人/无人脸输出基线，再正常停止并排空正式所有者。候选在同一所有者内交替关闭/开启统计，6轮×3场景，共18组配对、72次模型前向；检测框、身份、相似度及全部NPU输出字节哈希与正式基线一致。另8次真实摄像头请求通过PL保留源帧全量一致检查，均为无人脸场景。候选正常关闭后恢复正式服务，模型及人员库未变。

### 未开启统计时的阶段中位数

| 阶段 | YuNet，18次 | MobileFaceNet，18次 |
| --- | --- | --- |
| 会话创建 | 16.59ms | 39.40ms |
| 会话apply | 7.37ms | 20.36ms |
| 会话建立合计（含守卫等） | 24.25ms | 59.08ms |
| forward及输出ready等待 | 27.88ms | 21.18ms |
| 输出导出及检查 | 10.60ms | 1.01ms |

640×640 FAC1：等待DONE中位93.14ms、输出初始化可见验证9.31ms、完成后完整读回及alpha验证3.02ms。112×112对齐：对应约6.19ms、0.26ms、0.10ms。这里的等待DONE包括运行和服务延迟，未用ILA拆成纯计算/DDR停顿，不称为纯PL核时间。

### 开启统计时的SDK归因中位数

| 模型 | SDK total | memcpy | hard | other |
| --- | --- | --- | --- | --- |
| YuNet | 29.11ms | 11.09ms | 11.27ms | 6.86ms |
| MobileFaceNet | 29.24ms | 0.40ms | 15.29ms | 13.56ms |

SDK分别报告112和211个HardOp，以及Input/Output边界节点；本轮没有发现图内PS计算回退或缺失算子。YuNet一项名称为Cast的HardOp包含明显搬运归因；不能把“Cast”名称解释成PS回退，也不能把全部hard归因等同纯卷积MAC时间。上述时间是SDK归因，既不是占用率，也不能再加到host阶段上当作额外延迟。

开启统计会增加逐算子同步、统计收集和JSON/日志开销；例如MobileFaceNet的forward/等待由约21.18ms变为29.84ms，收集统计约6.84ms。因此没有将统计常开，也不使用有统计的请求墙钟时间预测正式性能。

## 两帧PL/NPU真正重叠

新增`ps_app/src/wcis_npu_pl_trial.cpp`及默认关闭的构建选项`WCIS_BUILD_PL_NPU_TRIAL`，复用现有`parallel_npu_jpeg_runner.cpp`已验证的Session前/后回调模式，目标程序`wcis_npu_pl_trial`。

1. 正常停止正式所有者，用原已验收CameraOwner取得两个不同帧号、不同原始SHA的SDI帧；YuNet输入来自帧A实际FAC1输出，帧B作为下一帧PL源。两份原始RGB565保留作证据。
2. 无人值守场景未必有人脸，所以特征模型资源试验另使用公开`obama2.jpg`及正式检测框求得的有效对齐输入，明确不称作摄像头身份流程。
3. 采样所有者排空并关闭SDK后，有限试验取得NPU/相机锁；每条命令仅一个Device、一个分配器。先分配并初始化帧B及scratch，确认A/B逻辑身份不同、地址窗口、尺寸、guard和分配区不重叠，再建立NPU会话。
4. 串行模式在整张NPU网络ready后提交FAC1；重叠模式在第一个实际ZG330卷积的前回调中启动FAC1，确认新busy区间后继续卷积。
5. 后回调等待该卷积输出Tensor ready，再读取FAC1状态。仅前后均busy才记录`overlap_proven`，不以两个API调用接近冒充硬件重叠。
6. 两端都完成后完整读回输出、检查alpha、新一轮A5可见性、帧号、两端guard及整个帧B源，最后销毁临时对象并关闭Device。没有第二个SDK线程或独立分配器。

学校独立构建`D:/yzd/tmp/wcis-camera-preview-pl-npu-cbb351b7`，二进制SHA256 `74fc61ccde7b6ea283a27dcb3c12962da513688e65ead57feadc75c3173915fe`。仍使用原厂后端配置，没有开启融合、ETM或OCM试验选项。

6轮×2模型，共12组串行/重叠配对、24次组合命令全部通过：12次均取得真实卷积输出ready时PL仍busy的证据，NPU全部输出字节相同，PL全部输出字节跨模式/模型一致。PL640×360内容与实际量化坐标的独立OpenCV remap逐像素相同，补边及alpha全零；整个帧B源和guard逐次一致。

| 模型帧A＋FAC1帧B | 配对数 | 串行中位 | 重叠中位 | 每对缩短比例中位 |
| --- | --- | --- | --- | --- |
| YuNet | 6 | 126.81ms | 121.16ms | 4.42% |
| MobileFaceNet | 6 | 119.61ms | 113.54ms | 5.10% |

窗口从会话/输入准备完成后开始，包含NPU前向及等待、FAC1完成、输出完整可读检查、源帧验证和PL文件写出；不包含会话建立、输入上传、NPU输出导出或完整识别后处理。因此不是正式识别端到端缩短比例，也不是持续视频帧率。

同时观察到PL自身DONE等待中位由串行约87.8ms增至YuNet重叠95.5ms、MobileFaceNet重叠101.4ms。共享存储/互连资源争用是可能解释，本轮没有硬件带宽计数定位到具体端口，不能把相关性当作已定位的DDR故障。事实说明分开计算核并不等于消除资源争用，暂不为这约5%的局部窗口收益增加正式跨帧队列和双租约生命周期。

## 当前结论与部署边界

当前优先项是进一步减少PL预处理串行访存/控制等待，并审查会话重建是否能安全减少；不能根据当前帧率直接认定NPU计算阵列满载。会话复用需要重新验证设备状态、内存生命周期和两模型切换，不能简单把两个会话永久留在设备上。复制卷积算子、删除硬件锁或直接开启多SDK不属于本轮实现。

正式应用仍是`/root/wcis-face/apps/camera-native-20261021`，控制文件仍是`/root/wcis-face/candidates/pl-preview-backend-20261021/native/owner-current.json`。最终审计确认8091/8092就绪、一个原生所有者、无遗留请求、无当前故障标记，应用文件/配置和人员库哈希与任务开始一致；真实摄像头最终请求及同帧JPEG绑定通过。原独立采集服务仍disabled。

启动ID仍`8f360a28-0740-4d81-a13f-379a20faf47e`，BOOT SHA256仍`f6da96abbc0144ce5a48f4fa85aed6dab65067211b8932e8f4e4db87d5110297`。本轮未生成bit/BOOT、未更改引脚/时钟/工具时序库、未重启或写启动分区。PAD仍为独立初测，正式接口继续`not_evaluated`，未改开锁或权限逻辑。

## 复跑入口与证据

- 大帧及原厂回归：`scripts/verify_face_customop.py --recording --simulator modelsim --out D:/yzd/tmp/<新任务>/full --timeout 120`；加`--verified-writes`开启候选桥，加`--posted-write-cycles 100`注入可见延迟；`--poll-gap 256`仅为测试轮询间隔。未指定仿真器时仍默认Icarus。
- 原早完成复现与并行回归：`scripts/verify_native_write_commit.py --out D:/yzd/tmp/<新任务>/commit`。
- 诊断API：`CameraOwner(..., native_inputs=True, profile=True)`，仅在隔离候选使用，结束后关闭。
- 两帧有限程序：`wcis_npu_pl_trial --serve <models.json>`，调用方持有并传入两个锁FD；JSON包含mode、role、NPU输入文件/源帧身份及下一帧PL描述符，详见源码和已跑通驱动。
- 本机任务`D:/yzd/tmp/pl-npu-resource-20261022`：构建收据、`profile-result.json`、`profile-summary.json`、`overlap-result.json`、`overlap-summary.json`、`large-summary.json`、`full-accepted/`、`full-verified/`、`posted-large-fixed/`、`commit-regression/`、`final-state.json`。板端候选同名目录保存`profile_board.py`、`overlap_board.py`、原生程序、输入原始帧、前后状态及日志。复跑应换全新任务目录，并重新检查当前启动、配置、校验值及控制文件，不能复用旧PID。
