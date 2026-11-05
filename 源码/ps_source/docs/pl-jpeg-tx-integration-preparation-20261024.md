# PL JPEG 单向发送整合准备（2026-10-24）

## 已完成的改动

依据独立发送模块的通过结果，将 `wcis_pl_jpeg_preview.v` 改为 SDI 原图分支 → 实际 JPEG 编码器 → WJP1 分片 → 单向 UDP/IPv4/MAC → 共用 250/125 MHz 时钟的六个 OSERDESE2。默认尺寸仍为 1920×1080。现役原图识别及 FAC1/JPG1 路径没有改动；没有操作真实 PHY、板端服务或 BOOT。

原预览 PLL 的 125 MHz +90° 输出改为同相 250 MHz，150 MHz 编码时钟及 125 MHz MAC 时钟参数保留。移除预览 RX/ARP 路径；以新魔数 NTP2（`0x4e545032`）区分旧 NTP1。配置页新增 `0x5c=7` 能力字，以及 `0x60/0x64` 的显式 48 位下一跳 MAC。旧网关/子网字段未被复用为 MAC。运行期间配置冻结，复位后关闭，零地址或组播下一跳不能启用；配置通过 224 位握手邮箱原子跨域。

准备脚本在 `D:/yzd/tmp/pl-jpeg-tx-integration-20261024/case` 生成候选，保留来源顶层 SHA256 与补丁，不修改原案例。新增 `fmql30tai_pl_ethernet_tx.xdc` 保持手册中的 TX/MDIO/reset 球位与电平，使用已验证的正主边沿加统一 2 ns 偏移描述转发时钟；保留 +1.2/−1.2 ns 双边沿接收要求和 0.100 ns 不确定度。PCB 0.2 ns 偏差仍是设计预算，不是实测。

## 验证及修正

- `control-final/summary.json`：真实 CSR/router/邮箱/顶层控制通过 12 个异步复位相位，以及停用重启、取消尚在传输的配置、NTP2 标识/能力读取、无效下一跳拒绝、运行中地址冻结。时钟、JPEG 与网口在此台架中是明确标注的 stub，不能证明物理时钟或吞吐。
- `pipeline-native-fixed/summary.json`：Vivado 2018.3 原生 `unisims_ver/secureip` 串化器模型，真实采集桥、JPEG、分片和 MAC 串联，以 256×64 输入 3 帧，收到 3 张 JPEG、9 个 UDP，拒帧和中止均为 0。独立核对 Ethernet FCS、IPv4/UDP 校验和、完整像素来源、JPEG 解码和尺寸；梯度像素平均绝对误差约 3.486。该结果不等于 1080p 实拍或整板帧率。
- 原生仿真首次在时间 0 误触发截止：旧台架使用超过 32 位的整数延时常量，XSim 2018.3 处理为零。改为实数时间常量后通过，失败日志保留于 `pipeline-native/`；没有替换厂商串化器模型。
- `school-manager/receipt.json`：使用受保护的学校服务器连接，重新检查工具与编译进程，在独立 `D:/yzd/tmp/wcis-pl-net-20261024-3dc4aa8925` 交叉编译 NTP2 配置程序成功，ELF 为 AArch64。没有编译模型、访问板子或将程序部署。

管理工具只接受 NTP2/能力字/1080p 几何一致的固件；必须给出有效下一跳 MAC。依据本地 YT8521S 手册 Table 19、49，确认千兆、全双工、协商完成及链路已起，再启用。仅清除 PHY 追加的千兆 TX 延迟和 TX 反相，保留 RX 延迟及电压/模式 strap。硬件状态字里的速度位表示固定 MAC 模式，不能作为物理协商结果。

## 未完成及边界

2026-10-24 的综合在输出综合网表检查点前被中断。日志中的“0 errors”位于 RTL 综合结束阶段，此后还需读取 AI_Mate EDIF 并写出检查点；任务目录没有完整顶层 DCP，不能记为整板综合完成。没有进行整板布局布线、生成 bit/BOOT 或上板。

固定千兆发送候选需要真实千兆接收链路，先前查到的 D12 百兆口不能满足该条件。没有 ARP 应答或自动速率切换；移动网络、下一跳变化或链路重新协商后，要关闭并重新确认配置。后续须验证整板时序/CDC/资源、原引脚和 NPU/DDR 时钟保持、1080p 实拍、长时丢包及网页展示性能。

## 本地依据

- `rtl/wcis_pl_jpeg_preview.v`、`wcis_preview_registers.v`、`wcis_jpeg_network_tx.v`、`wcis_rgmii_tx_serdes.v`；`npu_photo/src/pl_net_config.cpp`。
- `scripts/prepare_pl_jpeg_preview.py`、`build_pl_jpeg_preview.tcl`、`implement_pl_jpeg_preview.tcl`、`gate_pl_preview_placement.tcl`、`verify_pl_preview_control.py`、`verify_pl_preview_tx_pipeline.py`、`native_xilinx_sim.py`。
- 任务中的 `preview-staging.json`、`preview-top.patch`、上述仿真/交叉编译结果及 `synthesis-driver.log`。
- 前置独立实现记录：`docs/pl-ethernet-shared-clock-validation-20261024.md`；PHY 来源：`D:/yzd/tmp/pl-jpeg-ethernet-1080p-20261023/YT8521S-datasheet.txt`，其 Table 19、49 对应延迟控制与状态位。

工作日期依据为 2026-10-24 的改动和日志；后续恢复工作另记 2026-10-25。本记录同步到 `D:/bigfuture/竞赛/记录/2026-10-24.md`，保留当日其他记录及原文件。
