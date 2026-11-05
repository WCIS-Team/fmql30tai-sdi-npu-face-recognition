# 摄像头与照片识别互斥接入（2026-10-20）

后续界面已增加同页真实画面与检测叠加，当前入口与验收见 [同页摄像头画面与检测叠加](face-live-overlay-20261020.md)。本文“未增加前端”等表述是本阶段完成时的历史范围。


## 当前结果与使用

已恢复 `http://192.168.1.113:8091/` 的原有照片登记和识别页面，真实摄像头预览保持在 `http://192.168.1.113:8092/`。先填写姓名、登记一张清晰且恰好包含一张脸的照片，再用同一人的另一张照片测试识别。原有输入限制为8MiB、1600万像素、PL边长不超过8192且有界分配不超过64MiB；不符合时明确拒绝，不回退CPU。

增加后端 `POST /api/recognize-camera`，空请求体，取当前真实摄像头的一张新鲜画面识别；未增加网页按钮、前端或开锁/权限编排。照片仍走原登记和识别接口。所有结果标记 `presentation_attack_detection.status=not_evaluated`：**身份匹配并不代表真人通过，本轮没有接入PAD推理或验收防照片攻击。**

## 依据与范围

本轮先读取本地AGENTS、`D:/xiangmuwendang/WCIS-FPAI/wiki/PL/plvid.md`、现有照片/视频/PAD记录及源码。背景介绍中曾出现SFace，当前实际部署为YuNet + MobileFaceNet，以当前模型清单与服务为准。开始时仍为上一轮修正版BOOT和启动 `b174ec4a-a93d-4833-81ca-962ecdf4ba9a`；原系统采集服务已经停止，但同目录采集程序由独立会话持续运行，因此不能把服务inactive误当成摄像头停机。原照片服务inactive/disabled。

只修改ModelBackend的硬件准入与采集退出行为，复用原页面、登记库、模型和PL预处理。无RTL修改、综合、布局布线、位流生成或BOOT替换；不修改学校共享SDK、外部案例或长期记忆。

## 实现过程

1. `ps_app/src/wcis_sdi_vpu_live.cpp`：停止信号只停止接收新帧，已发出的DMA继续等待完成，VPU输出在EINTR后继续排空。真实超时/错误仍退出隔离，不当成正常完成。
2. 学校服务器在线核验SDK/MSYS2及编译任务后，在独立 `D:/yzd/tmp/wcis-camera-preview-drain-51d2b164` 交叉编译，CPU单目标构建，不在板上编译。C++源码SHA256=`c6a1fdd88d97983ab9e30a07043b086c12aa3ba883b0630f6ee8ce2524fa4530`；新采集程序SHA256=`937d71165665c7b285a1481050a9376bea24b086cd254404bd7169203bab1b2b`。任务TMP/TEMP/TMPDIR、缓存和源码独立，共享工具只读。
3. `npu_photo/camera_interlock.py`：同一release的准入文件锁跨进程串行请求；核验本次启动BOOT证明与隔离标记。识别前停止受控采集，要求本次会话退出码0，确认原有`npu.lock`已释放，才允许PL/NPU工作；结束时再次检查隔离标记，然后恢复采集。SDK失败或停止结果不明时不自动重试。
4. `scripts/run_sdi_vpu_capture.py`：以同一个`npu.lock`覆盖SDK完整生命周期。照片模型为CPU驻留、每次硬件调用结束关闭设备，因此服务active不等于SDK被占用；取消单凭照片服务active拒绝启动摄像头的旧判断。
5. 摄像头单帧接口验证来源camera、boot、原生PID、会话目录、正帧号、960×540几何和1.5秒内的单调时钟年龄。复制JPEG后才暂停采集，识别结果绑定同一JPEG SHA、帧号和会话。停止后的tmpfs帧目录只按固定文件名清理，拒绝越出所属会话目录，不使用递归删除。
6. `serve_photos.py` 的登记、照片识别和摄像头识别共用现有PL+NPU管线；新增硬件准入健康字段。检测到隔离标记时健康接口不可用，不返回默认安全通过。
7. 新服务 `wcis-sdi-camera-live.service` 使用 `KillMode=mixed`、`SendSIGKILL=no`，停止超时不强杀DMA所有者。照片服务同样禁止强杀；原有请求忙时拒绝策略保留，不排队处理过时画面。

## 部署与恢复

应用：`/root/wcis-face/apps/camera-ready-20261020`。采集和本轮证据：`/root/wcis-face/candidates/face-camera-ready-20261020`。从旧应用复制完整目录，只替换服务入口并添加互斥模块，复用原C++人脸程序与原模型。

备份原照片、查看器、旧采集服务单元、输入配置和正式人员库校验值，安装候选后正常重启一次，消除旧独立采集会话与SDK状态。当前启动为 `6d292f53-4a5d-4600-bbcd-28ea2654a6c0`，只读核验BOOT=`f6da96abbc0144ce5a48f4fa85aed6dab65067211b8932e8f4e4db87d5110297`、DTB和uEnv均未变。

试验恢复计时器最初240秒，在独立登记测试继续执行前延至420秒；全部检查通过后已停止并禁用。新采集、照片、查看器均active并启用开机启动；旧 `wcis-sdi-refclk-fix-20261020.service` 停止且禁用。

收尾复核仍是同一启动：照片health=ready、硬件准入可用，连续采集/编码均到1349帧，最新帧年龄0.035秒，tmpfs仅剩1个活动摄像头会话目录。全部应用文件哈希与当前输入配置一致，正式人员库不变，恢复计时器inactive/disabled；证据为 `final_state-output.txt`。

软件回退入口：`systemctl start wcis-face-camera-ready-recover.service`，会停止当前照片与采集，恢复原软件配置并重启至原预览方式，BOOT不变。旧的位流回退不是本轮软件回退入口。恢复依赖Linux可运行，不是硬件双镜像容灾。

## 验证

| 检查 | 结果与边界 |
|---|---|
| 无硬件测试 | 8项通过：新鲜帧、过期/异源帧、元数据截断、完成后恢复、坏图恢复、SDK故障隔离、缺退出证明阻止推理、拒绝清理非所属目录 |
| 原页面 | 本机直接HTTP 200，沿用登记/上传按钮，未改HTML |
| 单人照片 | 1张脸，完整FAC1预处理与NPU推理；未登记的独立照片返回unknown，未改阈值强行匹配 |
| 无脸/双人 | 分别0/2张脸，多人结果仍关联各自检测框 |
| 当前摄像头 | 实际桌面画面返回no_face，JPEG SHA与识别输入SHA一致；不是有人脸的现场身份验收 |
| 损坏图片 | HTTP 400，随后直播恢复，没有写硬件隔离标记 |
| 交替使用 | 5种请求后均恢复同一启动的camera新会话，复查最新软件再次全部通过；不是SDK同时访问或不间断录像 |
| 已登记样本 | 自匹配recognized，相似度0.998576；这不是独立测试照准确率 |
| 隔离登记库 | 复制到独立eMMC验收目录，通过实际HTTP登记、识别、删除；同图相似度1.0只是接口通路验证 |
| 正式库 | 6个文件校验值与部署前逐项一致，未新增验收人员 |

最终一轮5种请求，从请求到预览恢复约1.95～3.05秒，包含停止采集、模型工作、SDK重新打开和等待新帧，不能称为纯推理耗时或稳定帧率。识别期间预览会短暂停止，旧画面不会冒充新帧。

首轮独立登记脚本误用127.0.0.1访问仅绑定192.168.1.113的正式接口，在调用模型前连接被拒；修正访问地址后通过，不能将其记成人脸模型失败。记录保留于 `enroll_error-output.txt`。

## 未验收与后续

- 你们真人面对摄像头、另一张照片的泛化识别、不同光照/距离/姿态仍待实际样本测试，不能从自匹配分数外推。
- 当前摄像头输入为SDI采集后的RGB565抽样、VPU JPEG，再PS解码和上传PL；不是1080p原帧零复制，也不是连续视频NPU实时识别。输出预览960×540、上限5fps，经PS网口。
- 防伪双模型已有独立原型，新PAD PL裁图尚未接入位流；本轮API明确不评估活体。照片、屏显、视频回放攻击仍可能被身份模型匹配，当前入口不作开锁依据。
- 原NPU脉宽及厂商代理器件告警未消除，本轮没有新的生产时序签核或长期稳定性结论。

## 证据来源

- `npu_photo/camera_interlock.py`、`npu_photo/serve_photos.py`、`scripts/run_sdi_vpu_capture.py`、`ps_app/src/wcis_sdi_vpu_live.cpp`、`tests/test_camera_interlock.py`
- `D:/yzd/tmp/face-camera-ready-20261020/build-receipt.json`、`build.log`、`school-preflight.txt`
- 同目录 `http-verification.json`、5份 `*-response.json`、`enroll-verification.json`、`accepted.json`、`before.json`、`deployment.json`、`final_state-output.txt`
- `docs/sdi-refclk-fix-20261020.md`、`docs/face-pad-minifas-20261018.md`

记录同日同步到 `D:/bigfuture/竞赛/记录/2026-10-20.md`，保留当天已有内容。
