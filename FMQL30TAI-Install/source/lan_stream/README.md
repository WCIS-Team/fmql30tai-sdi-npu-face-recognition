# 第一版：SDI 画面与识别结果网页

**当前入口（2026-10-30）：** [阶段验收](../docs/acceptance-20261030.md)、[维护计划](../docs/maintenance-plan.md)。现役为 `external_h264.py`／`vpu_live_server.py` 配合单 owner 的 960×540 H.264 链路。下文是早期原始帧接收路线的历史说明，不能作为现役启动操作手册；不执行历史 `--run-camera` 示例。当前停止功能扩展。

无摄像头时，可查看[照片人脸识别参考路径](../photo_reference/README.md)的本机 CPU 实际结果，启动后地址为 `http://127.0.0.1:8090/`。此入口展示照片测试记录，与下文的板端实时采集通路分别验收。

**历史板端状态（2026-10-14）：经用户明确授权，已恢复厂商 BOOT、重启并验证
SDK 控制接口。** 硬件 VTC 测试帧已完整到接收端，真实摄像头仍为 0 帧。
新版硬件入口有启动身份/有效期、独占锁、一次取帧记录和失败标记检查；旧程序继续封住。
不要执行下文旧的 --run-camera 示例。网页提供当前真实诊断状态。
详见 [厂商恢复与通路验证](../docs/board-factory-restore-20261014.md)。

下文采集说明和“尚未上板/本轮未访问”记录原开发阶段，只描述预期路径及此前验证，
不代表当前已实现或验证摄像头取帧。

本版接入现有 **SDI → PL → PS udma RGB565 帧缓存**接口，不依赖模型。
PS 只取完整帧、读取像素并发送；网页转换像素和叠加结果。
默认保持配置的 1920×1080 分辨率，取帧/发送目标 2 fps，没有 PS 软件缩小、
颜色转换或 JPEG 编码。2 fps 是保守试验配置，不是已验证的板端性能。

**已完成 AArch64 交叉编译、本地协议与浏览器验证；尚未上板。**
没有连接板子、打开板端设备、替换 BOOT、启动模型或操作 SD 卡。
实际 SDI 不出图的问题仍由用户线下调试。没有模型也可以显示有效画面；
不能保证摄像头一打开必然有画面，取帧/SDK/位流/网络仍必须工作。

## 本机先看网页

- 双击 `start-demo.cmd`：当前首页推送 RGB565 色条，显著标注“测试图 · 非摄像头”；
  默认不生成任何人脸/语音结果。只证明电脑网页/协议，不能证明板端出图。
- 双击 `start-receiver.cmd`：启动接收网页，等待板端程序；不会打开摄像头。
- 关闭窗口或 Ctrl+C 停止接收服务；不添加自启、不改防火墙。
- 本机 `http://127.0.0.1:8088/`；PS 和其他设备使用启动窗口显示的电脑物理网卡 IPv4。
  使用同一局域网可达地址；实际板子到电脑、其他浏览器连通性仍待验证。

不再把首页连接到旧 JPEG 推流。旧 JPEG 代码保留用于回归，页面为
`/jpeg-preview`；原 `stream_demo.cpp`/`demo_sender.py` 只能推该旧通道。
JPEG 旧页面没有新版本的画面/结果同步机制。

## 准备好的板端程序（先审核，再决定部署）

源码：`../ps_app/src/wcis_camera_preview.cpp`。
配置：`../ps_app/configs/camera-preview.yaml`。
已编译产物：`../outputs/camera-preview/wcis_camera_preview`。
它是实际 SDK 取帧应用，不是生成测试图的 demo。

当前配置的 SDI 输入为 1920×1080；输入必须与真实 SDI 信号及当前位流一致。
程序不自动识别任意 SDI 制式，不能用一份配置适配所有摄像头。
用户需求目标是**在硬件支持范围内自动适配不同SDI规格**，不是永远手填固定规格。
当前手动配置仅是现有SDK接口的首版限制，自动检测/安全切换尚未实现，
具体底层证据与后续接口边界见 `SDI_AUTO_ADAPT.md`。
本适配器只接 `0x40080000` 的第一路、RGB565LE，帧负载上限 8 MiB。
版本检查要求 `frame_ctrl` 的 `+0x0c` 为 `0x20230218`，不匹配则在摄像头配置写入前拒绝。
SDK `Device::Open` 本身的硬件兼容性和耗时尚未上板验证。

后续经用户决定部署、确认板端依赖及取帧外设独占之后，在板端执行：

```sh
# 帮助与配置校验不调用 Device::Open，不读取/写入摄像头寄存器。
./wcis_camera_preview --help
./wcis_camera_preview camera-preview.yaml <电脑IPv4>

# 显式启动实际摄像头取帧；默认运行30秒。
./wcis_camera_preview camera-preview.yaml <电脑IPv4> --run-camera
```

不要与旧 YOLO 摄像头程序或其他控制同一寄存器/帧缓存的进程并行运行。
首次试验沿用确认兼容的现有板端环境；本轮没有产生/部署新的 BOOT。
软件编译成功不补足当前 RTL 位流的时序/硬件兼容性验收。
这里不给“替换启动分区/重启”命令，也没有自动部署脚本。

### 真实接口与错误处理

复用 `ps_app/vendor/include/pipeline/io/input/sdicamera.hpp` 的 `GenericSDICamera`：
配置与参考例程同源，PS 输出尺寸等于输入尺寸，保留完整视野；
构造函数也写厂商 PL 抽样分支配置，但本应用不创建模型/ImageMake/NPU 会话、
不执行 forward，不创建 HDMI/VPU actor，不调用任何无限等待 reset。
使用 SDK `getMemRegion("udma").malloc(..., false)` 分配一帧 DMA 缓冲。

`camera.take(chunk)`：向 `+0x50` 写 udma 地址右移3位，向 `+0x04` 发取帧请求。
本地 RTL `case/rtl/display/frame_ctrl.v` 确认 `+0x04` 清 done，
`+0x58 bit0` 是完成、`bit2` 是写 FIFO 错误，与 SDK 轮询合同一致。
新程序有界轮询 `camera.RegRead(0x58)`，错误优先于完成。
成功后才用 `chunk.read(...)` 读取一次，移动自有像素 vector 给网络线程；
网络线程不持有 DMA 缓冲，没有第二次 clone。下一次 take 不会覆盖发送中的自有像素。

取帧超时/错误/取帧中被中断：不发送无效像素，不自动 reset 或继续发下一请求。
当前 SDK 没有核实可用的 DMA 取消接口，错误分支停止网络线程后 `_Exit(3)`，
绕过用户态缓冲释放；**这不证明硬件 DMA 已停止**。再次运行前需检查外设状态，
不自动重启程序，也不能在错误后立即让另一个程序复用该外设。
正常完成/两帧之间退出则按正常生命周期释放。
寄存器访问本身仍依赖板端驱动，轮询超时不能中断已经阻塞的 SDK 寄存器调用。

RGB565LE 假设 packed R[15:11]/G[10:5]/B[4:0]。SDK 使用 CV_8UC2 的参考显示路径
支持此设计依据，但真实字节序、缓存可见性和画面颜色仍要上板用色条/现场画面验证。
配置保持原分辨率不等于保留传感器 RAW/SDI 原始采样精度；这里传的是现有 PS RGB565 帧。

## 数据流与独立迭代

```text
SDI → 现有PL取帧 → PS udma完整帧
                     → 采集适配器：自有像素、会话ID、帧号、完成时间
                     → 最新帧网络线程 → 电脑接收服务 → 原子画面/结果包 → 网页绘图

未来模型 → PS结果汇合/时间匹配 → 同帧结果包或同帧结果更新 → 网页叠加
```

| 责任 | 文件 | 后续变化 |
|---|---|---|
| 实际 SDI/SDK 采集 | `../ps_app/src/wcis_camera_preview.cpp` | 新摄像头增加适配器 |
| Linux 网络发送 | `include/wcis_raw_publisher.hpp` | 换传输/编码不改采集接口 |
| 版本化数据与同帧约束 | `raw_protocol.py`、`PROTOCOL.md` | 模型字段和版本演进 |
| 电脑接收与状态 | `server.py` | 录像/备份以后扩展，不占第一版 |
| 像素绘图、人脸框、字幕 | `dist/index.html` | 网页样式无需改板端采集 |

当前取帧应用不需要模型文件、识别人脸、音频设备或 SD 卡；首页显示“模型未接入”。
提供 `/api/results` 作为未来 CPU 汇合结果接口，**尚未接到真实模型 API**。
录音、模型加载/推理、录像、定期清理和网盘备份均未实现。
其他输入如 USB/RTSP/MIPI/HDMI 需要各自硬件、驱动和格式适配；当前只实现 SDI。

## 第一版同步边界

像素和元数据在一个二进制响应中发送，网页在同一次绘图中更新人脸信息和字幕。
结果必须携带同一 `stream_id` 和 `frame_id`；不能把上一个缓冲区编号当作永久帧号。
默认结果为空且模型未接入。新帧自动清掉上帧结果；旧会话/旧帧更新返回409。
字幕只显示覆盖该帧时间的区间，数字时间与帧号用十进制字符串避免 JS 64位精度丢失。

本版时间戳是 **PS观察到 DMA 完成的 steady_clock 微秒**，不是传感器曝光时间。
尚无真实音频时钟映射，也不能证明将来语音和视频的物理采集同步。
模型接入时 PS 汇合层须保留原帧身份并建立音频/视频时间对应关系。
当前采用低延迟最新帧策略：迟到结果如果已不是最新帧就拒绝，不缓存等待所有模型。
若后续要求完整字幕必须随对应画面出现，需要另定延迟/缓存/丢弃预算。
不是“所有模型同步工作”的现成实现。

接收超过2秒没有新帧时拒绝返回旧帧，网页隐藏画面、框和字幕。
网络线程最多一帧在发送、一帧待发送，新帧替换待发旧帧；连接/发送/应答共用
默认1000ms绝对期限。浏览器不直接给 PS 取帧线程回压。
网络失败记入 `failed`，摄像头错误不会用测试图代替。
HTTP连接成功后复用；失败时关闭连接，后续新帧重新连接，避免每帧建立短连接。
接收器保留64项连接等待队列，网页单请求轮询，没有额外逐帧状态连接。

## 性能预算待上板测量

1920 × 1080 × 2 B × 2 fps = 8,294,400 B/s，即 **66.3552 Mbit/s** 纯像素；
协议/网络开销另计。1080p30未压缩约995.328Mbit/s，不能认为千兆链路就可稳定传。
没有板端编码开销，仍有 SDK 帧读取、内存写入、内核网络复制和带宽成本。
1080p像素缓冲上界约四份：DMA、自有读取、正在发送、待发，约16.59MB；
这只是像素量估计，不是进程RSS/SDK/内核内存测量。
日志有 `read_us/sent/failed/replaced/send_us`；后续同时测CPU、RSS、网络吞吐和识别完成率。
网页 fps 是接收帧率，不能当作传感器/推理/浏览器绘图 fps 或端到端延迟。
来源标签由发送端声明，不是摄像头来源的独立硬件证明。

## 本轮验证

- AArch64 SDK 3.39 / GNU Arm 10.3.1 交叉编译及链接通过，学校隔离目录构建；
  `outputs/camera-preview/cross-build.json`、`build.log`、ELF报告保存。
  ELF仍依赖 iCraft 后端及通用库；当前板端依赖解析、帮助、配置校验、运行均未验证。
- `test_raw_stream.py`：有效像素与stride、64位ID、格式/长度限制、同帧结果、
  原子CPU结果包、字幕区间、新帧清旧结果、会话隔离、断流、真实C++网络发送、
  静默接收端超时/最新帧替换、PS轮询状态，结果为 `local-verification.json`。
- 旧JPEG回归通过，结果 `legacy-verification.json`；并不作为新真实采集的证据。
- 浏览器实际显示1920×1080测试像素、未接入模型提示、同帧测试框/字幕和断流隐藏。
  测试框/字幕来自 `browser_fixture.py` 的合成数据，**不是模型结果**。
- 本轮没有板端访问、硬件运行、录像、云上传。接收服务与临时测试发送器验证后停止。

运行本地测试示例（WSL）：

```sh
cmake -S /mnt/d/renlianshibie/fpga_project/lan_stream -B /mnt/d/renlianshibie/fpga_project/outputs/lan-stream/build -DCMAKE_BUILD_TYPE=Release
cmake --build /mnt/d/renlianshibie/fpga_project/outputs/lan-stream/build -j2
python3 /mnt/d/renlianshibie/fpga_project/lan_stream/test_raw_stream.py --sender /mnt/d/renlianshibie/fpga_project/outputs/lan-stream/build/wcis_raw_demo --wait-test /mnt/d/renlianshibie/fpga_project/outputs/lan-stream/build/wcis_capture_wait_test --out /mnt/d/renlianshibie/fpga_project/outputs/camera-preview/local-verification.json
```

学校重建：在本机运行 `python fpga_project/scripts/build_camera_preview_on_school.py`。
只上传本项目源到新隔离目录，检查现有任务，不中断他人任务、不部署板子。
浏览器绘图依据：[ImageData](https://developer.mozilla.org/en-US/docs/Web/API/ImageData)。
## 恢复前的保护阶段（历史记录）

当时板子已恢复连接；当时 BOOT 的 MD5 实测为 `0f4f00e1de0af8f70299572be622e45a`，
属于无 NPU/SDK 寄存器桥的状态导出版本。旧 SDK 预览二进制已移除执行权限，
启动脚本及重新编译的保护版都拒绝硬件取帧。不要用旧示例解除门禁。

新增 `sdi_status_sender.py` 和 `/api/device-status` 只提供真实 DDR 状态，
网页区分板子连接、摄像头信号与像素帧；诊断状态不会作为图像或模型结果。
当前真实采样没有锁定 SDI 输入，尚无画面。详见 [恢复记录](../docs/board-recovery-20261014.md)。

