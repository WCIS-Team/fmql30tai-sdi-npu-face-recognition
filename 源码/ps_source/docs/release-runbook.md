# 540p 视觉服务发布与回退说明

2026-11-03 最新状态：已撤回CPU JPEG双编码方案；现役v2使用原VPU H.264、约30fps连续预览和原MP4录像。90秒并发窗约29.45fps，软件位置年龄p50/p95约562/601ms；光学延迟、30分钟矩阵、首次预热超时根因及候选整板重启未验收。详见[修复、实测与回退](h264-live-preview-20261103.md)。

2026-10-31 独立录像服务新增 H.264 闲时压缩，现役录像候选为 `/root/wcis-face/candidates/recording-idle-compression-20261031-r1`。实现、验证边界及录像单独回退见 [闲时压缩记录](recording-idle-compression-20261031.md)，对应冻结清单在 `release/recording-idle-20261031/recorder-manifest.json`；以下 540p-r2 清单仍是此前整套发布快照，不作为本次录像文件的当前散列。

适用范围：当前 960×540 单 owner 人脸/PAD、外部 VPU H.264 预览及独立 MP4/旧 JPEG 录像。2026-10-31 整理。本次仅整理、读取和离线验证；下面的停启命令是以后维护时的操作说明，本次没有执行。

## 从哪里开始

| 资料 | 位置与用途 |
|---|---|
| 本说明 | 当前发布/回退统一入口 |
| [文件对应表](release-source-map.md) | 全部 39 项主应用文件、首页来源、独立录像依赖、服务和启动前置关系 |
| [版本清单目录](../../logpack/05-release-receipts/540p-r2/) | 冻结的 app、recorder、services、startup、baseline 清单，source-map 与 owner 构建收据 |
| `outputs/release-baseline-20261031/` | 本次只读保存的 r2 应用、录像文件、启动文件、服务、配置和 r1 回退副本；不是安装目录 |
| [r2 上板验收](preview-maintenance-deploy-20261031.md) | 72 次固定输入回放、媒体验收、失败经过和未验收边界 |
| [维护任务](maintenance-plan.md) | 长稳、现场光照、人脸与重启等后续验收 |

旧资料一直存在，但用途不同：

- [2026-10-13 上板记录](board-deployment-20261013.md)、[2026-10-15 重新部署](face-redeploy-20261015.md)：对应当时的平台/照片方案；其中每请求独立进程等历史设计不适用于现役单 owner。
- [2026-10-30 H.264 部署](h264-ffmpeg-20261030.md)：r1 格式迁移、回退与整机重启证据；不能替代 r2 的重启验收。
- `scripts/deploy_face_photo_interface.py`、`deploy_camera_preview.py` 是早期部署入口，参数/页面/服务配置与现役版本不同；不要直接运行它们更新 r2。`verify_offline_release.py` 面向 BOOT/PL 离线包，不是当前应用校验器。
- 原始上板脚本与日志保留在 `D:/yzd/tmp/h264-ffmpeg-20261030`、`D:/yzd/tmp/preview-maintenance-deploy-20261030`，10-27 页面历史见文件对应表；不移动或覆盖这些证据。原脚本有固定日期、一次性目录及动作，不能整目录重跑。

## 当前版本与实际入口

以下为 2026-10-31 只读核实的基线。每次更新前重新读取现场配置，发现已变化时按新的现场版本重新准备，不能强行套用旧路径。

| 对象 | 实际入口 |
|---|---|
| 主清单 | `/root/wcis-face/video-stream-current.json`，读取 `app`、`files`、`verification` |
| 主应用 | `/root/wcis-face/apps/camera-h264-20261030-r2` |
| 页面 | 主服务 `ExecStart` 的 `--site`：上述应用的 `site/`；不是根目录 `index.html` |
| 照片/模型服务 | `wcis-face-photo.service`，8091，`serve_photos.py`；owner 校验由 `--camera-owner-sha256` 指定 |
| 浏览服务 | `wcis-sdi-vpu-view.service`，8092；共享 owner，不另启采集程序 |
| 录像服务 | `wcis-face-recording.service`，8093；实际目录 `/root/wcis-face/candidates/recording-h264-20261030-r1` |
| 模型发布 | `/root/wcis-face/releases/20261014-b5a454c11d22`；PAD 参数指向 `/root/wcis-face/candidates/pad-20261018-7d22c90e30` |
| owner 控制文件 | `/root/wcis-face/candidates/pad-owner-20261026/owner-current.json`；保留实际路径，不因发布目录变化而另起 owner |
| 人员库/录像 | `/mnt/wcis-emmc/wcis-face/galleries`、`/mnt/wcis-emmc/wcis-face/recordings` |
| 启动前置配置 | `/root/wcis-face/candidates/face-camera-ready-20261020/deployment.json` 的 app 必须与主清单一致 |
| 故障隔离 | `/root/wcis-face/hardware-review-required.json`；比较 boot_id，不删除标记解锁 |
| r2 回退材料 | 原 r1 应用；板端任务 `preview-maintenance-deploy-20261030/backup/`；本地保存为 `outputs/release-baseline-20261031/rollback/` |

照片服务启动前会运行 `boot_prepare.py`，检查 SD 上 BOOT/设备树/uEnv、配置网络并写启动证明。它不是只读诊断工具，不能为了检查而手动执行。存储服务 `wcis-face-storage.service` 的停止动作会卸载 eMMC；普通应用发布只停三个视觉服务，保留存储服务和音频任务。

## 只读校验与页面重组

在 Windows 项目根目录 `D:/renlianshibie` 执行。以下命令不会连接板卡、启停服务或操作硬件。清单冻结为 r2；未来新版本必须另存新目录和新清单，不能用新计算的散列覆盖旧期望值后再声称通过。

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python fpga_project/scripts/verify_app_release.py --root fpga_project/outputs/release-baseline-20261031/app --manifest fpga_project/release/540p-r2/app-manifest.json
python fpga_project/scripts/verify_app_release.py --root fpga_project/outputs/release-baseline-20261031/recorder --manifest fpga_project/release/540p-r2/recorder-manifest.json
python fpga_project/scripts/verify_app_release.py --root fpga_project/outputs/release-baseline-20261031/services --manifest fpga_project/release/540p-r2/services-manifest.json
python fpga_project/scripts/verify_app_release.py --root fpga_project/outputs/release-baseline-20261031/startup --manifest fpga_project/release/540p-r2/startup-manifest.json
python fpga_project/scripts/verify_app_release.py --root fpga_project/outputs/release-baseline-20261031/rollback/app --manifest fpga_project/outputs/release-baseline-20261031/rollback/config/config.json
python fpga_project/scripts/verify_app_release.py --root fpga_project/outputs/release-baseline-20261031 --manifest fpga_project/release/540p-r2/baseline-manifest.json
```

逐条确认退出码为 0 且 passed=true；任一失败就停止后续发布步骤。该工具只按外部指定清单检查文件，拒绝越界路径、重复项、符号链接及空清单；不检查目录内未列入清单的运行时文件，也不证明服务、模型、BOOT 或设备健康。可加 `--out 新文件路径` 保存 JSON，已有输出文件会拒绝覆盖。

重组首页时选择新的输出文件；保留旧文件，不直接写运行目录：

```powershell
python fpga_project/scripts/assemble_camera_site.py --template fpga_project/release/540p-r2/site-template.html --panel fpga_project/npu_photo/camera_panel.html --version 20261027-overlay-1 --out D:/yzd/tmp/release-runbook-20261031/site-rebuilt.html
Get-FileHash -Algorithm SHA256 D:/yzd/tmp/release-runbook-20261031/site-rebuilt.html
```

此基线应为 `6c04bfed7cf62923d11f26f9869097d0eb01b1f4a6ea0858a89bf85341cce178`。命令输出已存在时换新路径。后续修改源片段会改变结果，需另做页面回归、版本化与发布校验，不能继续使用旧预期散列。

## 准备一次应用更新

使用 [发布记录模板](release-checklist-template.md) 在新的任务目录记录，不覆盖历史记录。

1. **重新确认现场**：当前 boot、隔离标记、三个服务的完整单位文件/实际 ExecStart、主配置、启动前置配置、模型/PAD路径、owner PID/session、健康、源帧和媒体推进、录像模式、存储挂载及 UUID、其他任务。只读读取，不执行旧部署脚本。跨时段发现 PID 或数据变化要分段记录。
2. **准备候选和回退**：保存上述服务/配置原文及散列，核对旧应用完整性；备份候选将替换的文件。人员库和已有录像保留原位置并记录完整性，不清理、不重建分区。运行时 `service-stop.json` 单列，不能将正常停止回执更新当作录像损坏；录像媒体/索引/信息仍逐文件比较。
3. **明确改动范围**：列出旧/新路径与每个变更的 SHA256。仅改 Python/页面不冒称重新交叉编译；原生程序在学校独立目录构建，记录源码包、包内源文件、构建日志与二进制散列。模型与 BOOT 不随普通应用发布改动。本轮保留的旧 native 程序不能凭当前同名 cpp 宣称可复现。
4. **离线组装**：使用尚不存在的候选目录；从正式真实 `--site` 或已验证的模板组装页面。保留原模型、控制文件、人员库、录像和启动前置关系。分别核对主应用与独立录像目录。若不改录像，其服务和文件保持不动。
5. **发布前检查**：完成适合改动范围的软件回归、清单验证、脚本语法检查，准备本次完整回退和下述验收项目。临时脚本必须先核对当前参数，不能复制首轮失败报告中的 error 字段当作本次状态。

## 正常切换顺序

此部分用于已安排的维护执行。需要排他硬件访问，不与其他摄像头/NPU试验并行。以下是经过现有服务布局核对的顺序，不是本次已执行的动作。

1. 记录主服务当前 owner PID、session、boot，若录像正在录制，先结束录像并等待 idle、current=null、error=null，保留收尾结果。停止时不使用 kill -9。

   ```sh
   systemctl stop wcis-face-recording.service
   systemctl stop wcis-sdi-vpu-view.service
   systemctl stop wcis-face-photo.service
   ```

2. 从**刚才运行的应用目录**读取 `<停止前PID>-owner-stop.json`；必须对应本次 PID/boot，包含 sdk_closed=true、camera_pending=false、exit_code=0，并确认旧 owner/编码/封装进程退出。不能拿历史成功回执替代。如果没有安全关闭证据，或隔离标记属于当前 boot，停止重开设备；保留证据，再安排不影响其他任务的恢复窗口，不删除标记。
3. 在三个服务停止期间，写入候选的照片/浏览服务单位文件、主清单及启动前置 deployment.json，保持 app 一致；更新 owner 参数里的散列及所有受管文件散列。若录像有独立变更，同时更新它自己的目录与清单。每份 JSON 用同目录临时文件完整写入后 rename；不同配置文件不是跨文件原子事务，失败时恢复整组备份，不能带着半组配置启动。
4. `systemctl daemon-reload` 后，先启动照片服务；等待健康与媒体 ready，再启动浏览和录像服务。没有设置无界自动重启，也不改变已配置的 KillMode/SendSIGKILL/Restart 策略。

   ```sh
   systemctl start wcis-face-photo.service
   # 确认 /api/health 和 /api/camera/status 就绪后继续
   systemctl start wcis-sdi-vpu-view.service
   systemctl start wcis-face-recording.service
   ```

5. 使用本次任务内已核对的 `wait_visual_ready.py`，显式传入开始时记录的 boot_id，最多等待 45 秒。示意参数：`python3 wait_visual_ready.py --boot-id 本次启动号 --timeout 45`。它只 GET 8091/8093，不打开硬件；端口暂未监听会有界重试，要求同一 owner 的 encoded 和 frame_id 推进、960×540 H.264、模型/硬件准入 ready、录像输入 ready 且 off/idle。失败返回非零，不据一次 connection refused 判断硬件故障。8092 服务状态与浏览器播放另查，该工具不替代它们。

## 正式验收和失败回退

验收至少记录：候选散列与真实入口、三个服务状态、固定原帧原始模型输出对照、现场请求的同帧绑定、浏览器实际播放推进、新 MP4 的完整解码/索引/Range、旧录像兼容、原数据完整性、有限时长的帧率/CPU/内存/队列及内核异常。新录像要按验收前后 ID 集合差找到，不能按 boot_id 或列表第一条误取旧文件；列表参数 limit 上限为 50，记录多时逐页遍历。

全部完成后才将本次 acceptance.json 设为 passed=true，并更新主配置的 verification。分别记录编译、校验、服务切换、板端推理、浏览器、重启和长稳，不相互替代。当前 r2 的近黑画面与有限时间验证不能写成正常光照、真人/PAD安全或长期验收。

失败时：

1. 保存失败阶段、日志、当前 PID/boot/配置/媒体；该次结果保留 passed=false，新尝试另建结果文件。
2. 若候选已打开设备，按同样顺序正常停止，并验证其自己的关闭回执；不能证明安全关闭时不自动启动旧版。
3. 恢复本次备份的三个服务单位文件、主配置、启动前置配置；若改了独立录像入口也恢复。旧应用保持完整原目录，不用新目录冒充旧版本。daemon-reload 后仅在硬件允许重新打开时启动旧服务并完成有界就绪等待和实际播放检查。
4. 回退不删除新增 MP4、人员资料或历史失败记录。旧版本不能显示新格式录像时也保留文件。恢复记录写清“配置已恢复”“服务已启动”“媒体/推理已验证”各自状态，不能混为一个成功。

## 本说明的验证边界

本次实际完成只读采集、r2/r1 文件校验、页面重组字节比较、工具回归和现役 HTTP 就绪检查；未运行发布/回退/重启命令、未重新构建原生程序。以后版本必须新建发布清单和任务证据。完整历史构建可复现性、现场有人脸和长稳等剩余项见维护清单。
