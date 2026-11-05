# H.264 预览延迟根因复核（2026-11-02）

11-03后续：已在板端FFmpeg4.2.7重现等待，并部署原VPU编码的连续fMP4预览、保留MP4；结果见[修复实测](h264-live-preview-20261103.md)。以下保留11-02诊断时的连接状态和原r2源码分析，不表示当前仍不可连接。

本轮按用户“找出延迟的原因然后再修改”重新检查原 H.264 链路。已确认两处结构性等待，并用保存的板端码流重现封装等待；没有再次变更正式预览格式、帧率、编码器或板端配置。当前网页、录像接口及网关均连接超时，不能声称完成本轮板端分阶段测量或修复部署。

## 网页不需要先录完一段录像

原路径为：采集 → VPU H.264 → FFmpeg解析/复制封装 → `/dev/shm`临时HLS分片 → HTTP → 浏览器MSE。

保存录像是另外一个消费者：录像服务读取同一已编码码流，触发后保存eMMC MP4。即使录像处于off，HLS预览分片仍会生成。临时视频分片不是60秒录像；网页播放等待来自当前封装/供给实现，不是MP4录像或浏览器的必然要求。

## 已确认的等待及证据

| 位置 | 代码/证据 | 可以确认的影响 |
|---|---|---|
| 服务端完整分片 | `lan_stream/external_h264.py` 的 `-hls_time 1`、`independent_segments+temp_file` | 原实现等整片完成并在关键帧边界切段后才改名发布；片内较早的帧在此期间无法由网页取得 |
| 服务端准入发布 | `external_h264.py::_observe()`、`h264_media.py::manifest()` | 要等真实采集索引与整片sample匹配才对外提供；monitor每0.2秒检查，增加轮询等待。保护不能简单删除 |
| 播放器从较旧段起播 | `lan_stream/h264_player.js` 的 `slice(-2)`、`buffered.start(0)+.01` | 选最近两段、从较旧段头部播放，追加新段后自然保留一段左右的媒体积压 |
| 网页轮询和追赶 | 同文件250ms轮询、落后buffer末端超过3秒才跳到末端前1秒 | 取段还有轮询等待，且不会主动消除较小的积压。此前粗暴缩缓存/seek已出现更多停顿，不能直接照搬 |

不把这些区间机械相加为摄像头到屏幕总延迟：网络、实际编码完成、浏览器解码/显示尚未在本轮现场分离。历史浏览器约2秒的软件滞后估算也不是光学测量。

已排除一个容易误判的原因：`encoder.stdout.read(65536)`采用`bufsize=0`，读取上限不表示必须攒满64KiB。本机管道试验只发送1字节后保持进程2秒，读取约31ms即返回该字节；此测试不能代替检查驱动/FFmpeg内部缓冲。

## 针对原因的离线对照

使用 `D:/yzd/tmp/preview-maintenance-20261030/real-media-snapshot-r2/` 保存的真实板端H.264，30fps定时送入；三个条件完全使用`-c:v copy`，没有JPEG编码、H.264重编码、模型或摄像头。记录每帧提交与完整可用片段出现的同一主机单调时钟，排除首末各30帧后统计。

| 条件 | 输出 | 封装等待p50 / p95 | 完整性 |
|---|---|---|---|
| 原整段HLS方式 | 5个整段；每段30帧，首段60帧 | 555.9 / 1005.1 ms | 180帧完整解码 |
| 逐帧fMP4复制封装 | 180个片段，每段1帧 | 66.8 / 67.1 ms | 180帧完整解码 |
| 同一个FFmpeg同时输出原HLS和逐帧fMP4 | HLS继续保留；预览每帧输出到管道 | 66.8 / 67.2 ms（逐帧输出） | 两个输出各180帧完整解码 |

结果证明：**不改变H.264编码与30fps输入，也可以去掉按整段发布造成的等待，并保留原录像消费者的分片输入。** 本次只验证封装层候选，未接入正式HTTP和播放器，不能宣称网页总延迟已经达到67ms。

限制：离线工具为隔离目录安装的FFmpeg `9.0.2-essentials_build-www.gyan.dev`，不是板端4.2.7；首段分片边界出现60帧，这也是必须实测实际片段、不能只看目标参数的例子。4.2.7源码已含`frag_every_frame`等选项，但板端行为、额外封装CPU、网页实际帧率及缓冲稳定性仍须现场验证。无AArch64/model构建，本地CPU复制封装实验不属于模型构建本地回退。

复跑工具：`scripts/probe_h264_packaging_wait.py`。要求指定现有FFmpeg路径、保存的init/m4s目录和新的输出目录；不会打开硬件、覆盖输入或清理用户录像。例如：

```text
python scripts/probe_h264_packaging_wait.py --ffmpeg <ffmpeg路径> --snapshot <保存的HLS目录> --out <新证据目录>
```

本轮证据：`D:/yzd/tmp/preview-h264-latency-diagnosis-20261102/reproducible-probe/results.json`、`reproducible-probe.log`、`unbuffered-pipe-check.json`和`current-connectivity-and-source.json`。首轮实验因Windows当前目录造成init文件位置错误而失败，日志/产物保留；修正进程cwd后，独立工具三组复跑全部通过。

## 由证据确定的修改范围

只针对复制封装和供给时机：复用现有VPU H.264、同一FFmpeg输入，在原HLS输出旁提供逐帧fMP4，播放器按到达的小片段连续追加；录像继续原输入。新连接仍须从关键帧开始，不能任取一个依赖旧帧的P帧起播；预览慢客户端不能阻塞编码/录像，缓存需有界并按会话拒绝过期帧。

以上为已验证到封装层的修改候选，尚未接入或部署；原编码/播放器源文件散列保持不变。需要连接恢复后先补采集→编码输出→封装发布→HTTP接收→MSE呈现的分阶段时间线，再完成HTTP/播放器候选及同负载CPU、帧率、MP4对照。未完成部分不记作已实现。

技术依据：[FFmpeg 4.2.7 HLS文档](https://raw.githubusercontent.com/FFmpeg/FFmpeg/n4.2.7/doc/muxers.texi)明确整段临时文件的发布行为及关键帧切段规则；[4.2.7 MP4封装源码](https://raw.githubusercontent.com/FFmpeg/FFmpeg/n4.2.7/libavformat/movenc.c)包含逐帧分片选项；[W3C MSE ISO BMFF格式](https://www.w3.org/TR/mse-byte-stream-format-isobmff/)定义moof/mdat媒体片段，并不要求积攒一秒或完成录像。
