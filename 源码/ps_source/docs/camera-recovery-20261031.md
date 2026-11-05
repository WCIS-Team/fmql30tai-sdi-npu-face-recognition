# 2026-10-31 摄像头故障与整板重启恢复

日期按聊天客户端 Asia/Shanghai；板端原始日志采用 UTC，本文时间已换算为北京时间。用户先授权重启摄像头主站服务，失败后明确授权整块板卡重启。

## 故障与验证边界

- 原启动号为 `fd5d27fd-00f6-4c41-8991-a796091a53f9`。隔离文件 `/root/wcis-face/hardware-review-required.json` 记录 `phase=capture_dma`、`Pending camera request exceeded its lifetime`，禁止自动重试。主站 8091 未监听，8092 状态为等待采集。
- 此前日志中有 VPU 连续内存分配失败，但不能据此认定它导致了更早的采集超时，也不能认定是队友模型主动关闭摄像头。语音相关服务是常驻服务，没有批处理完成时间。
- 18:18 执行一次 `systemctl restart wcis-face-photo.service`；systemd 命令返回成功不代表就绪。后续主站因原启动的隔离标记退出，状态 failed、网页未恢复。启动失败清理又出现编码器退出等待超时；核对 PID 66553 的精确 FIFO 路径后，仅向本次遗留 FFmpeg 发送 SIGTERM，确认退出。未删除隔离标记，未强杀进程。

## 整板恢复过程

1. 保存原启动号、服务状态/视觉单位文件、隔离标记、内核和主站日志及录像状态。主应用仍为 `/root/wcis-face/apps/camera-h264-20261030-r2`；独立录像服务已另行升级，未恢复旧录像单位文件。
2. 重启前录像模式 off、状态 idle、没有活动段或待写队列。执行 `sync` 后，于 18:20:30 下发 `systemctl reboot --no-block`，使用正常系统关机启动流程，没有更换 BOOT、位流、驱动或模型，也未删除人员资料和录像。
3. SSH 恢复后确认启动号变为 `940910c3-d67a-44fc-98ad-30ee02396d7b`。早期服务 active 时 8091 尚未监听，继续等待真实 HTTP 和采集状态；主站日志约 18:21:25 就绪，18:21:26 媒体 ready。
4. 18:21:37 至 18:21:42，摄像头状态 ready、960×540 H.264；同一会话 `c64a1q9_` 的帧号由 331 推进到 481，编码计数由 330 推进到 480。此为约五秒短窗，不作为长期帧率保证。
5. 本机直接访问 `http://192.168.1.113:8091/` 和 `/api/health` 均 HTTP 200，健康状态 ready、模型缓存和硬件准入 ready。8092 ready；录像输入 ready、off/idle、error 为空。三个视觉服务及四个语音相关服务均 active。
6. 18:22:03 复查仍 ready，帧号推进到 1111。本次启动内核未出现所筛选的 MMU ABORT、watchdog timeout 或 page allocation failure 行。原隔离标记保留，属于旧启动，不是通过删除保护来恢复。

## 结果与仍未验证内容

整板重启已完成，网页可访问、摄像头采集与编码恢复，语音相关服务自动启动。此次没有新发起人脸识别、语音端到端测试、录像写入或浏览器实播验收，不将服务状态或编码计数等同于这些功能已经重新验收。采集超时的根因、其他负载是否有影响和长期稳定性仍未确定。

## 本地来源和证据

- 维护流程依据：`docs/release-runbook.md`、`docs/h264-ffmpeg-20261030.md`；同时读取 `D:/xiangmuwendang/WCIS-FPAI/repos/FPAI30TAI图像FPGA/README.md`，其中旧 JPEG 描述不替代本次实际 H.264 状态。
- 服务重启证据：`D:/yzd/tmp/camera-service-restart-20261031/` 的 `restart-101830281722.json`、`followup-1018.json`、`final-state.json`、`startup-cleanup.json`。
- 整板重启证据：`D:/yzd/tmp/camera-board-reboot-20261031/` 的 `before.json`、`reboot-request.json`、`reconnect.json`、`after-initial.json`、`readiness.json`、`final.json`。
- 本记录同步追加到 `D:/bigfuture/竞赛/记录/2026-10-31.md`，保留同日既有内容，不移动或改写来源材料。
