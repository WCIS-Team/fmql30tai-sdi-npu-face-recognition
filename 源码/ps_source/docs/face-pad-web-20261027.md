# 防伪网页结果接入（2026-10-27）

## 问题与核实

用户发现网页未显示防伪功能。检查发现 8091 后端健康接口已返回 `presentation_attack_detection=same_frame_model_evidence`、`pad_security_calibrated=false`，但正式网页与 `npu_photo/camera_panel.html` 仍写死“活体防伪：未评估”，`camera_panel.js` 未读取防伪字段。10 月 26 日的记录明确只完成后端接入；网页确实尚未接齐。

初次访问板端 127.0.0.1:8091 被拒绝，核查监听地址后改用 192.168.1.113:8091，健康检查 ready；这是绑定地址差异，不是后端停止。现场另有检测请求竞争，接口可返回 409，本次未停止其他客户端或重启服务。

## 实现

- `npu_photo/camera_panel.js` 新增防伪状态映射，显示模型判断为真人、疑似攻击、不确定、无人脸、多人不适用、未评估、过期、失败与后台忙。身份匹配不代替防伪结果。
- 比对防伪证据与检测帧的 frame_id、session、boot_id 和原帧散列；按后端帧龄和页面经过时间处理过期。暂停时清除显示结论，暂停自动检测后仍可手动检测一次。服务错误、画面源失效或会话切换时不持续显示先前真人结论。
- `npu_photo/camera_panel.html` 用动态状态区替换固定文案，标明 PS 裁图、NPU 双模型、只属于对应检测帧以及尚未校准。更新脚本版本查询参数，刷新页面后加载新脚本。
- 仅替换正式站点 index.html 和 camera_panel.js，无需服务重启；未修改 PL 位流、模型、人员库或录像设置。

## 验证和边界

JavaScript 语法检查及三组 Node 回归通过：防伪状态/帧绑定/过期、视频与检测独立运行/暂停/单次检测、检测框和身份对应。单次检测回归特别检查自动模式保持暂停时仍能显示刚返回的防伪结果。

后台浏览器实际验证了后台忙、无人脸、暂停及结果过期。单次检测返回后显示“活体防伪：未检测到人脸”，对应检测帧 1200961；截图保存为 `D:/yzd/tmp/pad-web-20261027/pad-panel.png`。模型真人/攻击等状态的显示经过构造数据测试，不算新真人或攻击样本的板端验收。本次现场画面无人脸，没有补造真人标签。

当前处理仍是 PS/OpenCV 裁图与 NPU 双模型推理。PL 防伪裁图未部署，新版本人工标注实拍及阈值校准未完成，网页不声称安全放行。

## 来源和部署证据

- 本次本地来源：`npu_photo/camera_panel.html`、`npu_photo/camera_panel.js`、`npu_photo/owner_pad.py`、`npu_photo/serve_photos.py`、`docs/face-pad-owner-20261026.md`。
- 补充资料：`D:/xiangmuwendang/WCIS-FPAI/wiki/PL/plvid.md`，旧 SFace 概述未作为当前模型依据。
- 本机任务目录：`D:/yzd/tmp/pad-web-20261027`，含原文件、部署脚本、散列报告和截图。
- 板端站点：`/root/wcis-face/releases/20261014-b5a454c11d22/run-01/site`；备份：`/root/wcis-face/candidates/pad-web-20261027/original-index.html`、`original-camera_panel.js`。部署前检查原文件未变，替换后逐字节核对；失败自动恢复逻辑未实际触发。
- 同日归档：`D:/bigfuture/竞赛/记录/2026-10-27.md`。
