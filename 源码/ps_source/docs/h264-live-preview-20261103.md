# H.264 网页预览延迟修复（2026-11-03）

**已运行 `camera-low-latency-20261103-v2-live`：960×540、原VPU H.264编码、约30fps预览、原MP4录像。CPU JPEG双编码方案已撤回。** 本轮是有限现场验证，不等于原SOP光学指标、30分钟负载矩阵或完整产品验收通过。

用户要求先查明延迟原因、保留MP4、避免降帧及重复编码。本次仅修复既有预览。已读取两级AGENTS和 `D:/xiangmuwendang/WCIS-FPAI/repos/FPAI30TAI图像FPGA/README.md`；补充快照的旧JPEG描述不作为现役状态依据。日期按客户端Asia/Shanghai，板端UTC文件名可能仍为11-02。

证据目录 `D:/yzd/tmp/preview-h264-live-20261103/`；板端任务 `/root/wcis-face/candidates/preview-h264-live-20261103`；冻结交付与回退见[发布目录](../../logpack/05-release-receipts/preview-h264-live-20261103/README.md)。

## 原因和实现

网页不需要录完60秒录像才播放。原预览读取临时HLS：服务端等整片封装及关键帧边界，再由监控发布；播放器轮询整片列表、从较旧位置起播。录像是另一个消费者，off时仍有这些等待。详见[根因记录](h264-preview-latency-cause-20261102.md)。

板上FFmpeg4.2.7以保存的实际H.264按30fps提交，各条件180帧、全部复制封装：

| 条件 | 暖态封装等待 p50 / p95 | 验证 |
|---|---|---|
| 原整段HLS | 719.5 / 1835.9 ms | 180帧全解码 |
| 逐帧fMP4 | 67.0 / 67.0 ms | 每片1帧、180帧全解码 |
| 同一FFmpeg输出原HLS及逐帧fMP4 | 67.0 / 67.1 ms（逐帧输出） | 两路各180帧全解码 |

67ms只证明封装等待，不是摄像头到屏幕延迟。证据为 `board-packaging-results.json`、`board-packaging.log`。

- `lan_stream/external_h264.py` 保留原VPU编码参数（GOP30、无B帧、2M码率）及原1秒HLS录像输出；同一个复制封装进程增加stdout逐帧fMP4输出。没有第二个编码器或CPU JPEG预览线程。
- 新 `lan_stream/h264_live.py` 解析完整片段，按真实输入索引绑定采集身份、排除60个合成预热帧。缓存前一/当前GOP，最多120帧、16MiB；无新鲜源、序列缺口或慢客户端时停止供给。现场缓存通常约40～56KiB。
- `npu_photo/serve_photos.py` 持续HTTP供给现有owner的片段，最多4个共享流连接，有发送超时/缓冲上限。预览解析失败仍排空stdout，避免阻塞录像。`vpu_live_server.py` 的8092页面只代理同一实时缓存，不另开设备。
- `h264_player.js` 连续读取并追加MSE，从已到齐缓冲末端前250ms起播。默认速率0.985，处理真实采集与名义30fps的节奏差；小幅调速有2秒间隔/滞回。仅积压超过0.9秒且距上次跳转至少3秒才追帧，暂停时不跳转；定期移除旧缓存。
- 原生二进制沿用r2，不重编译。规范C++源码撤回此前CPU JPEG线程后，与保存的r2源码逐字节一致；被撤回版本保存在 `outputs/preview-low-latency-20261102/experiments/ps_app/src/wcis_camera_owner_webjpeg.cpp`。模型、SDK、RTL、BOOT和音频未修改。

逐次追加时改速曾产生大量短暂waiting；改为滞回后减少。100ms起播余量、MediaSource无限时长未显示更好结果，未采用。各单因素JSON保留，不称参数已最优。

## 启动失败与授权恢复

1. 正常关闭JPEG版owner4513、确认SDK关闭/无pending/exit0后恢复r2 owner27947，完成基线。首个连续片段候选native30044在合成预热阶段报 `External raw sink write deadline`，未出现VPU预热完成标记，stdout为 `device_opened=false`；不能称相机DMA故障。隔离后还原r2配置、视觉保持停止，没有清标记或同boot强开设备。
2. 用户明确允许正常重启后执行恢复。新boot `ca08d773-cea8-44fa-84c1-9841d7cf4ed3`，原r2 owner326/session `00trpfcv` 恢复；39项散列、模型缓存、帧推进及录像输入正常。证据 `authorized-reboot-result.json`、`after-authorized-reboot.json`。
3. 保存码流的完整Python管道回放通过；正常关闭r2后，仅测试真实VPU合成预热，不打开SDK/摄像头。60帧预热完成，owner1156 camera requests/captured/commands均0、正常关闭，外部编码/封装进程正常退出。随后恢复r2 owner1190。
4. owner1190正常关闭后切换v2，HLS解码、采集绑定、逐帧供给和录像源检查通过。当前owner5786/session `oxpr7ys8`，encoder5779、mux5780。最终JS更新只更新受管文件及散列，未再次重启owner。

**首次原始输入管道超时的具体根因仍未查明，后续成功不等于根治。** 首轮FFmpeg临时日志未保全，native stdout/stderr/fault已找回。新代码增加退出前持久保存有界日志/退出码，是取证改进；没有完成候选整板重启或重复启动可靠性验收。失败完整经过保留在[首轮试验记录](h264-live-trial-20261103.md)。

## 浏览器与资源结果

延迟为真实采集元数据映射到浏览器媒体位置的软件估算，记录HTTP往返误差；不包含源事件进入相机及物理屏幕扫描，不能代替光学端到端指标。

| 条件 | 播放帧数 / 时长 | 软件位置年龄 p50 / p95 | 其他观察 |
|---|---|---|---|
| 原r2预览，录像off，第1窗 | 1794 / 60秒 | 2622.5 / 2963.9 ms | 最大帧间隔42.6ms |
| 原r2，第2窗 | 1797 / 60秒 | 2817.7 / 3183.9 ms | 最大42.7ms |
| 最终v2，含录像及定期识别 | 2651 / 90.008秒，约29.45fps | 562.0 / 600.5 ms | 最大54.3ms，无媒体错误 |

最终窗暖态84个估算样本最大1074.7ms，不能只报中位数。缓冲距末端中位353ms；浏览器累计报告18个丢帧，前5秒后8/2504帧（约0.32%）；19次waiting，最长90ms。现场为无人脸，不能外推多人脸/PAD高负载。证据 `browser/candidate-quality-concurrent-20261103-90.json`、`browser-final-quality.json`。r2两窗位于前次任务的 `browser/r2-20261103-60.json`、`r2-resource-20261103-60.json`。

早期180秒窗只收到204次 `requestVideoFrameCallback`，曾疑似一秒一帧；随后30秒同步计数：回调58次、presentedFrames879、总视频帧891且媒体位置连续推进。该后台环境中回调次数不能当呈现帧数。最终90秒回调/呈现均2651；异常记录保留，未静默删除。

| 六个视觉进程窗口 | 平均CPU核数 | 比较边界 |
|---|---|---|
| 原r2，单浏览器、录像off、10Hz状态采样20秒 | 0.624 | 重启前，有内存/交换压力 |
| v2，同样公共状态采样20秒 | 0.636 | 重启后，不含额外逐帧诊断请求 |
| v2，单独预览页，30秒只读进程计数 | 0.587 | 测量窗无诊断轮询/识别请求；没有原版同条件被动基线 |

不宣称CPU下降，也不拿历史0.3/0.5核或JPEG混合负载1.24核直接计算增幅。v2末次RSS约229MiB；原版重启后快照约217MiB、重启前约128MiB，不能把跨boot差额全归因于代码。量化净资源增量仍需同boot同负载对照。证据 `baseline-aligned.json`、`stream-common.json`、`candidate-passive-cpu.json`。

8091实际首页及8092独立页已打开确认：H.264、readyState4、未暂停、媒体位置推进；首页识别继续返回无人脸，视频独立播放。`website-final.png`证明页面播放，不证明光学延迟。

## 模型、录像、数据和软件验证

- 两次固定PNG与基线比较：YuNet12个输出及MobileFaceNet特征输出/人脸结果一致。10次现场请求和并发6次请求的boot/PID/frame/source hash绑定通过；16次均无人脸，PAD未校准，真实身份/多人脸/防伪效果未覆盖。
- 132秒录像伴随每10秒识别：3个MP4分别1800、1800、330帧，共3930帧；全帧解码、1秒seek、HTTP206 Range、索引通过。后续90秒播放窗含约65秒录像及定期识别，额外两段1800、150帧；正常收尾并恢复off/idle，队列无积压/丢帧，额外媒体检查见 `final-probe/extra-videos.json`。
- 索引一行代表一个HLS源片段、samples=30。验收脚本最初误用“行数等于帧数”触发断言；核实格式后改成累加samples，对齐summary/解码帧数、时间单调及源帧连续。没有因此修改录像实现。
- 人员库4文件及原125个录像相关文件散列不变，新增验收素材保留。主应用40项、录像8项散列、唯一owner、启动配置及当前boot无隔离检查通过；辅助入口散列/任务/前版元数据已同步本次真实值。
- Windows流相关43项：41通过、2项既有POSIX跳过；Linux隔离软件目录43项全通过；录像32项通过；Node8项新播放器行为和7个原相机测试文件通过。软件测试未打开硬件。见 `linux-tests-final.log`、`regression-final.json`。

## 现役与回退

主应用 `/root/wcis-face/apps/camera-low-latency-20261103-v2-live`；独立录像副本 `/root/wcis-face/candidates/recording-low-latency-20261103-v2-live`，8项代码未改。主清单 `video-stream-current.json` 与启动配置 `face-camera-ready-20261020/deployment.json` 的app一致。5个直接变更文件与本地源码散列一致，原native二进制与r2相同。

收据 `/root/wcis-face/candidates/preview-h264-live-20261103/20261103-v2-live/acceptance.json`，本地副本见发布目录。明确：光学测量、30分钟矩阵、候选整板重启、首次预热超时根因均未完成；5次重连/前后台矩阵与真实人脸/PAD也未完整覆盖。

回退为原 `camera-h264-20261030-r2` 和原独立录像服务，冻结于本次 `20261103-v2-live/prepared.json`，不是JPEG或中间短分片版。控制器rollback仅适用于本次boot，先结束录像/停视觉，验证本次SDK正常关闭及子进程退出，再恢复并检查健康和实际媒体。若有新隔离或缺关闭回执则停止，不能清标记强开；不删除人员库/录像。操作资料见发布目录README。
