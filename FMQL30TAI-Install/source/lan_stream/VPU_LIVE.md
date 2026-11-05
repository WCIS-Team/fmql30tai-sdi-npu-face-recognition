# SDI → VPU JPEG → 内网直播

2026-10-21最新[独立采集线程](../docs/face-capture-worker-20261021.md)已部署到8091/8092：正式空闲29.84fps、混合识别29.07fps。沿用已有位流及VPU JPEG，唯一iCraft SDK所有者和识别源帧保留；采集线程独立推进，并补充PL输出可见性验收。不是每帧模型识别，也不是PL自主环形DMA。以下为前阶段记录。

2026-10-21后续[持续预览与提前取帧](../docs/face-stream-smooth-20261021.md)已经正式部署：8091同源MJPEG主视频与检测小窗分离，8092同样读取新所有者；预分配两块PS UDMA缓冲，提前请求下一帧。正式空闲推流29.97fps，连续摄像头识别短测约18.28fps；不是全程30fps或每帧模型识别。没有重烧位流，旧独立camera服务仍禁用；以下5fps状态和目录属于前阶段记录。

2026-10-21当前入口及链路见 [单所有者接入](../docs/face-camera-owner-20261021.md)：8091正式服务同时负责SDI采集、FAC1/NPU识别及VPU编码，8092读取同一最新帧。识别使用原始RGB565而非JPEG解码，识别期间预览继续更新；旧独立采集服务已停止并禁用。候选单人请求中位约0.59秒，正式无人脸约0.43秒；60帧eMMC短录像逐帧读回解码通过，未新增常驻录像功能。当前启动`8f360a28-0740-4d81-a13f-379a20faf47e`，BOOT仍`f6da96…`。输出约5fps，经PS网口，PAD仍未评估。**以下描述保留前阶段状态，旧服务启停/回退说明不代表当前正式配置。**

最新延迟及硬件交接说明见 [识别延迟优化](../docs/face-latency-20261020.md)：8091桌面无人脸暖请求中位约1.06秒，采集程序常驻但推理期间仍暂停；旧的每请求停止/启动服务描述保留为前阶段记录。


人脸检测与画面同页入口：`http://192.168.1.113:8091/`，默认自动检测，支持暂停/单次检测/实时预览切换；结果对应同一JPEG帧，约2–3秒更新，活体防伪未评估。详见 [画面叠加记录](../docs/face-live-overlay-20261020.md)。8092仍为独立预览入口。


当前地址：`http://192.168.1.113:8092/`。页面显示当前输入来源和状态；`vtc` 是板内测试图，`camera` 是真实 SDI 输入，两者不会互相代替。

2026-10-20 下午先用原始位流确认摄像头正常，随后将项目的SDI参考输入修正到完整版CLK1（U6/U5），修正版已经上板。真实摄像头30帧采集及30帧VPU JPEG编码通过，本机Windows和102主机各验收5个不同帧号的MJPEG；原有FAC1预处理8组88次金标回归通过，人员库6个文件哈希保持一致。输出960×540、上限5fps，不等同于1080p30全速推流。

当前使用项目修正版BOOT `f6da96abbc0144ce5a48f4fa85aed6dab65067211b8932e8f4e4db87d5110297`，晚间软件接入后的启动身份 `6d292f53-4a5d-4600-bbcd-28ea2654a6c0`。照片服务已恢复，识别请求先暂停采集、排空在途帧，完成后自动恢复；并非同时访问SDK或不间断录像。摄像头单帧识别已经过桌面无人脸测试，有人现场身份与活体防伪仍待验收。当前软件和使用说明见 `../docs/face-camera-ready-20261020.md`，位流修正见 `../docs/sdi-refclk-fix-20261020.md`。

## 实现

- 厂商 `SDICamera` 从1920×1080输入整数抽样到960×540 RGB565，PS按 `repos/vpu-live/src/hdmi_display_actor.hpp` 的方式转换为NV12。
- `/dev/video0` VPU硬编JPEG，质量80，2缓冲，采集频率上限5fps。实际驱动协商为NV12双平面（Y=518400B、UV=259200B）；入队前按驱动缓冲长度分配并校验边界。
- C++输出缓冲在归还驱动之前复制，JPEG和帧身份一起原子发布。只保留最新帧，不做录像。
- Python服务器不访问硬件。帧超过2秒、采集退出、来源/启动/会话改变时停止显示缓存画面；最多4个流连接。
- 项目位流的真实输入模式先读SDI2快照，只在新鲜、锁定且1920×1080时发取帧请求。失锁时等待；已发出的取帧若失败则隔离，不自动重试或复位。
- 原始位流没有SDI2。启动器在核对当前启动的原始BOOT后专门提供兼容标记，允许有界的实际采帧；不把缺少监测块当成失锁，也不允许项目位流沿用该例外。失败依旧退出隔离。

## 接口

| 地址 | 内容 |
|---|---|
| `/` | 直播页面与输入状态 |
| `/api/status` | JSON状态；`ready` 表示当前存在可用的新帧 |
| `/snapshot.jpg` | 最新JPEG；没有新帧时返回503 |
| `/stream.mjpg` | MJPEG流；不接收自定义UDP或裸H.264 |

输出经过PS管理网口 eth0；PL网口的MAC/RGMII传输逻辑尚未实现。

## 程序与部署

- 编译目标：`ps_app/CMakeLists.txt` 的 `wcis_sdi_vpu_live`。按项目约定在学校服务器交叉编译，不在板子编译。
- 当前服务根：`/root/wcis-face/candidates/face-camera-ready-20261020/live`。采集程序加入停止后排空在途DMA/VPU输出，在学校服务器交叉编译，SHA256=`937d71165665c7b285a1481050a9376bea24b086cd254404bd7169203bab1b2b`，未在板端编译。
- `wcis-sdi-vpu-view.service`：HTTP服务，监听8092，已启用开机启动。当前绑定所有接口以容忍原始位流启动时网络地址尚未设置。
- `wcis-sdi-camera-live.service`：当前真实摄像头采集服务，已启用；启动前只读核验BOOT、刷新本次启动身份、恢复既有PS网口地址。没有新帧重试/失败SDK重启策略，停止先排空，超时不强杀设备所有者。
- `wcis-sdi-refclk-fix-20261020.service`：上一轮验收服务，当前停止且禁用，保留为软件回退。
- `wcis-factory-vpu-live-20261020.service`：原始位流的备用直播服务，当前停止且禁用；只在回退到原始BOOT后恢复。
- `wcis-sdi-vpu-capture.service`：之前的项目位流采集服务，当前停止且未启用，不与新服务并行。
- `scripts/run_sdi_vpu_capture.py` 负责当前启动身份、批准的BOOT、二进制哈希、硬件锁与VPU占用检查。它需要该次启动的 `boot-proof.json`，重启后不能沿用旧检查记录。
- `wcis-face-photo.service`：已恢复并启用，页面 `http://192.168.1.113:8091/`。照片模型进程只在CPU驻留，每次硬件工作结束关闭SDK；请求级互斥负责暂停采集、验证本次会话退出0和硬件锁释放，再运行PL/NPU，最后恢复新camera会话。当前完整BOOT与隔离标记不符时拒绝硬件准入。独立测试库验证登记/识别/删除，正式人员库6个文件保持不变。
- 当前软件回退为 `systemctl start wcis-face-camera-ready-recover.service`，恢复本轮之前的预览软件配置并重启，BOOT不变。试验计时器在全部检查通过后已停止/禁用；软件回退依赖Linux可运行。上一轮 `wcis-sdi-refclk-fix-20261020-recover.service` 是恢复原始BOOT的旧入口，不是本轮软件回退。

## 证据

当前修正版构建、BOOT校验、摄像头30帧、FAC1回归、人员库和双主机直播证据在 `D:/yzd/tmp/sdi-refclk-fix-20261020`：`timing-gate.json`、`package-gate.json`、`candidate-proof.json`、`finite-result.json`、`fac1-result.json`、`gallery-check.json`、`windows-stream.json`、`gateway-stream.json`、`accepted.json`、`camera-live.jpg`。原始位流证据保留在 `D:/yzd/tmp/factory-vpu-20261020` 和 `D:/yzd/tmp/factory-vpu-live-20261020`，早期VTC证据在 `D:/yzd/tmp/sdi-vpu-live-20261020`，复用采集程序构建在 `D:/yzd/tmp/sdi-vpu-factory-20261020`。

晚间照片与摄像头交接证据在 `D:/yzd/tmp/face-camera-ready-20261020`：`build-receipt.json`、`http-verification.json`、`enroll-verification.json`、`accepted.json`。当前 `POST http://192.168.1.113:8091/api/recognize-camera` 接受空请求体，返回绑定当前JPEG与采集会话的单次识别结果；使用的是压缩后的960×540图像，明确未评估PAD，不作权限放行。
