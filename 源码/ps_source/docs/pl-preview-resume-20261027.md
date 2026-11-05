# PL 千兆预览续作（2026-10-27）

本轮继续 1920×1080 SDI → PL JPEG → WJP1/UDP → PL RGMII → 电脑接收预览，任务目录为 `D:/yzd/tmp/pl-preview-resume-20261027`。本轮未访问板端硬件、重启服务或写启动分区。现役 PS/VPU 预览与人脸/PAD 服务不因本轮离线工作切换到 PL。

## 全分辨率发送与接收验证

`functional-1080p/summary.json`：实际 SDI 流桥、JPEG、分包和 MAC RTL，物理 DDR 输出接口使用行为模型，完成 1 帧 1920×1080、212 个 UDP 包，无拒帧或中止。

`native-1080p-optimized/summary.json` 与 `execution-receipt.json`：相同完整分辨率测试，使用实际发送 SERDES 和 Xilinx 原生仿真原语；仅关闭波形调试并使用 xelab O3 优化，没有降低分辨率、裁掉帧或替换发送 RTL。xsim 执行约 1048 秒，1 帧、212 个 UDP 包，无拒帧或中止。检查以太网 FCS、IPv4/UDP 校验和、会话/分包重组、JPEG 解码、几何及测试图像素。

两种物理输出仿真的 JPEG 均为 296427 字节，SHA256 为 `59e51e5e626e60da386d1c2611fc9db95ec98e9a519877e9cc62277f38c10527`，逐字节一致。解码为 1920×1080，测试渐变图平均绝对像素误差约 3.537/255。单帧仿真不能给出持续帧率、真实摄像头画质、亚稳态或板端网络结论。

标准调试配置的原生仿真此前在 600 秒超时，未记作通过；保留 `native-1080p` 的不完整输出。优化后的执行超时明确为 1500 秒，实际完成。`native-small-rechecked` 对旧 256×64、3 帧原生捕获先核验编译源散列再重检通过，这是旧捕获重检，不是本轮新仿真。

`receiver-loopback.json`：把完整原生仿真的 212 个 UDP 负载通过本机 UDP 送入真实 `lan_stream/receive_pl_jpeg.py`，HTTP 状态、快照、MJPEG 响应及网页入口检查通过；取回的快照与上面的 JPEG 散列相同，无转码，过期后状态为 `no_fresh_frame`。这是本机回环和真实接收软件集成验证，没有经过板卡 PHY、交换机或物理网线。另运行 5 项预览适配器测试、1 项慢客户端测试，均通过。

`manager-reuse-check.json` 重新核对现有学校服务器 AArch64 PHY 管理程序的构建收据、当前源码和二进制散列，均一致；因此无需重复交叉编译。本轮没有调用它访问 PHY，也未把历史构建成功写成当前千兆协商成功。

校验器 `scripts/verify_pl_preview_pipeline.py` 原先固定要求 3 帧，但生成脚本已允许配置 1 帧。本轮修复为从 `simulation-config.json` 读取帧数；无配置时仍要求 3 帧，非法帧数拒绝，帧数/拒帧/中止检查保留。原文件及补丁在任务 `originals/` 和 `checker.patch`，没有改 RTL 以迎合测试。

## 布局布线与尚未通过的门槛

最好的既有完整检查点仍以 `D:/yzd/tmp/pl-status-cdc-eco-20261025/status-cdc-postopt.dcp` 为基线：建立 WNS −0.176 ns、215 个失败端点，保持 +0.029 ns、0 个失败端点。其旧 NPU 最小周期/脉宽失败单列，不能当作完整时序签核。

本轮对此前 17 个寄存器复制、2008 个消费者分流的检查点核对类型、初值、C/D/CE/复位驱动及移动后消费者接线，保存 `replica-input-audit.txt`。此为有限结构检查，不是整板形式等价证明。`fanout-cleaned.dcp` 清除实际物理父网络上的局部冲突，保留 1143 条既有固定 DDR 走线；不是清空全片重新布线。

Explore 路由曾在少量节点重叠间反复，日志中的中间 WNS −0.048 ns 不能当成已完成结果；只停止本任务拥有的进程树并保留日志。随后 Quick 仅用于可连通性诊断，完成 116617 条网络、0 路由错误，但建立 −4.947 ns / 1245 个失败、保持 −0.279 ns / 8 个失败，不可生成可用候选。它的后路由尝试未收敛，未保存为成功优化结果。

回到最佳基线执行 AggressiveFanoutOpt，完成后结果未改善。`optimize_best_fanout.log` 明确显示：优化器继承旧增量参考目标 −0.590 ns，因当前 −0.176 ns 已优于该目标，跳过了物理优化。`incremental-reuse.rpt` 确认该旧参考来自 `pl-jpeg-tx-pipeline-20261025/camera-clock-eco/postroute-opt/postroute-optimized.dcp`；不能把命令退出成功当作时序达标。安装版命令手册支持用新的真实增量检查点覆盖旧参考，本轮以最佳完整检查点重新建立参考并运行 Explore。`refresh_reference.log` 已明确记录 `place_design is using directive Explore with target WNS of 0 ns`，目标恢复为零违例。布局完成为 −0.175 ns，后续物理优化的中间估算曾到 +0.002 ns，保存 `refreshed-placeopt.dcp`；但布线出现拥塞，2026-10-27 23:03 达 1800 秒超时，由本任务驱动停止自有进程树。`refresh_reference-receipt.json` 为 `timed_out=true`，没有 `refreshed-routed.dcp`，不能把中间正裕量当作路由完成或签核。

没有降低时钟、放宽数据时序、改变引脚/电平/PLL 或修改已安装工具数据库；没有生成或部署 bit/BOOT。整板建立/保持、全部路由、跨时钟、DDR、TX、引脚/时钟一致性及打包校验通过后，才具备后续受控上板的基础。

## 完整源码候选准备

`source-build/` 从旧任务 case 只读复用已完成 IP 结果，重新准备当前预览源码、摄像头分布缓冲和写帧错误同步。首次准备暴露 `prepare_pl_jpeg_preview.py` 的 Python 作用域错误：函数尾部重复 `import re` 使前面的同步补丁分支访问未初始化的局部 `re`。删除该重复导入，使用已有模块级导入；原文件和补丁分别保存在任务 `originals/`、`stager.patch`。

失败的任务副本经绝对路径范围检查后保留为 `source-build-staging-failed/`，没有覆盖原案例或旧成功候选。修复后首次准备和再次准备均成功，保留新补丁/散列与完整 IP 缓存。准备成功不等于综合、布线或部署成功；此处与上面的网表优化分别记录。

## 物理网络条件与后续验收

用户确认 PL 网口接千兆交换机或路由器的千兆口，随后明确继续通过原网站看预览，接收端应按网站后台链路设置，而不是要求用户另配本机接收。`network-preflight.json` 的本机有线/Wi‑Fi 清单仅是当时客户端状态，不是最终接收目的地址。

`website-preview-path.json` 实时读取现有网页接口，仍为 `PS_VPU_JPEG`、960×540、ready；Linux 接收主机 `192.168.1.102` 的 `enp2s0` MAC 为 `b8:97:5a:46:20:07`，当时实际链路为 100 Mbps。PL 口和接收服务器均须实际协商千兆，才具备完整千兆路径。原网站入口可以保留，视频改由独立接收服务供给，尚未切换正式页面。

任务文件和原生仿真捕获已上传服务器隔离目录 `/home/user/.cache/wcis/pl-preview-resume-20261027`。首次无节奏突发发送的服务器回环测试未收到完整帧，测试失败；未记录为通过，测试子进程已在 finally 中退出。原因尚未定位。完整本机回环通过不能覆盖该服务器失败，后续将按捕获时间戳重放并保存接收状态，以区分测试突发、接收缓存和其他丢包原因。没有留下后台常驻服务，也没有替换网站服务。

本轮尚未核对 PL 实际协商、物理 LAN 的 UDP 接收、防火墙及持续丢帧。当前 TX 路线使用固定目的 MAC，须按真实接收路径设置，不能把路由器有千兆口等同于数据一定能送达后台。

后续在时序门槛通过后，核对候选/回退包与现场接线，再验证 PL PHY 1000/full、真实 SDI 输入、有效 JPEG/UDP、电脑预览、长稳丢帧以及与 NPU/录像共存。正式帧率、延迟与负载收益以板测为准。

## 本地来源与归档

本地来源：上述任务目录的运行脚本、收据、源散列、捕获、`summary.json`、`receiver-loopback.json`、各次 CAD 日志与报告，以及 `docs/pl-status-cdc-20261025.md`、`docs/pl-preview-pad-budget-20261026.md`、当前 RTL 和接收源码。补充读取 `D:/xiangmuwendang/WCIS-FPAI/repos/FPAI30TAI图像FPGA/README.md`；该快照不作为当前部署证明。

日期按客户端本轮 2026-10-27。2026-10-28 续作时核对了 27 日 23:03 的超时收据并补记结果；28 日的新构建、连接状态及联调另记当日文档。记录同步合并至 `D:/bigfuture/竞赛/记录/2026-10-27.md`，保留已有内容和来源文档。
