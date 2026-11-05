# 同一硬件所有者内接入人脸与防伪（2026-10-26）

## 结果与范围

正式8091后端已切换至 `/root/wcis-face/apps/camera-pad-20261026`。真实摄像头请求在原人脸身份处理后，对同帧恰好一张脸执行MiniFASNetV2和MiniFASNetV1SE；复用同一进程、设备分配器和原帧租约，两个模型顺序运行，不启动旧的独立防伪设备进程。

防伪裁图仍在PS/OpenCV，双模型推理在NPU。PL身份预处理、VPU预览、模型权重、人员库及位流不变。本轮没有实现新PL防伪裁图，也未推进PL直接网口预览。

用户选择“暂不实拍，先完成后端接入”。本轮没有新的人工标注真人/攻击试验；历史实拍原帧仅作回放回归。接口返回的是未校准模型证据，不是门锁安全放行，未添加权限或开锁逻辑，也未改网页界面。

## 实现过程

- `ps_app/src/wcis_camera_owner.cpp` 增加可选PAD模型包加载，检查固定上游版本、MPE几何、80×80 NHWC FP32输入、三个输出及NPU算子。模型图驻留CPU内存，SDK会话顺序创建和释放，沿用已有完成后复位流程。
- `npu_photo/camera_owner_runtime.py` 验证模型路径/散列，监视文件版本，扩展两个80×80模型角色，在身份帧租约释放前调用PAD。输入仍取同一份RGB565原始帧，输出与设备所有者、boot、session、frame_id、租约令牌关联。
- `npu_photo/owner_pad.py` 复用固定上游裁图和双softmax融合。RGB565按位复制展开，不能称为原始完整8位图像。检测框按左上floor、右下ceil并裁边；身份记录必须对应同一检测脸。双模型后完整读回核对PL保留原帧。
- `serve_photos.py --camera-pad-bundle` 启用正式摄像头接口的同帧PAD；上传照片仍标记未评估，不将上传照片冒充现场活体。
- 默认3秒结果时效边界仅用于拒绝过期结果，不是校准后的安全阈值，也不强杀DMA。硬件超时/错误沿用原隔离机制，不以旧结果补成功。

接口 `/api/health` 的 `presentation_attack_detection` 为 `same_frame_model_evidence`，`pad_security_calibrated=false`。摄像头识别结果中的 `presentation_attack_detection.status` 为 `model_live`、`model_non_live`、`inconclusive`、`stale` 或 `not_applicable`；无脸/多脸通过reason区分。每份证据保留 `security_calibrated=false`、`authorization=not_evaluated`；身份匹配状态与PAD状态独立，`recognized`本身不是认证成功。

## 构建和验证

学校服务器重新检查连接、现有任务及工具，使用独立目录 `D:/yzd/tmp/wcis-camera-preview-pad-owner-7112f575` 交叉构建。共享SDK/工具链只读，任务设置临时/缓存目录、MSYS2工具链PATH和参数转换约定。没有本机或板端模型/C++编译，没有重导出模型。

二进制SHA256：`0b81bf6d4eee73d17000f08b283cb04de1b1ad1cc6253f517c21e9b2b87d74cb`。完整源码压缩包及主要C++/构建源散列保存在 `native-build-receipt.json`。

1. 14项CPU契约测试通过，覆盖同帧输入、输出对应、无脸/多脸、过期/未来时间、源数据变化、错误帧/会话/进程、无NPU执行、非有限输出、SDK异常、DDR核对失败、模型包及退出记录。测试运行在板端Python，使用假推理对象，不算NPU功能验证；本机Python缺少NumPy/OpenCV，没有为此改全局环境。
2. 候选实际NPU回放10月23日保存的18张RGB565原帧：15张有效单脸的检测、身份匹配及双模型logits与旧记录一致，最大logit差为0。真人6张为model_live，手机照片3张、视频6张为model_non_live；另3张多脸为not_applicable。回放源明确标记saved_fixture_replay，时间为回放起点，不冒充今天新拍。
3. 15张单脸回放的身份加PAD完整请求中位约694.68ms；这是有限旧样本的串行后端耗时，不是实时帧率、纯NPU核耗时或长期性能。
4. 候选6次真实摄像头请求均无人脸，跳过PAD且同帧核对通过。候选结束时433帧采集/编码一致，434次相机请求、末帧排空1次，SDK正常关闭。
5. 正式切换后6次HTTP摄像头识别检查均无人脸，返回同帧not_applicable/no_face；预览帧号在检查期间推进58帧。未将其换算为稳定帧率，未据此宣布新版本真人实时防伪通过。8091健康检查ready，人员库哈希未变。

## 遇到的问题及恢复

首次正常停止旧服务后，验证脚本读取旧stdout日志失败：日志达到4MiB容量上限，末行JSON截断，缺少完整终止收据。此时新版候选尚未启动。旧服务的systemd记录为正常退出，但不能由此补造排空计数。

依据正常退出及当时没有当前boot硬件故障标记，尝试恢复原服务；原版在启动采集/VPU时报告 `VPU output poll failed` 并留下硬件隔离标记。未清除标记、未强杀后继续使用SDK。核对任务后，以原BOOT执行一次正常系统重启，原服务恢复ready。VPU故障根因未定位，不能断言由日志截断导致。

新boot为 `0745327d-c2b5-45e9-a6f1-b4d0ecc78041`，旧故障记录仍保留且属于旧boot。BOOT仍为 `f6da96abbc0144ce5a48f4fa85aed6dab65067211b8932e8f4e4db87d5110297`，DTB/uEnv亦通过启动证明核对；未改启动分区。随后重跑候选板测及正式切换均成功。

为防止以后长时间运行再次丢失停机证据，Python传输层独立保存最终停止消息到 `<pid>-owner-stop.json`，不受诊断日志容量限制；新增测试及候选真实退出文件均验证该路径。退出记录改动只在新版后端，未回写原应用。

## 部署、回退与剩余边界

正式程序从旧应用文件清单复制到独立新目录，只覆盖本次后端文件、执行文件和构建收据，增加PAD契约模块。源应用保留。照片服务与8092查看服务更新应用/控制路径，原人员库和页面保留。

板端任务：`/root/wcis-face/candidates/pad-owner-20261026`。`formal-backup/` 保存原部署配置及两个服务单元；`rollback_board.py` 提供显式回退入口，要求当前应用匹配、没有当前boot故障、正常停止及独立退出收据通过。脚本已做语法检查，未为了测试回退再切换正式服务，不能写成回退演练已完成。

剩余事项：新版本人工标注的真人/手机/打印实拍、独立校准/测试集、误放/误拒评估、持续并行负载与长稳；新增PL防伪裁图接入与整板预算；完整系统时序/DDR容量签核。原服务重启时的VPU故障也需后续复现定位。本次仅完成ModelBackend同帧模型证据接入。

## 本地证据和归档

本机任务 `D:/yzd/tmp/face-pad-owner-20261026`：`originals/`、`native-source.tar.gz`、`school-preflight.txt`、`native-build.log`、`native-build-receipt.json`、`stage-manifest.json`、`contract-tests.log`、`fixtures.json`、`verification.json`、18份`replay-*.json`、`promotion.json`及退出收据。首次失败、恢复审查、原镜像重启均单独留档，未覆盖成成功记录。

回放依据：`docs/face-identity-pad-20261023.md`及其原始采样/eMMC保存数据。背景资料读取 `D:/xiangmuwendang/WCIS-FPAI/wiki/PL/plvid.md`，其旧SFace概述不能替代当前YuNet+MobileFaceNet实测契约。

本轮工作日期按客户端2026-10-26；历史采样日期仍为2026-10-23。本文同步合并至 `D:/bigfuture/竞赛/记录/2026-10-26.md`，保留同日已有内容。
