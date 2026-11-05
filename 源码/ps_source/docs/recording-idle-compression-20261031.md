# 2026-10-31：H.264 录像闲时压缩

日期依据为客户端 Asia/Shanghai 2026-10-31。用户最终限定：只处理 H.264，旧 MJPEG 不压缩；轻微有损，保留原文件供比较。

## 交付结果

独立录像服务已切换至 `/root/wcis-face/candidates/recording-idle-compression-20261031-r1`，入口仍为 `http://192.168.1.113:8093/`。默认启用闲时压缩，保留录像 off 和原自动清理策略。原照片/视觉服务、预览服务及其硬件所有者没有启停或修改；未构建模型、原生程序、RTL、位流或 BOOT。

当前 28 段录像中，25 段是旧 MJPEG，全部排除在候选之外；3 段 H.264 分别为 13,185、2,340、13,083 字节。正式 worker 在真实空闲窗口后自动将这三段标为“小于 256 KiB，跳过”，没有生成正式压缩副本。它们不能代表正常光照和复杂运动下的压缩空间。

现场另有既存限制：本轮连接时 `wcis-face-photo` 已 failed、`wcis-vpu-live` 已 inactive，8091 连接被拒，录像输入不就绪；部署起止两服务状态及 PID 未变。本次不把录像服务升级解释为恢复了采集、识别或实时预览，也未自行重启硬件。页面输入未就绪时改为显示“当前没有可用录像输入”，避免回退标签误报当前编码格式。

## 实现与边界

- `npu_photo/recording_compression.py`：仅枚举完整、非回收站的 H.264/MP4；不操作 `.part` 活动录像。连续空闲 60 秒才开始；录像写入、前台媒体读取、CPU 总忙碌比例大于 15% 或一分钟系统 load 大于 0.8 时暂停，重新满足 60 秒空闲后继续。负载检测不是推理请求的严格互斥，不宣称与识别绝对零重叠。
- 使用板上既有 FFmpeg 4.2.7 的软件 `libx264`，CRF 18、medium、单编码/解码线程；通过 taskset 固定到一个允许的 CPU，nice 19，并在每约一秒内最多运行 0.15 秒。实际 CPU 上限包含调度与轮询误差，不作为严格实时保证。没有调用第二路 VPU、SDK 或采集设备。当前资源策略只接受不超过 960×540 的源摘要尺寸；更大尺寸跳过，不借本功能宣称 1080p 能力。
- 只保留至少缩小 10%、帧数和尺寸一致、每帧 PTS 与源 MP4 时间线差不超过 1 ms、完整解码及平均 SSIM≥0.98 的副本。编码失败、收益不足或校验失败保留原片。整体 SSIM 门槛不是人脸识别/PAD 准确率或主观“无明显损失”的证明。
- 原视频、原采集时间索引、原摘要均不改写；副本为同 ID 的 `.compressed.mp4`，结果为 `.compression.json`。源 MP4 文件时间线与原采集时间索引继续分开；压缩版不冒用旧索引中的字节偏移。读取期间 pin 住原片，回收站/永久删除保护也覆盖副本。
- 临时文件仅在录像根下固定 `.compression-work` 中，计入配额；检查挂载、剩余和预留。子进程取消/停止时先终止并继续已暂停的子进程以确保退出，必要时 kill；清理只处理固定工作目录中的普通文件，不跟随链接。进程崩溃残留在下一次持有独占 recorder 锁后清理，不作为可回放副本公开。
- 页面提供启停开关、原片/压缩版分别回放与下载。压缩副本纳入存储、软删除、恢复和永久删除。页面明确“保留原片，实际释放 0 B”；副本缩小量只是潜在替代节省量，不能当作磁盘已释放。

## 实测与故障修正

1. 当前正式 H.264 的 8 秒、240 帧近黑录像，直接以 CRF 18 重编码：13,185 → 23,166 字节，反而增大约 75.7%。这只支持该样本不值得重压，不能据此断言所有 H.264 都无收益。
2. H.264 隔离测试片段：60 帧、960×540，1,174,154 → 969,747 字节，减少 204,407 字节（17.4%），SSIM 0.994040。该输入是本任务早期从旧录像制作并已保存的 H.264 测试素材，不是新一次正式 VPU 录像，不能外推当前正式摄像头场景的收益。原媒体/索引/摘要散列不变，计账 2,144,728 字节与实际文件长度总和一致。
3. 首次时间基配置把编码器时间基设为微秒/源时间基，旧 FFmpeg 输出 MP4 虽有 60 个 packet，却只解码出 59 帧；末帧被 edit list 标记丢弃。严格帧数/时间轴检查拦截，未发布失败副本。修正为保留 FFmpeg 的编码器默认时间基，输出后仍逐帧校验；最终 60 帧全部解码、0～2.36 秒逐帧 PTS 一致，播放器总时长 2.4 秒。
4. 最终媒体集成测试为缩短测试墙钟时间，仅在任务测试脚本中缩短 duty 休息；产品 worker 的 0.15/0.85 秒 duty 未放宽。单独的真实 duty 调度测试验证录像时计数不再推进、恢复空闲后推进、关闭策略后线程与子进程均退出、临时计账归零。不能把加速集成用例 35.7 秒当作生产后台转码耗时。媒体用例子进程峰值 RSS 约 136 MiB，只是一个 540p 短样本，不是最坏内存保证。
5. 隔离 HTTP 服务验证压缩版 Range 206、1024 字节读取、完整下载、启停策略、存储统计、回收站禁止读媒体、恢复重新可读。没有在正式目录删除或移动录像。
6. computer-use 后台浏览器在隔离页实际解码 960×540，播放从约 0.1 秒到 2.4 秒 ended=true、readyState=4、无媒体错误；修正了原有 CSS 覆盖 hidden 导致 MP4 下出现损坏 JPEG 占位和多余进度条的问题。正式页确认压缩开关已启用，三个 H.264 显示跳过，旧 MJPEG 正常列出，未切前台。

## 验证、部署与回退

- 本地 `tests/test_recording_service.py`、`test_recording_library.py`、新增 `test_recording_compression.py` 共 32 项通过；覆盖旧格式排除、候选幂等、原片保留、忙碌/读者准入、策略持久化、压缩副本发布权限、配额分类、回收站与清理。`recording_panel.js` 语法检查通过。
- 更新前核对录像 off、无活动段/待写队列，备份独立录像 unit，切换新候选并只重启 `wcis-face-recording`。新版本 active、API 可用、默认压缩 enabled；未因主视觉服务既有故障而擅自操作硬件。
- 全部 28 段的 84 个原媒体/索引/摘要文件部署前后 SHA256 一致。自动 worker 仅新增三个跳过结果 sidecar，25 段旧 MJPEG 无压缩结果文件。动态服务停止回执不混入原录像校验。
- 运行文件冻结到 `release/recording-idle-20261031/recorder-manifest.json`，8 个文件；5 个修改文件与本地源码散列一致。原 `release/540p-r2` 清单保持历史冻结，主视觉应用 r2 不受本次 recorder 独立升级影响。
- 原 unit 备份为新候选目录 `backup/wcis-face-recording.service`。回退需先关闭录像/闲时压缩，正常停止新录像服务，恢复该 unit 并 reload/start；原片从未改写，旧服务不会显示压缩副本，但副本文件会保留。部署脚本包含失败回退，未执行正式回退演练。
- 尚未覆盖长时间混合识别/预览/录像/回放负载、最大段内存、真实断电恢复或不同复杂场景的人脸细节/算法准确率验收。

## 本地来源与证据

- 主要源码：`D:/renlianshibie/fpga_project/npu_photo/recording_compression.py`、`recording_service.py`、`recording_library.py`、`recording_panel.html`、`recording_panel.js`。
- 任务证据：`D:/yzd/tmp/recording-idle-compression-20261031/`，含 `current-h264-crf18.json`、`h264-worker-trial-failed-timebase.json`、`h264-worker-trial.json`、`scheduler-result.json`、`http-trial.json`、`deployment-baseline.json`、`deployment.json`、`final-status.json`、`recorder-manifest.json` 和后台截图。
- 板端隔离数据：`/mnt/wcis-emmc/wcis-face/recording-tests/idle-compression-20261031`；不是正式录像目录。
- 补充资料：读取 `D:/xiangmuwendang/WCIS-FPAI/repos/FPAI30TAI图像FPGA/docs/recording-storage-20261027.md` 和对应录像源码。这是旧 MJPEG 快照，当前编码状态以本地 10-30 记录和板上实际文件为准。
- 成熟编码/指标实现：[FFmpeg 文档](https://ffmpeg.org/ffmpeg.html)、[SSIM filter](https://ffmpeg.org/ffmpeg-filters.html#ssim)。文档不替代当前旧版二进制实测；曾尝试的 concat option 语法在 4.2.7 不支持，用户缩小范围后已整体删除 MJPEG 转码路径。

本记录同步合并到 `D:/bigfuture/竞赛/记录/2026-10-31.md`，不改写原文档或其他同日记录。
