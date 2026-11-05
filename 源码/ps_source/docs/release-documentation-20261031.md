# 2026-10-31：发布与回退资料整理

日期依据：聊天客户端 Asia/Shanghai，2026-10-31。用户要求执行维护清单第四项，并询问以前是否做过、存在哪里。本轮只整理现有功能的工程发布资料，没有更新板端应用或启停服务。

## 原有资料与缺口

项目 `docs/` 已有 10-13/10-15 部署记录、10-30 H.264 r1 部署、10-31 r2 验收；`scripts/` 有早期照片/摄像头/BOOT 部署工具；每次实际操作及备份分散在 `D:/yzd/tmp/h264-ffmpeg-20261030`、`preview-maintenance-deploy-20261030` 等目录。它们有证据价值，但没有统一说明现役文件对应关系，部分旧脚本会采用历史服务参数和页面目录，不能直接重跑。

读取项目两级 AGENTS.md 及 `D:/xiangmuwendang/WCIS-FPAI/repos/FPAI30TAI图像FPGA/README.md`，后者仍包含旧 JPEG 状态；以本地源码和本轮只读板端快照为现役依据，没有访问旧站点、前台浏览器或修改共享工具。

## 具体整理过程

1. 在 `D:/yzd/tmp/release-runbook-20261031` 建独立证据目录，使用已有连接读取正式清单和 39 项文件、四个服务单位文件、独立录像目录和启动前置文件。逐项 SHA256 与正式清单一致。另按上次回退清单读取原 r1 的 39 项文件并验证，不复制人员照片或录像内容。
2. 将上述只读副本归档到项目 `outputs/release-baseline-20261031/`，共 108 个文件；原任务目录及备份未删除或移动。该副本是保存的版本证据，不是新安装目录，也不保证后续板端未变化。
3. 确认实际首页是 `--site` 指向的 `site/index.html`，与 `D:/yzd/tmp/camera-pad-overlay-20261027/deployed-index.html` 逐字节一致。追到该任务 deploy.py 的区块替换和脚本版本号更新；应用根目录旧 index.html、camera_panel.html 不是现役首页输入。
4. 把首页固定部分保存为 `release/540p-r2/site-template.html`，复用现有 npu_photo/camera_panel.html，通过新离线组装脚本重建，与板端 SHA256 `6c04bfed7cf62923d11f26f9869097d0eb01b1f4a6ea0858a89bf85341cce178` 相同。没有改变页面行为或部署页面文件。
5. 主应用 39 项分为 32 项直接源文件、1 项重组首页、1 项构建收据、2 项历史 HTML、3 项原生程序。owner 的源码压缩包散列、包内 cpp 与本地 cpp、学校收据及二进制散列均核对；另两个原生程序仅明确当前源码入口及已发布二进制身份，未宣称其历史完整构建可复现。
6. 录像实际入口仍在独立 recording-h264-20261030-r1 目录。核对 recording_service/library、panel HTML/JS、vpu_live_server、h264_fragments/media 共 7 个运行依赖，均与本地源文件相同。该目录的旧 external_h264.py 不由录像服务导入，不能把同名差异直接视为现役错误或批量覆盖。
7. 新增只读文件校验工具，按冻结清单核对并拒绝越界路径、重复项、符号链接、空清单；不修改期望散列来“修复”差异。新增有界 HTTP 就绪等待工具，将端口未监听与启动失败区分，要求同一 owner 输出推进、正确 boot、540p H.264 和录像 off/idle；没有自动启停或绕过硬件隔离。
8. 编写发布/回退统一说明和新任务记录模板，明确服务停止顺序、当次 SDK 关闭回执、配置组恢复、独立录像校验、真实 --site、动态停止回执、分页上限及新录像 ID 集合差。服务/配置备份是回退依据；数据文件保留，不能以回退为由清理录像。

## 新入口与文件

- `docs/release-runbook.md`：统一操作说明及原资料索引。
- `docs/release-source-map.md`、`release/540p-r2/source-map.json`：完整文件关系与来源边界。
- `docs/release-checklist-template.md`：每次发布的可复制记录模板。
- `release/540p-r2/`：主应用、录像、服务、启动文件、整个快照的冻结清单，以及页面模板和 owner 构建收据。
- `scripts/verify_app_release.py`、`assemble_camera_site.py`、`wait_visual_ready.py`：只读验证、离线页面重组、有界只读就绪等待。
- `tests/test_release_tools.py`：工具的故障场景回归。
- `README.md` 和 `docs/maintenance-plan.md` 已增加统一入口并更新完成状态。

## 验证结果与边界

9 项回归通过，覆盖文件篡改/缺失、路径越界/重复/空清单、模板标记错误、端口延迟、静止帧、错误 boot、录像错误和持续更换 owner 的情况。真实保存副本检查：主应用 39、录像运行文件 7、服务 4、启动文件 3、回退应用 39、全快照 108 项均通过；首页重组逐字节一致。

通过 SSH 标准输入仅执行新就绪工具的 GET 检查，没有上传或安装程序、没有重启服务。当前 HTTP 健康、模型/硬件准入、同一 owner 的 H.264 输出推进、录像输入及 off/idle 条件通过；这不是重新执行模型、录像、浏览器或重启验收。依据为本轮 `validation.json`、各 `*-check.json`、`unit-tests.log`、`live-readiness.json`。

本轮没有重新构建、执行部署/回退、改动 BOOT/模型/驱动/网络配置或音频任务。新版整板重启、正常光照有人脸、长期压力、完整历史构建复现等边界仍保留。归档操作仅新增/合并副本，不改写旧原始证据。

关键本地来源：本轮源代码与清单；`D:/yzd/tmp/release-runbook-20261031/snapshot/`；`D:/yzd/tmp/preview-maintenance-deploy-20261030/board-evidence/backup/`；`D:/yzd/tmp/camera-pad-overlay-20261027/deploy.py`；`D:/yzd/tmp/preview-maintenance-20261030/integration-build-receipt.json` 与源码压缩包。记录同步合并到 `D:/bigfuture/竞赛/记录/2026-10-31.md`。
