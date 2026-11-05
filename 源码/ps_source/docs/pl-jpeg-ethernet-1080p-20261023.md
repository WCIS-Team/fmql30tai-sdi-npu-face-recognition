# 1920×1080 PL JPEG 网口预览（2026-10-23）

## 目标与当前边界

用户选择保持摄像头完整 1920×1080 视野：SDI → PL 流式 JPEG → 独立 PL 千兆网口 → 内网接收机 → 浏览器。输入为 1080p30；30 fps 是目标，不是已完成板测的结论。已有识别支路保留原始像素；新预览不占用 NPU 的 DDR 主接口，不改变原 NPU 1 GHz 时钟。

本记录依据下列源码和任务产物编写。截至本条记录，新增模块已完成分项 RTL 仿真和独立综合，**尚未接入整板、生成新 BOOT 或部署新位流**；当前板卡仍运行原 f6 镜像。现有连续 PS/VPU 预览也尚未切换，因此尚无实际 CPU/VPU 节省比例。

## 实现

- `rtl/wcis_sdi_jpeg_stream.v`：接收完整 SDI RGB，8192 深度异步像素 FIFO，忙时跳过整帧。逐行/逐帧检查 1920×1080 几何和像素计数；未通过验证不发送有效 JPEG 结束标记。超时、溢出或输入异常中止当前帧，允许下一帧恢复。
- `rtl/wcis_jpeg_udp_packetizer.v`：WJP1 分片，每包最多 1400 字节 JPEG、40 字节元数据；会话号、帧号、偏移、末帧总长度、尺寸和 CRC32。流控期间输出保持，异常帧发送中止标记。
- `rtl/wcis_jpeg_network.v`：复用 alexforencich/verilog-ethernet 的 MAC、ARP、IPv4、UDP、RGMII/FIFO，固定提交 `77320a9471d19c7dd383914bc049e02d9f4f1ffb`；41 个文件和许可列在 `rtl/vendor/verilog_ethernet/sources.json`，未改上游文件。选择该版本考虑旧 Vivado 与 Verilog 兼容性；上游已提示后继 Taxi，本任务未引入后继项目的代码或许可。
- `rtl/wcis_pl_jpeg_preview.v`：独立 MMCM 产生 JPEG/网络逻辑 150 MHz、发送 125 MHz/+90°；配置以握手邮箱原子跨时钟传递。
- `rtl/wcis_preview_registers.v`、`wcis_mdio_clause22.v`、`wcis_preview_csr_router.v`：NTP1 管理页 0x2200，复位默认关闭、PHY 保持复位；使能前检查配置，运行时拒绝修改。旧 FAC1/JPG1 读响应归属在背压期间保持。
- `npu_photo/src/pl_net_config.cpp`：只读写已知寄存器、无模型编译/像素搬运；验证当前启动证明、继承 NPU/摄像头排他锁和 NTP1 魔数，识别 YT8521 PHY 后才配置。保留电压/模式 strap，不盲写其他 PHY。
- `lan_stream/pl_jpeg_protocol.py`、`receive_pl_jpeg.py`：按来源 IP/端口和会话号接收，最多一个拼接中帧和一个最新帧；超时、丢包、冲突分片不展示，不积压历史帧。复用现有 MJPEG 页面，不重新编码 JPEG。CRC 是传输校验，不是身份认证；可信内网与来源固定不等于抵御同网段伪造。

## 已完成的验证

证据目录：`D:/yzd/tmp/pl-jpeg-ethernet-1080p-20261023`。

1. `transport-test/summary.json`：7 个 RTL 分片边界用例，随机背压，长度、CRC、输出稳定性、中止恢复；接收端乱序/重复/丢包、错误 CRC、会话、尺寸、ID 回绕、过期帧和冲突包检查通过。
2. `network-test/summary.json`：实际 MAC/RGMII 管脚级仿真，坏 FCS 丢弃、有效 ARP 响应及完整 WJP1 UDP 发包通过；独立校验 Ethernet FCS、IPv4/UDP 校验和与精确载荷。
3. `source-test/summary.json`：真实 JPEG RTL 与采集桥，随机输出背压，错误行宽中止后下一帧恢复通过；JPEG 解码及独立软件 DCT 系数对照通过。
4. `results-gradient.log`、`results-noise.log`、6 个 `rtl-*.jpg`：真实 RTL 1920×1080 仿真，150 MHz 编码域、74.25 MHz 像素域、2200×1125 输入时序；渐变/噪声各 3 帧，拒绝 0 帧，帧间隔约 30 fps，全部解码为 1920×1080。此实验尚未把整条 MAC 网络背压与真实 SDI/PHY 一起验收。噪声约 1.8 MB/帧，30 fps 约 432 Mbps JPEG 净流量，说明不能用普通画面的几十 Mbps 当最坏带宽。
5. `mdio-test.log`：写寄存器、上升沿后延迟 20/62 ns 的 PHY 读模型、缺失 PHY 的 turnaround 拒绝通过。手册 Table 139 的 t6 最大值是 **20 ns**，62 是该页印刷页码，不是参数；62 ns 只作为额外仿真裕量。主机改为双级同步后在高电平中间采样。
6. `net-admin-build.log` 和 `net-admin-receipt.json`（具体文件名以目录为准）：学校服务器隔离工作目录完成 AArch64 管理工具交叉编译；未在板上执行新 NTP1 访问。
7. `preview-ooc-*.rpt`：独立综合用于预算资源与检查逻辑，不是整板时序签核。增加 CSR 路由和 MDIO 同步后须重新综合更新结果。旧 r3 建立时间 WNS +0.366 ns，未布线保持时间 WHS −0.147 ns；不能将此数当最终通过。

## 官方硬件依据与待验收项

板卡手册 `D:/xiangmuwendang/WCIS-FPAI/wiki/PS/board_extract/41_manual_full_extracted.txt` 给出 PL 网口管脚：TX_CLK AD23、TX_CTL AD26、TXD[0:3] AF24/AF25/AA24/AB24；RX_CLK AC23、RX_CTL AA25、RXD[0:3] AB26/AC26/AE25/AE26；MDC AE22、MDIO AF22、RESET AA13。工具查询显示数据/时钟/管理口在 bank13，与已有 eMMC 的 LVCMOS18 一致；RESET 在 bank12。需按这些新增网口映射建约束，不改已有信号管脚。

Motorcomm YT8521S 手册（制造商文档，由 LCSC 分发）：`https://datasheet.lcsc.com/datasheet/pdf/f403627dbc667ce1e0f863a440de082f.pdf?productCode=C2685354`。本地 `YT8521S-datasheet.pdf` 与第 72/73 页渲染图已核对；RGMII 内延迟方式的最小输入/输出建立和保持时间均 1 ns。PHY 接收时钟采用约 1.95 ns 内延迟、发送使用 MAC +90°，不能两端重复加发送延迟。PCB 时钟/数据偏差尚无实测值，约束中如使用预算必须明确是设计假设。

下一步是加入整板并验收约束、资源、布局布线及现有 DDR/NPU/SDI 保持情况。新视频链路有图后，还需切换连续 PS/VPU 预览并对照 CPU、帧率、延迟、丢包与识别同帧绑定；当前不承诺收益百分比。原镜像已有厂商 1 GHz 最小周期违例，本任务不通过改库、宽泛假路径或降 NPU 频率掩盖它，也不将原镜像视作完整生产时序签核。

板端切换必须先完成候选门槛、完整备份及可用回滚；用户已有取出启动 SD 卡恢复的方式。本任务截至记录时未动启动分区。
