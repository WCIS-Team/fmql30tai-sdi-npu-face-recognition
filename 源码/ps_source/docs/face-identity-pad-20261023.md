# 同人身份匹配与手机呈现攻击实拍（2026-10-23）

本轮在原镜像上完成同一测试者的真人、手机静态照片和手机视频回放三组实拍。使用独立临时登记参考，真人 6 张有效帧均匹配身份且被 PAD 判为活体；照片 3 张有效帧、视频 6 张有效帧均匹配同一参考，但被 PAD 判为非活体。照片组另有 3 张多脸帧，未做 PAD，不能计为攻击被拒绝。

这是模型后端的同帧功能验证，未完成门锁安全验收。**正式实时服务仍报告 `presentation_attack_detection: not_evaluated`，没有接入 PAD 拦截，也没有执行开门。** 本轮未修改生产模型、阈值、应用、正式人员库或位流，没有综合、布局布线、交叉编译或板端编译。

## 环境与参考

- 普通 SDI 摄像头，用户配置为 1080p30；实际保存的是现役路径输出的 960×540 RGB565LE。PNG 使用 R5/G6/B5 位复制扩展，不能恢复原始完整 8 位颜色。
- 使用原 BOOT，SHA256 `f6da96abbc0144ce5a48f4fa85aed6dab65067211b8932e8f4e4db87d5110297`。不是 500 MHz 候选验收，未测量实际 NPU 内核频率。
- 现役应用 `/root/wcis-face/apps/camera-native-20261021`，模型 release `/root/wcis-face/releases/20261014-b5a454c11d22`。
- 临时参考来自此前人工确认真人采样的实际所选帧 `D:/yzd/tmp/npu-500mhz-frontal-20261023/selected-0.jpg`，SHA256 `267262c7032e6272ee718e3db740715089ba4c86cafb989e65d7851a9ad8db11`。新采样帧没有作为参考复用。
- 参考经既有 PL 预处理与 NPU 检测/特征链提取 512 维向量，任务私有名称 `acceptance_subject_001`，pipeline `yunet-mf-fp16-npu:a49114c2174ff0b132e4116fcb94978ef53566e4ef7edae583a186d09ef0a88e`。身份余弦阈值沿用 `0.3283871143367488`。
- 临时库仅在独立任务目录内，未走生产登记接口、未修改正式人员库。因此本轮验证的是“私有参考与新帧匹配”，不能写成“生产人员登记接口验收”。

补充资料读取 `D:/xiangmuwendang/WCIS-FPAI/wiki/man/NPU调用链.md`。该文描述厂商 YOLO 路径，不能将其中直接入 NPU 张量的零拷贝描述套用到本轮人脸链路；本轮路径以现役应用及采样证据为准。

## 采集、同帧绑定与 SDK 隔离

复用既有 `npu_photo/capture_pad_samples.py` 的采样、启动证明、应用哈希、正常停机和恢复约束，在任务目录添加 `capture_identity_pad.py`。识别调用保留 `return_embedding=True`，只将私有库传给现役匹配逻辑。没有修改生产服务或引入前端/编排层。

每组分别收到用户就位确认后才启动，记录人工标签、带时区的确认时间和独立采集组 ID。每组 6 帧；真人、照片、视频分别采集，不把先前的“可以配合”当作当前画面标签。

1. 重读当前 control PID、boot ID 和启动证明，核验现役应用文件及 PAD 包。正常停止正式所有者，要求最终日志 `sdk_closed=true`、`camera_pending=false`、`camera_drained=1`、`captured==encoded`、`camera_requests==captured+1`。
2. 启动唯一私有 CameraOwner，所有命令输出在其 `/dev/shm/wcis-owner-*/request-*/job` 内。每帧检查 PL 保留源区与相机原始 RGB565 全量相同，保存源数据、PNG、SHA256、帧号、会话、boot ID、检测框、身份结果及特征。
3. 只对恰好一张脸的帧做 PAD。浮点 xyxy 框按左上 floor、右下 ceil 并裁边，显式转为整数 xywh；多脸帧不选猜测目标。
4. 结束采集并确认私有所有者正常排空/关闭 SDK，之后才运行独立 PAD NPU 程序。两个 SDK 所有者不并发。PAD 验证返回源 SHA 与保存 PNG 相同。
5. PAD 完成后恢复正式服务；硬件错误不默认返回活体，也不自动强杀后反复重试。三组均正常完成并恢复。

复用冻结包 `/root/wcis-face/candidates/pad-20261018-7d22c90e30`，每次核验受清单覆盖的 5 个文件。上游提交 `b6d5f04ad78778917853b25c778acef6d5626d15`；MiniFASNetV2 与 V1SE 使用 2.7/4.0 上下文，80×80 BGR FP32、0～255，分别 softmax 后平均，类别 1 为 live。输出采用三分类 argmax，没有根据本轮结果改阈值。分数没有校准，不能当作安全放行概率。

**PAD 裁图仍由 PS/OpenCV 参考实现完成，双模型推理在 NPU；新 `wcis_pad_preprocess.v` 未在本轮接入或部署。** 现役身份识别仍使用已有 PL 预处理。不能把此轮写成“新 PL 防伪预处理已上板”。

## 结果

| 人工标签 | 采集帧 | 有效单脸帧 | 匹配临时参考 | PAD 判活体 | 身份相似度范围 | 活体类别融合分数范围 |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| 真人 | 6 | 6 | 6 | 6 | 0.764210～0.786955 | 0.999571～0.999988 |
| 同人手机静态照片 | 6 | 3 | 3 | 0 | 0.676006～0.745262 | 0.000824～0.083421 |
| 同人手机视频回放 | 6 | 6 | 6 | 0 | 0.493009～0.746362 | 0.000000721～0.001278 |
| 打印照片 | 未测 | — | — | — | — | — |

照片组前 3 帧各检测两张脸，其中次框在画面顶部边缘，未人工断定其成因；该 3 帧没有 PAD 结果。其余 3 帧及全部视频帧，身份匹配与 PAD 使用的是同一张原始帧，不是异步预览截图。这支持本轮条件下“身份相同但呈现方式不同”时模型给出不同判断，不能外推到所有屏幕和攻击方式。

本地另取回 15 张有效帧的 PAD 原始 logits、运行日志和 result.json，检查 boot/帧号、源 SHA、框与身份记录一致。每张有两个 `npu_bound_ops>0` 的 forwarded 结果，重新计算双模型 softmax 融合及 512 维参考余弦；最大差分别约 `1.11e-16` 和 `7.77e-16`。这只核验记录绑定和计算，不新增硬件测试或准确率证据。三个代表 PNG 均与采样 SHA 一致。

人工查看保存的手机照片/视频代表帧可见屏幕边缘；照片中的脸偏模糊。模糊、边缘、反光、拍摄背景和距离可能提供区分线索，不能认为模型只依赖人体生理信息。静态照片/视频的身份一致性来自用户的场景确认及特征匹配，不作人工外貌身份断言。

## 初次参考调用故障与处理

初次私有参考脚本误将输出指定到所有者工作区之外，原生路径检查在 `command_begin` 返回 `Command path outside owner workspace`，进程异常退出；当时相机 DMA 已启动，缺少正常排空证据。这是本次诊断脚本的路径错误，不是模型算子缺失，也没有在板上编译模型。

保留旧 boot `d830757c-9da4-40a9-a86f-1fad9651c859` 的故障标记与原始日志，没有删除标记或绕过保护。SSH 仍可用；采用一次正常系统重启恢复硬件状态，未更换或改写 BOOT。随后改为先在所有者工作区内完成推理，再复制结果到任务证据目录。参考重试及三组采样正常结束。

恢复后的 boot 为 `00e85ed6-f66b-4176-ae7a-79d786c552a8`，三组及最终核对均属此启动。历史故障标记仍保留，最终核对确认它不属于当前 boot。

## 恢复核对与结论边界

`final-audit.json` 确认：SD 启动分区只读核验的 30 个文件与先前原镜像清单一致，BOOT/DTB/uEnv 与当前启动证明一致；23 个现役应用文件符合清单，正式人员库 6 个文件及识别服务单元未变。8091 识别和 8092 视频状态 ready，boot ID 相同；仅一个正式 `wcis_camera_owner`，没有遗留采样进程或请求目录，无当前 boot 硬件隔离故障。只读核验后已卸载 SD 启动分区。

三组都是单人、单现场的短片段，相邻帧相关，不能按 6 次独立攻击尝试统计；未量化普通场景下的误放/误拒率。未测试打印、弯折照片、换屏幕、屏幕亮度、严格尺寸匹配、清晰聚焦且遮住边框、独立人员/场次或长期稳定性。后续校准集与最终测试集应分开。本轮保持 `security_calibrated=false`。

本轮完成的是独立后端原型验证。后续需要在这些边界下验收新 PL 裁图与参考一致性、在单所有者内接入同帧 PAD，并由 PS 侧明确多脸/不确定/超时的拒绝规则；这些尚未因本轮通过而自动完成。

## 证据位置

本机任务目录 `D:/yzd/tmp/face-identity-pad-20261023`：

- `board-before-initial.json`、`board-before.json`、`registration-source.json`、`reference-result.json`、私有 `temporary-gallery.json`。
- 三组 `request-*.json`、`capture-*.json/.log`、`group-summary.json`。
- `pad-evidence/` 下逐帧 result 与 SDK 日志、`selected/` 下代表 PNG/采样元数据、`evidence-verification.json`。
- `reference-console.log`、`reference-rejection-review.json`、`reset-after-path-rejection.json`、`reference-console-r2.log`、`final-audit.json`。
- 私有采样、参考、核对和证据验证脚本；正式源码不变。

板上原始 RGB565/PNG 和逐帧 PAD 输入/输出保留在 eMMC：

- `/mnt/wcis-emmc/wcis-face/acceptance/identity-pad-20261023-bona_fide-192032`，组 `1917292f727647cc91ace4adbcea4882`。
- `/mnt/wcis-emmc/wcis-face/acceptance/identity-pad-20261023-phone_still-192152`，组 `631a66e8f0714f79bcefdbb88e65efe7`。
- `/mnt/wcis-emmc/wcis-face/acceptance/identity-pad-20261023-phone_replay-192454`，组 `2cd7eec094a940a1bdd5691ccde959f9`。

日期依据为带 `+08:00` 时区的人工采样确认记录，均为 2026-10-23。报告同步归档到 `D:/bigfuture/竞赛/记录/2026-10-23.md`，保留同日已有记录。
