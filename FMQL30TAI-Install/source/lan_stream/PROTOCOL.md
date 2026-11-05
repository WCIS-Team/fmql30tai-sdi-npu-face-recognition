# 画面/结果协议 v1

本文件是应用间的新约定，不是已存在的人脸/语音模型API。
当前SDI适配器接实际SDK；未来模型需另写适配器保留同帧身份。

传输：POST `/api/frame`，`Content-Length` 必须明确，无chunked。
数据：`[4字节JSON长度，大端uint32][UTF-8 JSON][像素字节]`。
GET `/api/frame?after=<revision>` 使用同一封装，返回200为最新完整包、
204为同一版本无更新、503为无画面/已断流。`revision` 是接收器更新编号，
不是物理摄像头帧号，服务器重启后从0开始。

```json
{
  "schema_version": 1,
  "stream_id": "sdi-process-unique-session",
  "frame_id": "1",
  "timestamp_us": "123456789",
  "timestamp_basis": "ps_dma_done_monotonic",
  "source": "camera",
  "pixel_format": "RGB565LE",
  "width": 1920,
  "height": 1080,
  "stride_bytes": 3840,
  "models": {"face": "not_connected", "voice": "not_connected"},
  "faces": [],
  "subtitles": []
}
```

JSON最大64KiB；像素最大8MiB；宽高1..4096且`stride_bytes*height`
必须恰好等于像素长度。RGB565LE的行stride可包括最多4096字节的额外padding。
PS应用当前发紧密行，不发padding。其他像素格式先在适配器明确转换或扩展协议，
接收器不会把未知格式当作RGB565显示。额外未识别字段在v1中忽略。
64位帧号/时间传十进制字符串，`stream_id`为1..80个字母/数字/横线/下划线；
每次应用启动变更ID。同一会话frame_id严格递增，timestamp_us非递减。
接收器只接受一路当前发送源，保留最近32个退休会话ID拒绝其晚到包。

`source` 可为camera/demo/unverified，是发送端声明，不是物理来源证明。
`timestamp_basis` 当前只能是ps_dma_done_monotonic。不能传模型完成时间
代替原帧时间，不能未经映射填入音频采样时间或PC墙钟时间。

PS汇合层可把同帧模型结果直接附在POST画面JSON里，接收器校验后原子发布。
也可POST `/api/results` 发不含像素的JSON：schema_version、stream_id、frame_id、
models、faces、subtitles。只允许更新仍然有效的最新帧；错帧/断流返回409，
格式错400。不缓存等待下一帧，不将迟到结果平移到其他帧。

```json
{
  "schema_version": 1,
  "stream_id": "sdi-process-unique-session",
  "frame_id": "1",
  "models": {"face": "ready", "voice": "ready"},
  "faces": [{"box": [0.1, 0.2, 0.3, 0.4], "name": "示例标签", "confidence": 0.9}],
  "subtitles": [{"start_us": "123456780", "end_us": "123456800", "text": "示例字幕"}]
}
```

box为**当前展示原帧**上的归一化[x,y,width,height]，不是模型输入图上的坐标。
需要在PS模型适配器中完成crop/resize/letterbox/对齐坐标恢复，尚未实现。
置信度0..1，有限数；最多100个框、20段字幕，标签128字、字幕2048字。
字幕与帧时间同一基准，仅保留覆盖timestamp_us的区间（闭区间）。
模型状态ready/not_connected/error；空结果不能自动推断模型已经就绪。
模型状态与结果必须一起提交；新帧未携带模型结果则状态恢复not_connected。
网页用绘图/textContent显示，不把名称或字幕当HTML执行。

未来录像要保存像素/编码画面和**同会话同帧结果及时间**，网页叠加不会写进录像像素。
目前无录像/持久化/上传API，没有占用64G SD卡。
当前服务只用于可信局域网，不是带账号/TLS/公网转发的发布服务。
# 诊断状态扩展（2026-10-14）

后续厂商恢复增加 `source: "ps_capture"`：发布已验证的 SDK/取帧记录与实时 PS 心跳，
不访问 SDI 锁定寄存器。该来源下五个硬件标志可为 null，表示未知；不得从旧启动沿用
锁定结果。capture_state 为 `bridge_verified` 或 `capture_timeout`，可带布尔
`path_test_passed` 表示该启动中的独立测试源通路验证结果，默认 false。
测试通路通过不会创建真实摄像头帧，也不代表自动识别实际 SDI 制式。
以下原 `sdi_status_ddr` 来源的硬件标志仍必须为布尔，状态枚举仍仅支持
`blocked_incompatible_bitstream`，不能混用两个来源的字段含义。

`POST /api/device-status` 接收独立 JSON，返回 204；非法数据 400、旧序号/已退休启动 409。
`GET /api/status` 的 `device` 字段返回最近的诊断状态。接收超过 3 秒没有更新时，
只返回 `{"connected": false}`，不会继续展示旧信号为实时信号。

状态不是图像帧，不增加 `frames_received`，不修改 `/api/frame` 或模型结果。
`timestamp_us` 是 PS 读取 DDR 状态的单调时间，不是曝光/DMA 完成时间，
不能把它当作 `/api/results` 的帧身份。

必填字段：`schema_version: 1`、`source: "sdi_status_ddr"`、UUID `boot_id`，
uint64 十进制字符串 `sample_id`、`timestamp_us`、`status_sequence`，
布尔值 `signal_locked`、`transport_locked`、`writer_fresh`、`progressive`、`qpll_locked`，
0–4096 整数 `width`、`height`，以及当前唯一支持的
`capture_state: "blocked_incompatible_bitstream"`（这组字段限定 `sdi_status_ddr` 来源）。

`sample_id` 在同一启动中严格递增；`status_sequence` 来自 PL 导出序号。
`writer_fresh` 只有观察到 PL 序号增加才为真。首个样本、停止的导出器均不能作为实时
输入锁定的证据。重启更换 `boot_id` 后不接受旧启动的包。

