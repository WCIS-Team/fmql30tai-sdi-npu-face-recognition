# PL JPEG 分片同步 RAM 优化（2026-10-25）

## 问题与范围

继续 [整板发送链路检查](pl-jpeg-tx-integration-20261025.md)。上一候选完成完整布线及一次路由后优化，仍因分片 `count_reg[0]` 到 LUT RAM 写地址的高扇出路径失败，建立 −0.590 ns；工具明确不支持当前阶段的强制寄存器复制，因此先改存储结构并验证，不继续重复无目标的布线。

本轮独立目录为 `D:/yzd/tmp/pl-jpeg-bram-chunk-20261025`。仅改 ModelBackend/RTL 及验证/候选准备脚本，没有修改前端、业务编排、人员模型或门锁权限逻辑。保留 1920×1080、150 MHz JPEG 逻辑、同 PLL 250/125 MHz 发送及原 NPU 参数。未访问板子、生成 bit/BOOT 或更换镜像。

## 实现

`rtl/wcis_jpeg_udp_packetizer.v` 原为异步读的字节数组，由同一个 `count` 驱动大量 LUT RAM 写地址。现复用项目已固定 MIT 版本的 `axis_fifo`，使用同步读 RAM 和一级读流水。默认 1,400 字节分片采用 2,048 深度的 RAM，应用层 40 字节头的发送时间覆盖预取延迟；载荷 ready/valid、UDP 长度、WJP1 字段、CRC、帧号及分辨率不变。

只在 COLLECT 处理未发送的残片时复位该 FIFO。报文头已被接收或载荷正在发送时，中止只登记待取消，当前 UDP 必须按已广告长度完成，再发空 ABORT 报文，避免截断网络报文。缓冲按分片复用，新增存储不是视频整帧队列。

候选准备脚本新增显式 `--buffer-camera-clock`，只在独立副本为原摄像头选择逻辑添加 BUFG；不改原厂文件，不改变选择方程，也不宣称异步切换已无毛刺。脚本拒绝给已归档的旧候选直接补改或不匹配的缓存配置。整板将使用上一轮已优化 DCP 作布局引导，f6 仍是独立的引脚/NPU 核对基准。

## 已完成验证

- `transport-inflight-abort/summary.json`：7 种载荷长度 1、1,399、1,400、1,401、2,800、2,801、140,093 字节，随机背压，逐报文独立检查 WJP1 字段、长度、CRC 及载荷；每组 4 帧正常完成、3 帧取消。补测报文头广告后中止、载荷中途中止，以及取消后的下一帧不混入旧字节。140,093 字节参考 JPEG 为 1920×1080，可重组、解码；此项是注入参考 JPEG 的传输验证。
- `control/summary.json`：12 个复位相位的 CSR/邮箱/顶层控制回归通过；PLL/图像源/PHY 的控制台架替身边界保留。
- `pipeline-native/summary.json`：真实采集桥、JPEG RTL、新分片 FIFO、WJP1、UDP/MAC 与原生 Xilinx 串化器模型串联，收到 3 张 256×64 JPEG、9 个 UDP，解码/校验通过。未将它表述为新链路已做过 1080p 整链仿真。
- `chunk-synthesis.log` 与 `chunk-ram-topology.txt`：独立 OOC 综合确认为 1 个 RAMB18E1（0.5 BRAM tile）、433 LUT、404 寄存器、0 DSP；计数器最大扇出 12。原整板对应最差一位为 365 负载；OOC 数字不是整板资源、布线时序或板端帧率。

`functional-admission.json` 核对上述源散列。未改的网络发送器 17 报文原生模型测试重新核对源散列后复用，未冒充新分片器测试。PS 配置工具 CPP 和 AArch64 二进制亦与学校服务器原构建收据逐项匹配后复用，没有在板上或本机重新编译模型。

## 整板状态与剩余门槛

新候选已从上一任务复制 IP 缓存并完成完整顶层综合。厂商前置 hook 仍重建 MIG，未绕过该 hook；其工具库复制被只读保护替换成字节一致的空操作，未修改安装目录。完整综合检查点已保存，整板中的真实分片存储为 1 个 RAMB18E1，计数器最大扇出 13，通过结构检查。

整板综合估算为 53,965 LUT、72,263 寄存器、207.5 BRAM tile、79 DSP、24 BUFG。相对上一候选 54,364 LUT/72,225 寄存器/207 BRAM/23 BUFG，减少 399 LUT，增加 38 寄存器、0.5 BRAM 和摄像头分发使用的 1 个 BUFG；DSP 不变。该比较是综合估算，不是布线后资源、功耗或帧率。`preview-implementation-inputs.json` 绑定实际源码、RTL 副本、存储/网口约束、检查脚本、DCP 和复用证明。

已用上一轮 `postroute-optimized.dcp` 完成整板布局引导，旧 f6 仍独立用于最终审核。布局后新增预览 from/to 建立均为 +0.002 ns，保持 −0.346 ns，粗门槛通过并保存 `preview-placed.dcp`；整板布局估算建立 −0.285 ns、保持 −2.906 ns，不能称为整板时序通过。

随后在同一工程执行原定 `AggressiveExplore` 物理优化，约 3 分 17 秒，得到布线前全局建立 −0.150 ns、保持 −0.359 ns。原厂 route-post hook 和所有检查保持，释放继承的共享时钟走线、保留专用 DDR 物理路径后，完成本候选第一次完整布线，路由步骤耗时约 1 小时 42 分 9 秒。116,585 条可布线网络全部连接，路由错误为 0；建立 −0.467 ns、保持 +0.026 ns，仍有 230 个建立失败端点。连接完成不等于时序通过。

随后仅从该路由检查点执行一次官方后路由物理优化，没有重新综合或布局。初次启动遇到生成运行脚本在打开 DCP 前读取 `current_project/TOOL_FLOW` 的顺序错误；`repair_postroute_runner.py` 保存原脚本和补丁，只把查询移到 `open_checkpoint` 之后，再运行原任务副本的 runner。真实执行结束标记与 `ai7030_edif_top_postroute_physopt.dcp` 已生成，不能把先前失败的父驱动脚本记作成功。优化步骤约 2 分 34 秒，建立改善到 −0.422 ns、保持仍为 +0.026 ns，230 个建立失败端点尚未消除。两项既有 NPU 1 GHz 脉宽失败仍为最差 −0.409 ns。

最差路径定位到原厂摄像头写 FIFO 的粘滞溢出标志：由 `write_clk` 产生，直接进入 `mem_clk` 写帧状态机；另一条 −0.302 ns 路径来自 125 MHz MAC 欠载事件直接进入 150 MHz 诊断寄存器。后续在独立任务 `D:/yzd/tmp/pl-status-cdc-eco-20261025` 增加单比特状态同步，并在已经布线的 DCP 上尝试局部修改；本候选源码与 DCP 保持冻结。同步 RTL 的 32 组时钟/相位测试、实际原厂写帧状态机的 24 组溢出/恢复测试、预览控制 12 组复位相位测试已通过。这些结果不代表局部修改已完成或整板时序已通过。

`assert_pl_chunk_ram.tcl` 会在整板综合和实现中检查真正推断到块 RAM，且分片计数器不再出现高扇出。之后仍须完整路由、建立/保持检查、全部邮箱/CDC/总线偏差、DDR 校准驱动及引脚/NPU 对照通过。既有 NPU 1 GHz 脉宽问题与原异步摄像头切换风险仍需单列，不能以保留原参数代替生产签核。没有板端预览或帧率验收。

## 本地来源与归档

关键来源为上述任务的功能报告、OOC 报告、`functional-admission.json`、`preview-staging.json`、`school-manager/receipt.json`、整板综合日志、`routed-before-postopt/`、`postroute-runner-repair.json`、实际实现运行目录的后路由 DCP/时序报告/结束标记，以及前一任务冻结的源码和路由后报告。主要实现文件为 `rtl/wcis_jpeg_udp_packetizer.v`、`scripts/prepare_pl_jpeg_preview.py`、`scripts/assert_pl_chunk_ram.tcl`；中止台架为 `sim/tb_jpeg_udp_packetizer.sv`。后续状态同步的本地来源为新任务 `status-summary.json`、`writer-summary.json`、`control/summary.json`、`frame-error-cdc.patch` 与实际工具日志。

本记录与前一轮记录分别作为来源块合并归档至 `D:/bigfuture/竞赛/记录/2026-10-25.md`，保留当日其他内容。
