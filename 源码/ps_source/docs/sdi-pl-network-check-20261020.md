# SDI 摄像头与 PL 网口接线检查（2026-10-20）

## 结果

用户确认摄像头输出为 1080p30 SDI，PL 网线另一端接路由器／交换机。本轮远程实测没有取得摄像头帧，也没有跑通 PL 网口视频输出。

- 板端 SSH 正常，PS 管理网口 eth0 为 100 Mbps 全双工，carrier=1。这个结果不代表 PL 网口通过。
- 当前仅有 lo/can0/eth0/sit0；第二个 GMAC 设备树节点 disabled。结合本次启动对应实现的顶层源码，PL 外部 RGMII 数据口未接入，不能通过插线自动传视频。仅凭缺少 eth1 本身不足以排除独立 PL MAC，结论同时依据顶层源码。
- SDI2 诊断接口确实存在，magic=0x53444932、version=1。三次一致快照的状态均为 27（seen/fresh/ref_stable/gt_reset_released 为真，pending 为假），接收时钟计数增长。
- 三次 rx_flags 均为 122（0x7a），lock 位为 0；真实输入的已锁定帧/行/有效像素计数均为 0，测得宽高为 0。诊断点在 VTC/采集开关之前，不是因 image_enable=0 而简单读到零。
- 因未锁定且未测得 1920×1080，不发送采集请求，不分配摄像头 DMA 缓冲区，不重试或复位。没有输出图片；不能称为 SDI 采集通过。
- 检查期间暂停照片服务以独占 SDK，检查后已恢复，health=ready、gallery_storage_ready=true。

## 启动与接口核实

本次 boot_id=`d4c98f4d-da2b-4bb8-bd98-66a6dcfdde6c`，与上次验收启动不同；没有沿用旧启动作为本次实测。
只读挂载 SD 分区后核对 BOOT.bin SHA256 为 `f48397d08b1ccb1c950adafcebe5e36678154e73fa1d19792150aa5ddccd8ad1`，与已验收缓存优化版本一致；DTB/uEnv 哈希也一致。
`/download.bit` 不存在，`/root/live.disabled` 存在。此前隔离标记属于其他 boot_id，不算本次故障。
服务绑定 192.168.1.113:8091，访问 127.0.0.1 会拒绝连接；随后用实际绑定地址核实 ready。`camera_input=false` 是服务能力声明，不用于判断 SDI 电缆状态。

## 工具实现和构建

新增 `ps_app/src/wcis_camera_single_frame.cpp` 和对应 CMake 目标，复用厂商 SDICamera、SDK 以及已有 SDI2 一致快照读取器。
工具检查当前启动 ID、继承的 NPU/摄像头硬件锁和 frame_ctrl 版本；默认检查不构造摄像头、不写采集寄存器。单帧模式另要求输入快照 fresh/lock/1920×1080，限定一次、2 秒完成等待，关闭 VTC，失败后不自动重试或回收可能仍活动的 DMA 缓冲区。
启动文件、二进制哈希及服务所有权由维护启动器先核实。它不是可以绕过部署核实的通用摄像头入口。

学校服务器重新检查共享工具与编译任务后，在独立目录 `D:/yzd/tmp/wcis-camera-preview-sdi-bb3bddba` 构建 AArch64 工具，共享 SDK 只读使用。首次编译链接成功，但 readelf 使用 MSYS 路径且禁用参数转换，导致后处理失败；随后完成增量构建并取回二进制。没有静默使用本地交叉编译。
二进制 SHA256=`32e308a089e562d324a49d562e7154edc6f0029cc52f20a12c06c14b42c20304`。
实际板测只执行 `--inspect`，三次 SDI2 快照读取成功，进程返回 0。单帧采集分支尚未板测；未修改位流、启动文件、跳线、引脚或人员库。

## 差异、未完成与下一步

历史 `sdi-diagnostics-20261014.md` 说明当时厂商位流没有 SDI2，不能推广到本轮优化位流。本轮结合 JPEG 基线源码与板端 magic 已确认存在该接口。补充资料中的“eMMC 不可用／缺 SDI 工程”等为早期记录，不能覆盖当前 eMMC 服务和 SDI2 实测。
当前失锁的原因尚未定位，可能涉及输入端口、SDI 输出制式、线缆、GT 路由/时钟或接收器配置；接收时钟增长并不证明 SDI 数据正确。不能由本次结果认定摄像头损坏。
先核对 SDI OUT 到当前实现的 XS1/SDI0 输入和摄像头 HD-SDI 输出；物理条件正确后再读诊断，锁定后才做单帧验收。PL 网口需另行接入 MAC/PHY/RGMII 和传输逻辑，本次没有实施。

## 证据与本地来源

- 本轮输出：`D:/yzd/tmp/sdi-pl-net-check-20261020/` 下 `inventory.json`、`boot-inventory.json`、`inspection.json`、`build-receipt.json`、`rebuild.log`。
- 输入位流来源：`D:/yzd/tmp/face-cache-resume-20261020/build-input-proof.json`、`accepted.json`。
- 当前实现基线：`D:/yzd/tmp/pl-jpeg-board-20261016/case/rtl/ai7030_edif_top.v`、`rtl/display/frame_ctrl.v`、`rtl/wcis/wcis_sdi_monitor.v`。
- 项目文件：`ps_app/example_include/wcis_sdi_diagnostics.hpp`、`docs/sdi-diagnostics-20261014.md`、`ps_app/vendor/include/pipeline/io/input/sdicamera.hpp`。
- 补充资料：`D:/xiangmuwendang/WCIS-FPAI/wiki/todo/dev/板子（除芯片）.md`，后台读取本地文件，没有使用前台浏览器。
