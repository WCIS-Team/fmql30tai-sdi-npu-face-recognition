# 原案例对照、VPU 直播准备与启动失联（2026-10-20）

## 最新结果（恢复连接后续做）

**已恢复连接和原工作位流；VPU内网传输用板内测试图通过，真实摄像头仍在等待SDI锁定。**

- 按用户要求采用直连 `192.168.1.102 → 192.168.1.113`。先前学校映射入口使用的SSH路径与本次直连入口不能直接当作同一可达性结果。已把 `ssh_transport.py` 的板端连接改为直连102再转113；学校构建连接保持原规则，凭证仍由原受保护入口读取。
- 恢复任务回执表明，原案例启动 `f19ee5b6-7cb4-43f9-b347-d188441229c8` 执行了已验收BOOT的恢复与重启；之后启动为 `73883f36-5a3f-4214-87f3-588437eb47ed`，照片服务和eMMC正常，恢复定时器已禁用。因此不能将此前SSH超时等同于原案例位流死机或不能进入Linux。没有完成完整原版YOLO+HDMI案例的运行／摄像头A/B验收。
- 用户随后要求跳过故障日志分析，未再展开心跳／内核根因分析；上述恢复结论依据启动文件、服务状态和恢复任务回执。
- 第一版VPU适配在成功采到1帧VTC图后，被NV12平面数检查阻止：驱动实际返回Y/UV两个平面，初版仅接受一个。无编码结果；这不是新的固件切换。修正双平面缓冲布局后在学校服务器增量编译，正常重启清理测试状态，当前启动为 `5e10dfdf-2905-4778-975f-cd7b0fe821d2`。
- 当前BOOT SHA256仍为 `f48397d08b1ccb1c950adafcebe5e36678154e73fa1d19792150aa5ddccd8ad1`，DTB/uEnv未变。后续VPU测试没有再改位流。
- 最终二进制 SHA256=`9dc1a528df4919c80ae78d0abd6c5fd7f0149129f16385154c593089c6a76b87`，与源码和板端文件核对一致。学校构建仍在本任务独立目录内，初版和增量回执分开保留。
- 最终版本VTC模式取得30帧、VPU编码30帧，进程返回0，HTTP取得960×540 JPEG并成功解码。另从102主机订阅MJPEG，取得5个不同帧号；本机Windows直接访问HTTP也成功。该跨主机测试是在双平面修正版上进行，最终版再通过同一编码路径的30帧板测。
- 已关闭测试源并切回真实camera模式。连续状态为 `waiting_for_sdi_lock`，真实采集与编码计数均0；新代码在未锁定时只被动等待，不先排队DMA捕获。当前没有摄像头JPEG，`/snapshot.jpg`正确返回503，页面没有显示旧测试图。
- 当前地址为 `http://192.168.1.113:8092/`，页面/采集服务active。为独占SDK，原照片服务暂停；eMMC服务仍active，人员库和全部原应用文件哈希与切换前相同。当前等待进程约15988KiB RSS、1线程，该值仅覆盖待机，不是编码峰值。
- 直播输出经PS网口；PL网口尚无收发逻辑。相机修复后可由当前等待进程开始采帧，但真正摄像头画面、色彩与持续稳定性仍需实测。没有把合成测试图或编码通过说成摄像头通过。
- 最新Python服务已重新部署；本机8项来源/旧帧拒绝测试通过。维护说明为 `lan_stream/VPU_LIVE.md`。当前采集未启用开机自动启动，重启后要重新核验BOOT/启动身份。

### 续做证据

`D:/yzd/tmp/board-recovery-via102-20261020/state.json`；
`D:/yzd/tmp/sdi-vpu-live-20261020/{build-receipt.json,rebuild-v2.log,vtc-result-v1.json,vtc-result-v2.json,vtc-result.json,vtc-vpu.jpg,lan-verification.json,pc-reachability.json,camera-result.json,final-state.json,summary.json}`。

以下为02:55左右的阶段记录；其中“尚未恢复”的状态已由上述最新结果取代，保留原始过程供复核。

## 当前状态：未完成板测，优先恢复

本轮已在学校服务器完成新的 SDI/VPU JPEG 程序交叉编译并部署文件，但没有运行原案例程序或新直播采集程序，也没有获得新摄像头帧。内网直播尚未验收，不提供“已跑通”的结论。
为做原案例对照，将 SD 的 `BOOT.bin` 切成厂商原版并请求重启后，SSH 未恢复。用户随后确认已断电重上电，管理连接仍超时。截至本记录，尚未恢复原启动文件或取得本次故障心跳。

## 操作与证据

切换前 boot_id 为 `d4c98f4d-da2b-4bb8-bd98-66a6dcfdde6c`；照片服务 ready，硬件锁可取得，未隔离；本地 `board-before.json` 保存应用、服务、人员库及设备树校验值。

1. 只读核对并取回当前 BOOT/DTB/uEnv，保留本地、板端根分区和 SD 副本。当前 BOOT 的 SHA256 为 `f48397d08b1ccb1c950adafcebe5e36678154e73fa1d19792150aa5ddccd8ad1`。
2. 核对原案例 BOOT 为 `0088581b738fdef741983d2dfd4dd52363d2d90fddc2fa4dafb30cfdb3b23fca`，与 Downloads 原件一致。原案例程序的 `.vendor.bak` SHA256 为 `ceab9cb128f2b78385a8b5c39c22b1fad2b6830505d5242ccd87affd4f53ab7a`，也与 Downloads 原件一致；板上另一个同名程序已被更换，未误当原件。
3. 先部署仅提供 HTTP 页面/状态的 Python 服务 `wcis-sdi-vpu-view.service`，监听参数为 `192.168.1.113:8092`，不打开任何设备。确认启动命令返回成功，但没有完成浏览器可达性或画面验证。
4. 停止并暂时禁用 `wcis-face-photo.service`，暂时禁用 `wcis-face-storage.service`，保存两者先前 enabled 状态。未修改分区表、DTB、uEnv、引脚、跳线、模型文件或人员库。
5. 设置 `wcis-factory-ab-20261020.timer`（OnBootSec=10min）恢复已验收 BOOT；它只能在系统服务启动后执行，不能覆盖 FSBL/U-Boot/内核早期挂起。
6. SD 另存当前 BOOT 为 `FAB1020.BAK`，写入临时文件、fsync、校验、替换 `BOOT.bin`，再次核对 BOOT、DTB、uEnv，卸载 SD 后才请求 `systemctl reboot`。
7. 本机客户端时间约 2026-10-20 02:42:57 发出重启请求，随后板端 SSH 通道超时。跳板机 SSH 自身正常；从跳板机连接板子 IPv4 的 22/8092 和已知 IPv6 的 22 均超时。ARP 邻居仍显示此前 MAC 为 REACHABLE，此项不能证明用户态系统已启动。
8. 没有执行到原案例进程、新采集进程、NPU 模型或 VPU 编码。没有在开发板运行 CMake、编译器、模型转换或模型编译。

不能由这些证据确定是在关机阶段、引导阶段、内核、网络或其他位置卡住；也不能断言 OOM、驱动死锁或硬件损坏。原案例位流不含当前新增 eMMC 通路，而当前设备树仍保留该配置，这个组合的兼容性没有先完成本轮验证；仅禁用用户态存储服务并不能代替设备树兼容性核实。这是切换前检查不足，尚不是已证实根因。

## 心跳与恢复

已从心跳源码定位日志为 `/var/log/wcis-heartbeat/heartbeat.log`（1MiB 轮转，保留 `.1/.2`），包含 boot_id、内存/CMA、D 状态进程及可取得的内核事件，每10秒同步；另有历史 `/root/hb` 日志。
本轮 `read_incident_logs.py` 在建立板端 SSH 时即超时，没有取得任何新日志。未拿10月13日的本地旧日志解释本次失联。
已准备只读日志提取程序：连接恢复后应先取心跳、上一启动的内核日志、pstore、重启记录和恢复任务状态，不直接重跑硬件。

完整恢复文件在 `D:/yzd/tmp/factory-ab-20261020/before-BOOT.bin`，本地 SHA256 与切换前一致。`restore_sd.ps1` 是尚未执行的 PC 恢复脚本：要求明确的非系统 SD/USB 分区，并校验 DTB/uEnv/BOOT 身份，只备份并替换 BOOT 文件，不格式化卡。系统服务原状态及恢复任务配置也保存在 `preflight.json`，恢复后仍需核实服务与人员库。

## VPU 直播实现与验证边界

后台读取 `D:/xiangmuwendang/WCIS-FPAI/repos/vpu-live` 和 `wiki/PS/OrchestrationLayer/VPU串流直播SOP.md`。参考交付件的32个 MANIFEST.md5 校验全部一致，未修改外部仓库或 Downloads 原件。
采用参考中已有板测的 VPU JPEG 路线；没有把存在已知缺 SPS/PPS 问题的 HLS 路线直接当作可用浏览器流。

- 新 `ps_app/src/wcis_sdi_vpu_live.cpp` 复用厂商 SDICamera，以1920×1080输入、PL整数抽样到960×540 RGB565；PS按参考代码转NV12，VPU JPEG质量80、2缓冲、预览上限5fps。没有 HDMI 或模型会话。实际驱动协商、性能和画面尚未板测。
- 单次采集等待2秒，失败后不重试；待完成DMA不释放回SDK复用，启动隔离标记要求完整重启／审查。VTC和camera来源显式分开。
- VPU输出先复制出映射缓冲区再回队；帧身份、来源、boot_id、采集时间和JPEG封装成单个原子替换包，避免跨会话旧帧显示。
- 新 `lan_stream/vpu_live_server.py` 提供 `/api/status`、`/snapshot.jpg` 和 `/stream.mjpg`，最多4个直播连接，超过2秒的旧帧不显示，输入停机／换启动／换来源时拒绝继续展示缓存图。页面明确标注VTC不是摄像头。
- `scripts/run_sdi_vpu_capture.py` 要求当前启动文件检查记录、二进制哈希、独占NPU/摄像头锁及无其他VPU使用者；无自动重试。该启动器尚未运行。
- 学校服务器任务 `D:/yzd/tmp/wcis-camera-preview-vpulive-7f92df53`，任务目录独立，共享SDK只读；源码归档、编译日志、工具检查和二进制回执在 `D:/yzd/tmp/sdi-vpu-live-20261020`。
- 二进制 SHA256=`7c0d7ecc4f7f68135562caa9c11a9c1583f561242b233021b4efff2fbb35ec26`；ELF64/AArch64、源码与回执哈希核对一致，板上ldd未发现缺失依赖。这些不等于运行通过。
- 本机8项帧来源/新鲜度/HTTP旧帧拒绝测试通过。测试没有模拟摄像头或编码器来冒充硬件验收。
- Python网页源在首次部署后又补了会话校验等改动，最新源码尚未重新部署；不得把板上文件说成当前全部源码版本。

## 主要本地来源

- `D:/yzd/tmp/factory-ab-20261020/{preflight.json,reference-inventory.json,board-before.json,switch.json,switch.log,gateway-latest.json,before-BOOT.bin}`。
- 同目录恢复、日志提取及等待连接脚本；它们的计划内容与实际执行结果分别保留。
- `D:/yzd/tmp/sdi-vpu-live-20261020/{build-receipt.json,build.log,source-verification.json,ldd.txt}`。
- `fpga_project/docs/board-factory-restore-20261014.md`、`bitstream-health-20261020.md`及上述本轮源码。
