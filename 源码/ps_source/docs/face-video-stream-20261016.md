# 本机视频解码与SSH动态帧输入

2026-10-16已实现、安装并上板验证。动态联调使用本机视频源，原静态DDR回放保留用于单帧基线。
本轮聚焦ModelBackend输入适配，不改网页、业务调度、模型、RTL或BOOT，不接触SDI引脚/采集寄存器。

## 本机路径及运行

视频在用户本机，非学校服务器或板端：

`D:/yzd/tmp/face-video-input/videos/head-pose-face-detection-female.mp4`

本机PowerShell直接运行：

```powershell
python D:/renlianshibie/fpga_project/scripts/stream_video_to_board.py
```

默认使用上面的视频、RGB565LE、latest模式，最多向板端送30帧。自己有视频后：

```powershell
python D:/renlianshibie/fpga_project/scripts/stream_video_to_board.py --video "D:/my-videos/test.mp4" --mode latest --max-frames 30
```

`--mode all`按顺序处理每个解码帧，速度跟随板端，不丢帧；`--mode latest`按视频时间推进，
本机只保留一个最新候选帧，板端处理完才发下一帧，过时帧在电脑端跳过。
`--seconds 5`限制视频源时间，`--pixel-format BGRX8`可改为8位颜色输入。
每次测试最多1～300个已发送帧。Ctrl+C设置停止标志，等在途帧返回后正常结束协议，
不把终端控制字符写入二进制通道，也不强杀板端SDK进程。

本机日志：`D:/yzd/tmp/face-video-input/runs/<id>/summary.json`、`results.jsonl`、
`board.events.jsonl`及 `board.stderr.log`；不保存每个解码帧文件。
板端最新结果路径由启动消息给出，视频文件始终留在本机。
测试期间启动器临时暂停原照片服务，结束后恢复，照片服务配置未改变。

本机依赖及默认视频路径在 `ps_app/configs/video-stream-local.json`：当前私有Python为
`D:/yzd/tmp/face-video-stream-20261016/venv/Scripts/python.exe`，已安装OpenCV 5.0.0.93、NumPy 2.5.4。
普通 `python` 缺少依赖时会转交给这个已配置的本机解释器并等待完成。
可复用依赖清单为 `scripts/requirements-video-stream.txt`；迁移机器时在新私有环境安装并更新配置，
不擅改共享工具、学校SDK或全局Python。SSH继续复用项目既有连接配置，不在视频/协议/运行日志存凭证。

## 测试视频来源

视频取自 [Intel公开推理样例库](https://github.com/intel-iot-devkit/sample-videos)，
原文件名不变，未修改视频。下载脚本为 `scripts/fetch_face_video_sample.py`，默认保存到上述本机目录。
实际下载地址、授权和归属记录在该目录 `source.json`，同时保留
`Intel-sample-videos-LICENSE.txt`（上游CC-BY-4.0）。
视频SHA256：`e9290821ac0e0a186e8f5cae5e3b56e8062921642d46a5f65f1ca5b311811fc5`，
15,628,037字节；本机实际解码为768×432、12 FPS，共1615帧。
仅作为功能与链路测试素材，不用来登记人员或评估人群识别准确率。

## 实际链路与SDI差别

本机OpenCV VideoCapture解码 → 本机BGRX/RGB565打包 → 单个无PTY的SSH二进制通道 →
板端PS接收/校验、临时raw像素 → SDK上传至PL DDR → 已有PL缩放/对齐与NPU模型 →
stdout返回JSON识别结果。解码参考 [OpenCV VideoCapture官方接口](https://docs.opencv.org/4.13.0/d8/dfe/classcv_1_1VideoCapture.html)。

它在“已采集的一帧”适配层替代SDI帧源。与固定DDR图相比，内容、序号、视频时间和DDR租约不断更新，
可查变化画面、结果归属、输入格式和过时帧处理。每个新帧要经PS接收并上传一次PL DDR，
同一帧的检测与对齐仍共用原帧，不重复上传。

它没有经过真实SDI接收、像素时钟、跨时钟FIFO或持续DMA写帧。
默认跳帧在电脑端发生，板上只有一个在途模型请求；不能由此证明真实采集缓冲不会溢出，
也不能把SSH传输耗时、此次完成率或整帧选择率当作物理SDI吞吐。
未来PL直入摄像头可以省掉本测试的SSH接收和PS上传，新帧所有权/覆盖保护仍需接入。

## 协议及实现

- `scripts/stream_video_to_board.py`：本机解码、单候选帧缓冲及发送，默认保留原视频尺寸。
  记录本机解码/打包、发送、往返及解码至结果的时间。
- `npu_photo/frame_stream_protocol.py`：8字节magic、JSON长度、payload长度及有界元数据；
  帧带流UUID、递增序号、视频PTS、尺寸、步长、格式及像素SHA256。最大metadata 4KiB、payload 32MiB。
  分片读取重组、长度/校验不符和不支持格式会在SDK访问前拒绝。
- `npu_photo/receive_video_stream.py`：完整接收后才交给现有ModelBackend，共用
  `recognize_frame.py`，不另写人脸识别算法。只有当前原帧在tmpfs，处理后覆盖，退出清理。
- `pl_preprocess.py`：已打包入口可显式使用源序号作为PL帧号，要求uint32且严格增加；
  每个新帧另有租约token。对齐引用同一帧，NPU仍保留其DDR区间。
- 通用测试启动器增加stream分支，原静态入口的板端脚本与配置保持原版本。
  新入口为 `/root/wcis-face/run-video-stream.py --stream`，配置为
  `/root/wcis-face/video-stream-current.json`。

返回结果逐项检查流UUID、序号、PTS及像素SHA，避免旧帧错配；两端未做时钟同步，
所以只记录各端自身的持续时间，不声称得到精确单向网络延迟。
板端 `board_receive_ms` 从收到包首字节到组装/校验完成，
`pipeline_ms`为完整帧收到后的处理链路，包含PS临时写入及SDK上传/PL缩放。
初始化、模型CPU进程准备及服务恢复不计入逐帧时间。

## 验证结果

1. 8项CPU检查通过：字节分片重组、多包/结束包、截断、坏校验、超长前缀、错误几何/格式、
   已知红绿蓝的RGB565小端/步长填充，以及慢消费者只取最新帧。
2. 板端同一接收进程依次收单人RGB565、无人脸BGRX、多人BGRX，源序号为1/50/500。
   输出分别为1/0/2个人脸，框、状态和NPU原始输出SHA与既有对应参考一致。
   三个租约token互异，支持新内容、帧号跳跃、尺寸和格式切换。
3. 真实视频all模式4帧：序号1/2/3/4，不跳帧，4个像素SHA和4份检测输出均不同。
   处理中位565.9ms，本机往返中位649.0ms，板端包组装中位74.7ms。
4. latest模式截取5秒：60帧解码、8帧发送/处理、52帧在本机跳过；
   序号1/9/17/25/33/41/49/56，8个像素SHA和检测输出均不同。
   处理中位561.3ms，往返中位656.0ms，包组装中位76.9ms。不能外推为12 FPS的模型处理率。
5. 调用与键盘中断相同的本机停止回调，在完成2帧后结束并恢复原服务，未强杀设备进程。
6. 坏校验、半包EOF、重复帧号均拒绝，正常包边界EOF能完成退出；每项后服务均恢复ready。
   数据协议错误不写硬件隔离标记，真实SDK失败仍遵循既有隔离规则。
7. 最终人员JSON和原图SHA、服务单元、启动号不变，空闲无PL帧工作进程、NPU设备句柄及tmpfs交换文件。

首轮启动包装程序错误引用静态种子配置，随后SSH包装对象的文本/字节行接口不一致，
均在首个视频帧处理前发现并修正；本机解释器转交也改为等待子进程并转发停止。
失败目录 `video-all`、`video-all-v2`保留，修正后的实际通过记录为 `video-all-v3`。
停止验证后的Windows复核脚本曾以GBK读UTF8日志，修正读取编码并复核原已通过结果，没有重复硬件试验。

## 部署与证据

应用 `/root/wcis-face/apps/video-input-8ed79ca5ef31`，沿用原模型与学校服务器产出的C++可执行文件，
本轮无模型或AArch64构建、无新BOOT/RTL，无重启。
启动器SHA256：`cb4bd2eded2d1297dab64eb756d3047c22646141c6069349c9566c34ac716a51`。
板端任务目录 `/root/wcis-face/candidates/video-input-20261016`。

本机任务证据 `D:/yzd/tmp/face-video-stream-20261016`：
`candidate.json`、`preflight.json`、`verification.json`、`source-checks.json`、
`launcher-install.json`、`wire-failures.json`、`final-state.json`，
以及 `video-all-v3`、`video-latest`、`video-stop`内的 `summary.json`。
后台项目站点本轮HTTP200已读取，页面PS采集示意仍不等于本地PL物理采集实现；
所有实际功能和时延结论以以上源码/板端证据为依据。
