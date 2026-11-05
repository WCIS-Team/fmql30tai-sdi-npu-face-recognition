# 540p r2 发布文件对应表（2026-10-31）

11-03现役清单已扩展为40项（新增h264_live.py），5个直接变更文件及原r2对应关系见[当前发布目录](../../logpack/05-release-receipts/preview-h264-live-20261103/README.md)。下表仍是10-31冻结基线。

由当天只读 SFTP 快照逐字节核对。此表是保存的发布基线，不自动代表后续板端状态。完整散列见 [source-map.json](../../logpack/05-release-receipts/540p-r2/source-map.json)，操作入口见 [发布与回退说明](release-runbook.md)。

| 板端相对文件 | 来源/入口 | 对应类型 |
|---|---|---|
| `camera-owner-build.json` | `release/540p-r2/owner-build.json` | build_receipt |
| `camera_interlock.py` | `npu_photo/camera_interlock.py` | direct_source |
| `camera_owner_runtime.py` | `npu_photo/camera_owner_runtime.py` | direct_source |
| `camera_panel.html` | `outputs/release-baseline-20261031/app/camera_panel.html` | preserved_artifact |
| `camera_panel.js` | `npu_photo/camera_panel.js` | direct_source |
| `camera_requests.py` | `npu_photo/camera_requests.py` | direct_source |
| `external_h264.py` | `lan_stream/external_h264.py` | direct_source |
| `frame_stream_protocol.py` | `npu_photo/frame_stream_protocol.py` | direct_source |
| `gallery.py` | `npu_photo/gallery.py` | direct_source |
| `h264_fragments.py` | `lan_stream/h264_fragments.py` | direct_source |
| `h264_media.py` | `lan_stream/h264_media.py` | direct_source |
| `h264_packager.py` | `lan_stream/h264_packager.py` | direct_source |
| `h264_player.js` | `lan_stream/h264_player.js` | direct_source |
| `index.html` | `outputs/release-baseline-20261031/app/index.html` | preserved_artifact |
| `migrate_gallery.py` | `npu_photo/migrate_gallery.py` | direct_source |
| `model_backend/face_pad.py` | `model_backend/face_pad.py` | direct_source |
| `model_backend_runtime.py` | `npu_photo/model_backend_runtime.py` | direct_source |
| `native_forward.py` | `npu_photo/native_forward.py` | direct_source |
| `owner_pad.py` | `npu_photo/owner_pad.py` | direct_source |
| `persistent_gallery.py` | `npu_photo/persistent_gallery.py` | direct_source |
| `pl_preprocess.py` | `npu_photo/pl_preprocess.py` | direct_source |
| `receive_video_stream.py` | `npu_photo/receive_video_stream.py` | direct_source |
| `recognize_frame.py` | `npu_photo/recognize_frame.py` | direct_source |
| `recognize_photo.py` | `npu_photo/recognize_photo.py` | direct_source |
| `recording_embed.js` | `npu_photo/recording_embed.js` | direct_source |
| `recording_library.py` | `npu_photo/recording_library.py` | direct_source |
| `recording_panel.html` | `npu_photo/recording_panel.html` | direct_source |
| `recording_panel.js` | `npu_photo/recording_panel.js` | direct_source |
| `recording_service.py` | `npu_photo/recording_service.py` | direct_source |
| `run_frame_replay.py` | `npu_photo/run_frame_replay.py` | direct_source |
| `run_photos.py` | `npu_photo/run_photos.py` | direct_source |
| `serve_photos.py` | `npu_photo/serve_photos.py` | direct_source |
| `site/camera_panel.js` | `npu_photo/camera_panel.js` | direct_source |
| `site/index.html` | `release/540p-r2/site-template.html + npu_photo/camera_panel.html` | assembled_site |
| `site/recording_embed.js` | `npu_photo/recording_embed.js` | direct_source |
| `vpu_live_server.py` | `lan_stream/vpu_live_server.py` | direct_source |
| `wcis_camera_owner` | `ps_app/src/wcis_camera_owner.cpp` | native_binary |
| `wcis_face_cached` | `npu_photo/src/cached_npu_runner.cpp` | native_binary |
| `wcis_face_pl_retained` | `npu_photo/src/retained_pl_runner.cpp` | native_binary |

39 项均已核对正式清单。32 项直接对应本地源文件；首页由模板和摄像头片段重组后与板端逐字节一致；1 项构建收据；2 项历史 HTML；3 项原生程序。

## 首页的来源

正式服务的 `--site` 是应用下 `site/`。首页 SHA256 `6c04bfed7cf62923d11f26f9869097d0eb01b1f4a6ea0858a89bf85341cce178` 与 `D:/yzd/tmp/camera-pad-overlay-20261027/deployed-index.html` 相同。原生成过程见该任务 `deploy.py`：替换旧首页中的 camera-panel 区块、更新脚本版本号；更早的双视图过程见 `D:/yzd/tmp/camera-panel-views-20261027/deploy.py`。H.264 发布保留真实 --site；r2 继续复制它。

本次将不变的完整页面部分保存为 `release/540p-r2/site-template.html`，摄像头区块来自 `npu_photo/camera_panel.html`，用 `scripts/assemble_camera_site.py` 重组。重组字节和现役首页一致，没有部署页面改动。根目录 `index.html` 与旧 `camera_panel.html` 为历史受管副本，保留完整性校验但不作为首页生成输入。`h264_player.js` 由 serve_photos.py 单独提供，camH264 由 camera_panel.js 动态创建；recording_embed.js 动态插入指向 8093 的 iframe。

## 原生程序与构建收据

owner 构建收据的源码压缩包散列、包内 cpp 与当前 cpp、板端二进制散列三者已串联核对。学校目录见 `owner-build.json`。该收据是历史成功构建证据，本次没有重新连接学校构建或声称其当前可用。另两个原生程序可追到 CMake 源码入口并与 r1/r2 发布散列一致，但本轮未追溯其当时完整构建环境与源码归档，不声称从当前源码可逐字节复现它们。它们在此 540p 单 owner 路径中的参数保留，不擅删备用入口。

## 独立录像服务

实际执行目录 `/root/wcis-face/candidates/recording-h264-20261030-r1`。以下 7 项组成当前本地 Python/页面依赖闭包（另依赖系统 Python/FFmpeg）；都与当前本地源文件逐字节一致：

| 文件 | 本地来源 |
|---|---|
| `recording_service.py` | `npu_photo/recording_service.py` |
| `recording_library.py` | `npu_photo/recording_library.py` |
| `recording_panel.html` | `npu_photo/recording_panel.html` |
| `recording_panel.js` | `npu_photo/recording_panel.js` |
| `vpu_live_server.py` | `lan_stream/vpu_live_server.py` |
| `h264_fragments.py` | `lan_stream/h264_fragments.py` |
| `h264_media.py` | `lan_stream/h264_media.py` |

该目录还留有非运行入口副本，包括旧 external_h264.py 和 deploy_storage.py。录像服务不导入 external_h264.py；不能因为它与 r2 不同就批量覆盖。未运行 deploy_storage.py。同名录像文件在主应用中也有副本，39 项主应用清单不能替代上述独立目录校验。

## 服务与启动前置文件

四个 systemd 单位文件保存在 `outputs/release-baseline-20261031/services/`，启动前置文件保存在 `startup/`；对应 services/startup manifest 独立校验。照片服务 ExecStartPre 会只读挂载 SD 检查 BOOT 文件，并配置网络与更新启动证明，所以不能为了只读检查而手动执行 boot_prepare.py。存储服务 ExecStop 会卸载 eMMC；常规应用更新只停三个视觉服务，不停存储服务。
