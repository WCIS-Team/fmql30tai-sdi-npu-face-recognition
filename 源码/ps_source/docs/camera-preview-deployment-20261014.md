# 摄像头预览部署与首次硬件试验

**最新状态**：用户已明确授权恢复厂商 BOOT，切换及重启完成，控制接口已恢复。
后半段通路通过硬件测试源验证，真实摄像头仍未收到帧；详见
[厂商恢复与通路验证](board-factory-restore-20261014.md)。后文无响应/未替换 BOOT 的
描述是首次事故及恢复准备阶段，不是最新状态。

**后续状态**：板端连接已恢复，BOOT 身份已实测核对，旧程序已禁止启动 SDK，
网页可接收真实信号诊断；摄像头仍未锁定、实际像素帧仍为 0。详见
[恢复记录](board-recovery-20261014.md)。以下是首次失败试验的历史记录。

## 结果

部署完成，实际取帧验收未通过。没有收到任何摄像头像素帧。
用户授权部署并确认摄像头已通电、接好SDI；用户描述为魔克仕HD-SDI 1080P、
2.8–12mm镜头。镜头焦距不决定输出制式；实际SDI锁定/帧率仍未测得。

板端独立目录：
`/root/wcis-camera-preview/releases/20261013T161109Z-c3a75cda228e`（UTC命名）。
包含wcis_camera_preview、camera-preview.yaml、run-preview.sh与RELEASE.json。
二进制SHA256：`c3a75cda228e26e9c6da9ddda1b5266254dcde5f0e1a9d8b588c9907e7e51b5b`。

## 已确认事实

- 部署前板子192.168.1.113可SSH，aarch64，约993MiB RAM，约750MiB可用；
  没有视觉应用运行，wcis-heartbeat.service active，最近心跳每10秒更新。
- 目录/上传成功，远端二进制SHA一致；ldd没有not found；--help和不打开设备的配置校验返回0。
- 电脑192.168.1.106:8088接收服务正常，板端python3访问其/api/status返回0帧状态。
- 首次且仅一次运行30秒配置、外层timeout40秒/TERM后3秒KILL，没有模型、录像、
  新BOOT、启动分区修改或自动重启。
- 日志最后一条为SDK“Device initialization successful, version information:”。
  SSH执行通道50秒未完成，读取TimeoutError；没有frame/read_us/sent的应用日志。
- 随后只读SSH连接超时，ping 192.168.1.113超时，TCP22连接3秒超时。
  电脑访问接收端仍正常，frames_received=0；本机ping网关192.168.1.1成功。
  本机邻居表将板端IP记为Unreachable，属于路径/响应证据，不等于板上CPU状态证明。
- 用户报告板子电源灯和网口灯正常。本机没有枚举到调试串口。

## 未确认

无法取得试验后的心跳/内核日志/进程状态，不能确认硬件进程已退出。
外层timeout不保证能中断内核/AXI/不可中断等待；退出码没有收到。
日志定位只到SDK初始化附近，不能根据一条版本banner证明Device::Open已完整返回，
也不能排除其后第一个寄存器读取。没有证明相机take已经执行。
当前不能确认OOM、驱动锁死、AXI读阻塞、位流兼容性或网络故障中的某一种根因。
不能把失败归因于镜头、网页绘图、JPEG编码、模型推理或新RTL：本次没有JPEG/模型，
没有替换原位流，接收端仍正常。

## 后续

2026-10-14资料复核发现仓库已记录“不含NPU位流＋axi设备初始化”导致PS无响应的故障。
它与本次日志高度匹配；实际BOOT校验仍待恢复连接后确认。
详见 [板卡资料复核](board-hardware-review-20261014.md)。当前SDK预览程序不能继续视为
兼容现装纯视频位流的候选，必须先确认寄存器桥与缓冲布局。

暂停再次访问该SDK硬件入口。需要用户先保留可获得的串口输出，恢复板端连接后：
提取该启动心跳/内核记录，确认旧进程/外设状态，再增加阶段日志定位设备初始化与
首个寄存器访问。不得直接反复启动当前脚本或自动复位；若需替代采集入口，先核实
实际驱动、DMA缓冲和取消/完成接口，不能假设绕开SDK就一定安全或可用。

证据：outputs/camera-preview/board-preflight.json、board-deployment.json、
board-receiver-check.json、board-capture.log、board-trial.json、delivery.json。
电脑接收网页仍开着等待真实帧，没有用演示图替代；没有修改防火墙。
