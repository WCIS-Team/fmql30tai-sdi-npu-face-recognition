# 连续H.264预览有限发布（2026-11-03）

现役主应用 `camera-low-latency-20261103-v2-live`，原VPU H.264约30fps预览及MP4录像。实现、失败、实测与未覆盖范围见[本次记录](../../../ps_source/docs/h264-live-preview-20261103.md)。JPEG CPU双编码方案已撤回。

- `acceptance.json`：本次boot的有限验证收据、40项主应用/8项录像散列、健康、媒体身份、浏览器质量、数据保护和回退目标。
- `app-manifest.json`、`recorder-manifest.json`、`source-map.json`：全部受管文件和本地来源。5个变更文件保存在 `source/`；未变文件沿用r2冻结副本，原生程序未重新构建。
- `evidence/`：浏览器原始90秒质量记录/汇总、CPU窗口、模型/录像验证收据、数据与索引检查、软件回归日志、授权恢复和首次失败证据。主网站验证图为 `website-final.png`。
- `rollback-prepared.json`：本次原r2配置、单位文件、启动配置及已有数据冻结。`rollback-control.py` 是任务控制器的留存副本，使用原板端位置及下方命令；不要在Windows直接运行或重跑prepare/switch。

收据仅对应boot `ca08d773-cea8-44fa-84c1-9841d7cf4ed3`、owner5786/session `oxpr7ys8`时的观察，下一次任务必须重新读取现场。原生构建来源、软件测试、实际播放、光学延迟和整板重启是不同证据等级。

## 回退

目标主应用 `/root/wcis-face/apps/camera-h264-20261030-r2`，目标独立录像 `/root/wcis-face/candidates/recording-idle-compression-20261031-r1`；以 `rollback-prepared.json` 中实际路径/散列为准，不覆盖后续变化。原r2文件在此次收口时再次逐项核验。

在**同一boot、无当前隔离、其他工作负载身份未变化**且需要回退时，先核对实际配置/录像，再使用板端本次控制器：

```sh
python3 /root/wcis-face/candidates/preview-h264-live-20261103/remote_control.py rollback 20261103-v2-live
```

控制器会正常结束录像、依次停止三个视觉服务，读取本次owner的SDK关闭回执（closed、无pending、exit0），确认旧owner/编码/封装进程退出后再恢复冻结配置，启动并检查健康、HLS关键帧/解码及录像输入，最后恢复原录像模式。保留人员库及新旧录像，不停止音频。

若boot改变、出现隔离标记、SDK未正常关闭、其他任务变化或配置不再对应本次候选，停止使用该命令；重新冻结实际现场并按[发布说明](../../../ps_source/docs/release-runbook.md)处理。不得清标记强行启动或拿历史成功回执替代本次回执。

## 未验收

光学300/500ms指标、30分钟三负载矩阵、完整5次重连/前后台矩阵、真实人脸/PAD高负载、候选整板重启及首次原始输入管道预热超时根因。CPU跨boot对照不证明节省；软件位置年龄约562/601ms也不等于摄像头到屏幕总延迟。
