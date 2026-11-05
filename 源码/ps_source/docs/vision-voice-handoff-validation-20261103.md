# 视觉与语音交接实测（2026-11-03）

本次按用户要求增加前台语音任务包装入口，已安装到现有板卡。正常结束及控制进程异常结束两个有限实板场景通过。使用方法见[交接引导](vision-voice-handoff.md)，可复核的分项、安装散列和验证边界见[验证摘要](../../logpack/05-release-receipts/vision-voice-handoff-20261103/verification.json)。日期按本次工作日期归档。

## 实现范围

- `wcis-visionctl run --cwd 工作目录 -- 程序 参数` 先排空录像、正常关闭视觉SDK并核验回执和进程/硬件锁，再启动语音程序。systemd管理整个任务进程组，ExecStopPost负责恢复视觉和原录像模式。
- 安装器只增加自有CLI、控制器和三个视觉服务的原生启动条件，启用原服务开机启动；安装前后owner PID/session一致。语音网关、音频程序、原生二进制、模型、RTL及BOOT未修改。
- 使用本次boot、owner、事务token及配置散列校验。异常回执、残留进程、隔离、配置变化或恢复失败会保留blocked状态，不能通过重复recover绕过；不清硬件隔离，不强杀摄像头/VPU。
- 语音任务须前台运行，日志进入journal，不支持交互标准输入。SSH断开后任务继续；Ctrl+C或stop请求正常终止任务并恢复视觉。

## 软件与安装验证

Windows及板端Linux均为23项测试通过，包括off/auto/manual模式恢复、正常及非零退出状态、暂停中断、恢复写入中断、关机延后、重复任务、配置变化、精确关闭回执、旧进程/锁未释放与隔离拒绝。软件测试中的模式覆盖不能替代三种模式的实板录像验收。

最终安装检查：已安装控制器与本地源码逐字节一致，CLI及三个drop-in准确匹配，三个服务均active且enabled。最终只读复查确认新帧及编码计数推进、模型缓存及硬件准入ready、录像off/idle且source_ready、error为空，暂停条件已撤销，事务restored。

## 有限实板结果

环境：systemd 245，boot `ca08d773-cea8-44fa-84c1-9841d7cf4ed3`；现役为960×540连续VPU H.264预览及MP4录像，初始录像off。用无硬件访问的模拟语音程序验证交接，不调用真实ASR/TTS。

| 场景 | 暂停耗时 | 模型就绪 | 源画面推进 | 全部恢复 |
|---|---:|---:|---:|---:|
| 前台程序正常退出 | 2.255秒 | 9.398秒 | 11.274秒 | 12.153秒 |
| 仅交接控制进程SIGKILL | 1.838秒 | 9.131秒 | 11.280秒 | 12.143秒 |

模型、画面及全部恢复三列均从恢复动作开始计算。正常场景从观察到语音进程退出到全部恢复为12.951秒，包含约0.798秒生命周期清理开销；异常场景没有记录kill瞬间时间，不推导kill到ready耗时。此前修正后的单次手动恢复为19.587秒，说明现场负载/缓存会影响结果；这些是单次样本，不是平均值或SLA。

两次都检查了原owner正常SDK关闭、旧编码/封装进程退出、语音阶段三个视觉服务保持停止、手动start被原生条件跳过、新画面连续推进、模型就绪和录像输入恢复。字面参数 `$HOME %n space` 原样传入，重复交接请求被拒绝。

异常试验仅终止我们自己的 `wcis-vision-voice.service` 控制进程，未终止摄像头owner或真实语音网关。systemd清理模拟语音子进程后自动恢复。最终owner66938/session `tjgmzwne`，录像仍off/idle。真实语音网关在这两个测试窗口内PID52860/start_ticks5443738未变；更早时间段身份曾变化，不能声称全天未重启。

## 首轮失败及修正

最初用ExecCondition检查事务状态。实板systemd 245的预览服务配置为Restart=on-failure，跳过启动后仍出现自动重试，不能稳定保持inactive。模拟程序因此断言失败，恢复检查拒绝重开视觉。旧owner5786已有正常关闭回执且锁空闲，没有证据说明这是相机/VPU故障。

改为systemd原生 `ConditionPathExists=!/run/wcis-vision-handoff/hold.json`：暂停前建立属于该boot/token的条件文件，恢复前只撤销匹配文件。原生条件验证中三个服务保持inactive，四秒内重试计数不增长。先保存失败事务及旧配置，在精确核验原关闭回执、当前配置、空闲锁和无当前boot隔离后完成一次受控迁移与恢复，再重新做上表两次完整测试。没有删除隔离标记或强开设备，未重启板卡。一次性迁移脚本未作为通用“强制解锁”工具交付。

## 未覆盖与证据位置

没有验收真实语音识别/播报/麦克风、整板冷启动、浏览器首帧、光学端到端延迟、长稳、多轮压力或auto/manual真实录像交接。开机启动已配置，不能称已经通过整板重启验证。恢复就绪不代表完成一次真实人脸/PAD推理。

本地完整取证保存在 `D:/yzd/tmp/vision-voice-handoff-20261103/`，包括normal/supervisor-kill收据、关闭回执、失败首轮、Linux测试及安装/最终健康检查。板端任务证据目录 `/root/wcis-face/candidates/vision-voice-handoff-20261103`；长期事务收据 `/var/lib/wcis-vision-handoff/runs/`。仓库只保留精简验证摘要，队友日常使用不依赖这些临时目录。实现入口为[控制器](../scripts/vision_handoff.py)、[安装器](../scripts/install_vision_handoff.py)和[测试](../tests/test_vision_handoff.py)。
