# 2026-11-02：低延迟播放器候选、现场故障与恢复

日期依据：聊天客户端 Asia/Shanghai 2026-11-02；板端 UTC 2026-11-01 日志不改变归档日期。

执行 [低延迟 SOP](preview-low-latency-sop.md)。用户明确暂不能外拍，先完成软件与诊断；随后明确授权正常整板重启恢复现场。**候选只完成离线验证，未部署，不能宣称低延迟修复或验收通过。**

## 来源和证据

已读取两级 AGENTS、SOP、发布说明、维护计划、10-31 现场与录像压缩记录、相关源码。补充读取 `D:/xiangmuwendang/WCIS-FPAI/repos/FPAI30TAI图像FPGA/README.md`；本次该副本已记载 H.264，与 SOP 制定时“仍描述 JPEG”的旧观察不同，真实状态以现场入口、配置和散列为准。

证据根目录：`D:/yzd/tmp/preview-low-latency-20261102-003719/`。失败、基线、候选、回退分别保存。未做模型/原生构建，未修改 RTL、BOOT、模型、网络或音频代码。板端测试文件只放在 `/root/wcis-face/candidates/preview-low-latency-20261102-003719-offline`，模拟硬件测试没有打开设备。

## T0：现场冻结、故障与备份

直连 SSH 超时，既有网关 SSH 成功；两份结果在 `baseline/inspection.json` 和 `inspection-gateway.json`。

- 初始 boot `940910c3-d67a-44fc-98ad-30ee02396d7b`；owner PID 382、session `c64a1q9_`。本启动存在 `capture_arm / Hardware quarantined` 隔离标记，automatic_retry=false。
- owner、编码和封装进程为 defunct；8091 健康/摄像头请求被关闭，录像 source_ready=false。三个服务虽 active/running，不能证明采集健康；旧 status.json 的 ready 也不能替代新鲜帧推进。
- 未发现 PID 382 / 当前 boot 的正常 SDK 关闭回执；保存的 7391、7448 回执属于旧 boot，未拿来替代。
- 录像真实入口为 `recording-idle-compression-20261031-r1`。实际 auto/armed、current=null、队列为空，不是旧文档的 off。闲时压缩启用、自动清理关闭；压缩状态留有 `Compressed copy exceeds saving budget`，没有证据表明它导致摄像头故障。
- 板上存在 voice_gateway.py，未停止其他任务制造低负载条件。

下载并核验 53 个文件：主应用39项、独立录像8项、三个服务单位及主配置/启动配置/启动准备脚本。预期散列全部匹配，回退副本在 `rollback/board/`，清单为 `rollback/backup-manifest.json`。动态配置、旧关闭回执和录像文件名/大小清单另存 `baseline/dynamic-state.json`。

没有对人员库、录像原片与索引执行写入/删除；未对全部用户数据做前后逐字节校验，53文件核验不能外推为全部数据完整性证明。

## 用户授权的正常整板恢复

用户明确回复“现在可以，正常重启板卡”，允许本次恢复中断视觉和语音。

1. 确认没有活动录像，正常停止 recorder，检查 MainPID=0、inactive、Result=success；关闭回执为 off/idle、current=null、error=null。
2. sync 后请求 systemctl reboot，返回0。未强杀、未删除隔离标记，没有把整板恢复解释为故障 owner 已正常关闭 SDK。
3. 两次早期连接失败保留；随后确认新 boot `6bc39cf0-e747-41f8-8ae4-08aa76c12542`。启动早期8091尚未监听，继续只读等待，没有手动重复开设备。
4. 新 owner PID 359、session `eql3gar_`；最终模型缓存、硬件准入、960×540 H.264、录像输入 ready，帧持续推进。隔离标记仍保留且属于旧 boot。
5. 录像启动默认 off，随后恢复任务开始时的 auto。末次为 auto/armed、source_ready=true、current=null、error=null、detection_error=null。压缩仍启用、自动清理仍关闭。语音网关进程恢复，仅证明进程存在，不是语音功能验收。

证据：`baseline/pre-reboot-recorder.json`、`reboot-request.json`、`reboot-wait.json`、`after-reboot-*.json`。主应用保持原 r2，恢复诊断结束39项文件全部匹配正式清单。

## T1：恢复后的辅助基线

`baseline/recovered-diagnostic.json` 保存30秒、120次原始采样，`recovered-summary.json` 为统计。负载为现役后台、恢复的 auto 识别轮询和语音网关；没有实际浏览器呈现及真人/运动真值，不冒充三种受控负载。

| 指标 | 结果与限制 |
|---|---|
| 源帧率 | 约29.11 fps，captured增量/同板单调时钟 |
| 发布媒体帧率 | 约29.21 fps，批量发布和边界使其略异于源；不是屏幕呈现帧率 |
| 片段 | 去重41段，manifest时长均1.000秒；包括开始时已有窗口，不是30秒生成41段 |
| 实际进程参数 | GOP=30、无B帧、hls_time=1、列表12段，未调整 |
| 六个视觉进程CPU | 合计约0.892核，含自动识别；单窗数据，不与旧文档不同负载直接比较 |
| 录像 | 输入ready、无队列积压/丢帧计数、无活动录像；末次自动检测无人脸 |
| 端到端延迟 | 未测；无光学p50/p95/max、失显事件统计或旧JPEG同条件对照 |

原始采样包括摄像头状态、请求起止、片段列表和capture metadata、进程CPU tick/RSS、load。板端采集时间为请求下界，不是光学事件；未把frame_age、分片长度或媒体PTS拼成端到端延迟。

## T2：两个独立软件候选

`lan_stream/h264_player.js` 已在本地修改。真实生产由 serve_photos.py 同目录播放器文件提供，本轮没有替换板端该副本。

- 起播只取最新完整段，追加成功后定位至最新buffered区间末端前约0.35秒；非零PTS、分离/极短区间均限制在有效范围。
- `candidate-a/startup-only/` 默认catchUp=false；`candidate-a/bounded-catchup/` 默认catchUp=true，落后超过0.95秒才seek，至少间隔2秒，尊重暂停和正在进行的seek。两者保留250ms轮询，各自附散列清单。
- 首次及轮询清单检查session、编码、片段命名/顺序/时长；缺段或异会话停止并交回既有重连逻辑。
- stop取消fetch、sourceopen、SourceBuffer等待，清除监听/定时器；迟到结果不能复活播放。

参数只是实验提案。1秒段可能导致接近末端时断粮，seek限频也可能暂时保留积压。离线测试不证明画面不卡或达到300/500ms目标，因此未选定或发布优胜版本。

原播放器SHA256：`65924f9fbd6b716953dc12462632e8c77e79c2a6052cdf029539db55c63150c7`；本地追帧候选：`081b580cc58c2357750ba9548d87063d2187990eb4e1508f2d065c28a75dc11b`。

## 检查、失败及修复

- 新增 `tests/test_h264_player.cjs`，加载真实候选源码，16项全部通过：空缓冲、非零PTS、合法位置、缺段/异会话、网络延迟、暂停恢复、频率上限、停止取消及资源释放等。
- 既有7组页面JS回归全部通过，播放器语法检查通过。
- Windows六组Python回归：external_h264、h264_fragments、vpu_live_server、recording_service、recording_library、recording_compression，共67项中65通过、2项POSIX平台跳过。
- 板端独立目录补测external_h264共16项全部通过，含FIFO与inode轮换，不访问硬件。
- 新测试首轮浮点严格相等断言失败，改为容差并验证范围；`player-tests-first.txt`保留失败。Linux首轮遗漏h264_media依赖，补齐独立目录后复测；两轮日志均保留，没有把缺依赖算通过。
- 新增只读 `scripts/inspect_preview_latency.py`，输出拒绝覆盖，连接失败保存错误并返回非零，语法检查通过。它不执行重启/关闭/解除隔离，也不证明低延迟。

日志位于 `candidate-a/`，逐进程退出码见 `regression-summary.json`，Linux补测见 `linux-test-result.json`。

## 任务状态及后续

| 阶段 | 本次结果 |
|---|---|
| T0 | 初始冻结、53文件备份、故障留证完成；授权重启后健康/帧推进及39文件复核通过；未来切换前重新冻结动态状态 |
| T1 | 辅助诊断完成，外拍、误差、p50/p95/max、三负载及旧JPEG对照待测 |
| T2 | 两个软件候选和离线行为测试完成，真实浏览器/同条件延迟和卡顿对照待测 |
| T3 | 未执行；缺T2实测结论，不提前调整GOP、分片/录像窗口，也不标“无需执行” |
| T4 | 未完成30分钟、现场10次同帧、固定帧原始输出、跨两个60秒录像、全解码/Range等；软件回归不能替代 |
| T5 | 候选未发布，保留原r2和录像版本；阶段文档及当日归档完成，不生成passed=true发布收据 |

下一步先测现役光学基线，再分别实测起播版与限频追帧版；T2证明仍受分片等待限制时才进入T3。无外拍可继续浏览器辅助测试，不能解除正式发布的端到端门槛。隔离根因未定位，一次恢复和30秒观察不能证明长期稳定。

同步归档：`D:/bigfuture/竞赛/记录/2026-11-02.md`。


## 11-02 下午续作：浏览器对照、失败回退及最终网页预览修复

最新方案和有限验收见 [网页即时预览与 MP4 分离](preview-webjpeg-20261102.md)。本文前文是凌晨阶段记录，不能继续理解为候选尚未执行。续作证据根目录为 `D:/yzd/tmp/preview-low-latency-20261102-continuation/`。

1. 原1秒分片下60秒实浏览器对照：原播放器1781呈现帧/最大间隔176ms；仅起播优化1753帧/261ms；追帧版1098帧/1115ms。追帧增加断粮，拒绝采用。均为浏览器观测，不是光学总延迟。
2. 初次仅设GOP15的候选失败：驱动报 `Failed to set gop size`，真实仍是1秒段；24段列表超过新16秒上限，媒体503。此前文档已记载标准GOP不被驱动接受，本次未先核查该已知限制，且仅API ready的发布检查不足；随后把真实段长、关键帧及独立解码加入候选就绪检查，保留失败证据。
3. 后续现场曾出现另一boot `56a76c96-a7aa-4aad-b1a0-7d11b29ac5bf` 及采集超时。没有证据把采集超时归因于GOP改动。正常停止视觉服务、核验原版文件并恢复配置后，用户明确授权正常整板重启；新boot为 `eba65c31-d6c8-41ff-af67-568b800802b3`，r2实际视频恢复。未删除隔离标记。
4. 在学校服务器编译仅作用于FFmpeg编码子进程的MVX控制适配层，失败的标准GOP请求转换为厂商P_FRAMES并读回。模拟接口与板端0.5/0.2秒真实片段、每段首关键帧、完整解码均通过。参考 [FFmpeg 4.2.7 V4L2编码器源码](https://raw.githubusercontent.com/FFmpeg/FFmpeg/n4.2.7/libavcodec/v4l2_m2m_enc.c) 与项目厂商头文件 `ps_app/vendor/include/pipeline/vpu/mvx-v4l2-controls.h`。
5. 同浏览器60秒软件滞后估算：重启后r2中位1973ms，半秒分段配原播放器1407ms，0.2秒分段配原播放器1059ms。映射依据最新捕获元数据和名义媒体PTS，存在漂移/HTTP/显示误差，不是光学延迟；不能直接与最终JPEG的服务器帧龄作同指标百分比比较。半秒起播/追帧最大间隔552/891ms，均未选用。
6. 用户要求收窄，并明确保留MP4、只改预览。最终改为共享最新采集帧的15fps CPU JPEG网页预览，H.264录制恢复原r2参数；没有全系统回退旧版。短分片、控制适配层和播放器候选单独留档，未进入最终受管发布。
7. 最终实际网页播放、固定输入两次原始输出对照、10次无人脸现场归属检查、132秒录制及3段MP4共3930帧全解码/Range/定位/索引检查通过。4个人员库文件、116个既有录像相关文件散列一致。39项主应用、8项录像依赖核验通过；录像恢复执行前off。详细数字、CPU成本、未测光学/长稳边界见最终文档和收据。

本次不宣称已完成原SOP的30分钟三负载/光学指标、真人PAD或新版本整机重启验收。未做的计划不写成当天完成事项。
