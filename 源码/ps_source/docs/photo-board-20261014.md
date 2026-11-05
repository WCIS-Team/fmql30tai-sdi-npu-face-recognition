# 照片 NPU 适配与案例复核

> 此页为前次试验记录。随后已重新部署匹配的 9 月厂商 PL 基础固件，
> 教程 adder 的 16 项板端结果通过；设备实测为 4 行、2 列。
> 原先没有等待 Tensor ready 的数值不能作为有效输出。修正后，经过等价
> 重参数化和独立设备进程后，完整 NPU 照片人脸识别验收已通过。
> 最新记录见 [本次重新部署](face-redeploy-20261015.md)。

## 当前证据

学校编译、工具、下载、解包、缓存与日志均隔离在
`D:/yzd/tmp/wcis-face-32b2a267`，共享 SDK 与系统运行库没有替换。
已用 iCraft 3.39 生成 YuNet 和 MobileFaceNet 网络，交叉编译 AArch64 程序，
板端模型加载、SHA256、输入输出合同检查通过。

YuNet 已实际执行并返回 12 个有限数值输出。最新试验的 SDK 绑定记录为
112 个 NPU 算子，首次加载与前向、导出合计约 516.8 ms；这不是稳态帧率。
同一输入的 CPU 检测为 1 张脸，当前 NPU 输出解码为 1396 个框，**未通过识别验收**。
MobileFaceNet 已编译，但完整板端特征与识别仍未验收。

此前上层等待超时不能当作硬件没有返回的证据：原始文件和算子回调显示已返回，
协议读取已修正为能处理 SDK ANSI 输出，另保存完整 stdout。
置信度偏差在移出 Sigmoid 后仍存在，因此不能把根因认定为 Sigmoid。

## 编译修复

- 服务器系统 CRT 14.23 与当前工具不兼容；在任务私有 bin 中复用 14.50 CRT，
  解决访问异常，没有改系统目录。
- 指令生成器缺少 `PReLUNode` 配置项。模型使用等价的
  `ReLU(x) - alpha * ReLU(-x)` 改写，11 份 CPU 输入逐份输出一致。
- YuNet 导出末端激活前输出，由 PS 做 Sigmoid；11 份 CPU 输入与原模型最大误差
  小于 1.4e-7，但该变更没有解决板端置信度偏差。

## 教程与最新信息来源

已读取并检查 `C:/Users/anxianji/Downloads/20260916/30TAI使用教程.pdf`
全部 11 页文字和第 9、10 页图示。第 9～11 页要求在交叉环境编译 ZG 版案例，
提供 adder_demo、无 SDI 时 VTC 灰度图和接入 SDI 后 YOLOv5 的验证方式；
没有提供 YuNet 或 MobileFaceNet 部署步骤。

adder_demo 源码期望在 SDK RegRegion 地址 `0x400C00C0` 读到 `0x20230628`。
直接物理地址与同源 SDK 接口均读回 `0xA0AAAAAA`，因此没有触发加法运算。
本地 RTL 的 RFU 响应常量也包含该值，但本地 RTL 不等于现装位流读回，
不能据此断言具体模块缺失或板卡损坏。需核对教程案例、地址映射和现装固件。
此前厂商 VTC 测试图的电脑接收证据见 board-factory-restore-20261014.md，
不代替本轮 adder 或完整 NPU 验收。

已在后台从 Firefox 复用仅该站点的会话，成功读取
`http://10.101.54.192:18080/` 最新返回的项目首页。
页面 updated-at 为 `2026-10-13T16:11:33.181Z`，描述 NPU 先部署、CPU 基线、
逐项下沉 FPGA 的总体工程策略；它是规划信息，不是当前板端通过证明。
未保存或输出认证凭证。

## 板卡状态

本轮没有更换 BOOT、引脚或时钟。为排除旧进程和残留状态正常重启一次，
当前启动号为 `ffd3524b-642b-47a9-9a74-a83f0d51d991`。
NPU 试验进程均已退出，SSH 正常。原厂摄像头程序为独占 NPU 而暂停。
失败记录与当前启动绑定，不自动重复同一失败试验。

## 主要记录

- outputs/photo-board-20261014/tutorial-adder-check.json
- outputs/photo-board-20261014/tutorial-sdk-adder-inspection.json
- outputs/photo-board-20261014/board-staged-release.json
- outputs/photo-board-20261014/board-runner-stdout.log
- outputs/photo-board-20261014/logits-run-statistics.json
- outputs/photo-board-20261014/recovered-yunet/comparison.json
- outputs/photo-board-20261014/attempt-01 与 attempt-02：前次记录
- outputs/photo-board-20261014/models：模型与 CPU 等价性对照
