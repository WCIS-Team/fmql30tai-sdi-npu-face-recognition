# 板端恢复排查与预览程序保护

**后续更新**：用户明确授权后已恢复厂商 BOOT 并重启，SDK 控制接口及硬件 VTC
到接收端路径已验证；真实摄像头仍为 0 帧。详见
[厂商恢复与通路验证](board-factory-restore-20261014.md)。以下保留恢复前的准备阶段记录。

## 当前结果

板子已恢复 SSH；本轮没有执行复位、重启或替换 BOOT。当前 boot_id 为
`ea7deb05-4703-4056-91f8-03fedac3727b`，不同于故障启动的
`c02a944b-fff1-4c48-a38e-b7c16e25c1fd`。

只读挂载 SD 启动分区后实测 BOOT.bin：

- MD5：`0f4f00e1de0af8f70299572be622e45a`。
- SHA256：`6e81a17a9fb429607b619c653598d4c260c9d820b835e583d8e87bfb6532cb85`。
- 与仓库记录的无 NPU、带 SDI 状态导出版本一致。
- `/dev/udmabuf0` 的 SDIS magic 正确、序号持续增加，证实当前 PL 的状态导出在运行。

这进一步支持 SDK 对缺失寄存器桥的访问导致无响应的判断，仍未捕获本次具体卡住的
MMIO 地址/内核栈。卡上镜像身份和状态导出行为不能单独证明故障瞬间的总线事务。

故障启动的心跳最后一条为 2026-10-13 16:14:19 UTC；约十秒后启动旧预览程序。
该条可用 RAM 为 770920 KiB、swap 尚未使用、CMA 空闲 130784 KiB、D 状态进程数 0。
没有 OOM 证据。故障启动在 journal 的定向查询中没有可取得的条目；未继续扫描大日志。
本轮保留完整心跳副本供后续分析。

## 已落实的修正

1. 原事故程序的二进制内容保留且 SHA256 不变；移除执行位，原启动脚本另存为不可执行的
   `run-preview.sh.disabled-original`，现启动脚本直接退出 78，不进入 SDK。
   旧 `/root/wcis-vision/20261013-ea8135622061` 在恢复后的板上不存在，未改其他目录。
2. C++ 源码在 `Device::Open` 之前无条件拒绝硬件取帧，已重新交叉编译并部署到独立目录
   `/root/wcis-camera-preview/releases/20261013T165427Z-84aeb8c08079`。
   新 SHA256 为 `84aeb8c08079fd866563cf5a163a138b3eb166674f6e02d9d3f250408db62597`。
   板端直接传 `--run-camera` 也返回 2，未出现 SDK 初始化输出；启动脚本返回 78。
   该包是保护版，不能标为可采集图像的发布版。
3. 新增独立 `sdi_status_sender.py`：只读已验证的 DDR 状态页，不加载 SDK，没有
   `/dev/mem` 兜底，不读图像、不写取帧寄存器。每次只通过驱动对首 64 字节进行 CPU
   缓存维护，使用临时打包参数，不改全局 sync_offset/size/direction。
   参数格式依据 [u-dma-buf 官方说明](https://github.com/ikwzm/udmabuf/blob/master/Readme.md)，
   本板驱动版本 3.2.5 已实测接受该命令，全局属性在试验后未变。
   两次状态快照相同才接受，降低跨五个 AXI beat 更新期间的混合读数；它仍不是帧身份协议。
4. 网页新增板子连接、输入锁定与采集通路状态。诊断数据走 `/api/device-status`，
   不进入像素/模型结果通道，不会增加图像帧数；超时后不再显示实时连接。

## 验证与真实输入状态

- 新增 4 项诊断接口检查通过，原像素/模型绑定接口 13 项 Python 回归检查通过。
- 板端 15 秒状态试验正常退出，15 次采样，后 14 次序号均增长，15 次均没有 SDI 锁定；
  宽高为 0。用户确认摄像头仍然通电、接原来的接口。
- 试验后 SSH、心跳正常，boot_id 未变；没有硬件自动重试。
- 浏览器已实际显示“板子已连接 / 未锁定输入 / 采集通路待修复”，无摄像头像素帧。
- 单独启动诊断发送程序运行 3600 秒，进程号 565，日志位于
  `/root/wcis-camera-preview/status-20261014/status.log`；无自动重启、开机启动或固件改动。
  电脑接收服务为 `http://192.168.1.106:8088/`；不执行取帧。

当前有两个独立问题：现有 BOOT 缺少 SDK 采集控制桥，且 SDI 接收器没有锁定输入。
模型未接入不是这两个问题的原因。恢复桥也不能承诺摄像头一定锁定；还需要核对有效
输入端口（资料中的单路 XS1/SDI0_RX）、摄像头输出、线材、接收时钟/GT 配置。

## 已准备但未执行的固件恢复方案

已只读下载并校验卡上的 BOOT.bin 与厂商 BOOT.bak，保存到
`outputs/camera-preview/boot-recovery-prepared/`，manifest.json 记录完整校验值。

| 角色 | 文件 | MD5 |
|---|---|---|
| 当前固件备份 | BOOT.current-backup.bin | 0f4f00e1de0af8f70299572be622e45a |
| 厂商恢复候选 | BOOT.factory-candidate.bin | aca4612b566738350a8c5edac0db1929 |

厂商候选与仓库记载的包含 NPU/SDK 透明桥版本一致。它是已有镜像备份，
不是本轮未通过验收的新 RTL/BOOT 候选。

若明确选择该方案：先停止本任务的诊断发送进程，重读卡上当前 BOOT 校验值以防期间被
其他工作修改，再额外保留卡上备份；上传校验后的厂商候选，写入后同步并复验，然后重启。
重启后先核验 SSH、boot_id、BOOT 身份和进程，再设计最小 SDK/寄存器桥验证，最后才取帧。
旧保护程序保持禁止取帧；不能只恢复 BOOT 就解除门禁或直接跑旧启动脚本。

该切换会改变板上 PL 功能并中断所有板端运行任务，厂商版不保留现有独立 SDIS DDR
状态导出，因此当前诊断程序也不能直接延续。恢复桥与处理各种 SDI 输出是不同验收项。
按项目 AGENTS.md “不自行改变……启动分区”，本轮停在准备完成，不写入启动分区。

## 证据

- outputs/camera-preview/recovery-readonly-inventory.json、recovery-diagnostics.json。
- outputs/camera-preview/recovery-heartbeat.log、recovery-status-raw.jsonl。
- outputs/camera-preview/recovery-deployment.json、recovery-validation.json。
- outputs/camera-preview/device-status-tests.json、recovery-raw-tests.json。
- outputs/camera-preview/recovery-status-trial.jsonl、browser-recovery-status.png。
- outputs/camera-preview-guarded/cross-build.json、board-deployment.json。
