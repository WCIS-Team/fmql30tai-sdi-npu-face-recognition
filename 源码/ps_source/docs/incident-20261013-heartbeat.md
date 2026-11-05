# 2026-10-13 故障初查与自动心跳

## 当前结论

用户重启后已恢复 SSH。只读检查未发现能覆盖 2026-10-13 本次视觉应用运行的心跳或内核故障记录，不能认定 OOM、CMA 分配失败、AXI 阻塞、驱动死锁、NPU 损坏中的任一种原因。

事实与范围：

- `/root/hb` 共 20 个旧日志，最后一个记录到 2026-10-11 23:44 UTC，主要为音频 Python 测试。旧日志不能归因本次故障。
- `/usr/local/bin/hb.sh` 是 `/root/funasr/asr/hb.sh` 的软链接，需要调用 start 手动启动，没有发现针对本次应用的记录。此前运行没有启动它。
- 当前 `system.journal` 只列出重启后的 boot ID `763f9a3136a94e4783dd2ad1b6b661b8`。在故障附近 10:45–11:17 UTC 的查询没有条目。`journalctl -b -1` 返回了 10 月 11 日的旧启动，不能误当作刚才那一轮。
- 当前内核记录 ext4 非正常关机恢复和 journald 日志非正常关闭处理，能支持关机不正常，不能解释最初为什么卡住。没有 `/sys/fs/pstore` 崩溃记录目录。
- 根分区仍为 `/dev/mmcblk0p2`，ext4 rw，剩余约 9.6 GiB。没有发现本次安装的 `/root/wcis-vision` 目录。可能是未落盘数据丢失，也可能有其他清理操作；没有证据判定具体原因。
- 原板端参考 main 与本次 main 的差异为 help 入口与可选 vision_mode；测试配置没有该字段，新增模式分支不执行。新 BOOT/位流没有加载。因此不能将这次故障归因于新增 PL 门控逻辑的时序失败。

大致故障范围为：本次完整参考硬件应用运行引起板端响应异常；尚不能确定是设备打开、模型会话建立、相机/显示寄存器配置还是开始处理帧时出问题。硬件访问/驱动阻塞、内存压力均为待验证假设，没有可靠依据作概率排序。应用文件上传和 --help 不证明完整运行兼容。

本轮没有读写 FPGA 寄存器，没有重新运行视觉程序，没有替换 BOOT、启动分区或重启板子。只新增了用户要求的自动心跳服务。

## 新心跳服务

- 服务名：`wcis-heartbeat.service`。
- 程序：`/usr/local/libexec/wcis-heartbeat`，静态 AArch64 C 程序，单进程、单线程、不 fork，不依赖 Python 或 iCraft。
- 单元：`/etc/systemd/system/wcis-heartbeat.service`。
- 日志：`/var/log/wcis-heartbeat/heartbeat.log`，轮转为 `.1`、`.2`，以约 1 MiB 为轮转门槛，仅保留 3 个文件。单次采样批次可以小幅超过门槛。
- 每 10 秒读取启动 ID、uptime、时间、可用内存、空闲 swap/CMA、负载、D 状态进程数、最大 RSS 进程及视觉/阻塞进程的等待位置。同时从 `/dev/kmsg` 捕获新增内核信息，每轮最多 32 条。
- 每轮 fdatasync 同步日志以减少缓存丢失。系统或存储彻底阻塞时仍可能丢失最后一轮，不保证替代串口记录。
- CPU 调度 Nice=19；异常退出由 systemd 在 10 秒后拉起；60 秒内连续失败最多尝试 5 次，避免重启风暴。这里重启的是心跳进程，不是板子。
- 已启用 multi-user.target 开机启动。没有添加视觉程序的开机启动，也没有修改旧 hb.sh、音频任务或系统 rsyslog 配置。

学校编译全部在 `D:/yzd/tmp/wcis-fpga-20261013-62670b32/heartbeat`，只读复用现有交叉工具。首次动态链接的心跳程序因 sysroot GLIBC 2.33 与板端 ABI 不兼容，在进入 main 前退出；服务尚未启动。改为静态链接后，通过板端自检和单元检查。这个新心跳构建问题与前面的视觉应用死机不是同一个事件。

SHA256：`d6fdc8afb896db8e5bb0b07b0027f7205ca8c3a819f64968b9d316c80509999d`。

## 已验证与限制

- 指标解析自检通过，包括 `/proc/<pid>/stat` 的第 24 字段 RSS，以及带括号/空格的进程名。
- systemd 单元验证通过，服务 active/running、UnitFileState=enabled，开机链接存在。
- 只对该心跳服务主进程执行一次 SIGKILL；10 秒后自动拉起为新 PID，NRestarts=1。没有终止其他任务。
- 日志每约 10 秒继续更新，内核采集文件成功打开。
- `/proc/<pid>/smaps_rollup` 实测 RSS 648 KiB，PSS 640 KiB；`/proc/<pid>/status` 的小进程 RSS 统计滞后，未用它冒充精确测量。
- 21.02 秒采样中，用户态+内核态 CPU 增加 0.01 秒，约一个核心的 0.048%。这是本次空闲负载测量，不保证所有故障场景的相同占用。
- MemoryCurrent 和 CPUUsageNSec 为 not set，不能据此声称 systemd 16 MiB 内存上限已在该内核生效。资源占用使用 proc/smaps 独立测量。
- 新程序、服务文件及相关目录已单独同步。没有实际重启验证开机执行；已验证启用配置和运行时自动恢复。

## 查看与停止

```sh
systemctl status wcis-heartbeat.service --no-pager
tail -n 20 /var/log/wcis-heartbeat/heartbeat.log
```

如需停止并关闭下次开机启动：

```sh
systemctl disable --now wcis-heartbeat.service
```

后续硬件测试前先确认此日志正在更新，并把应用日志持续写出，再分阶段定位；本次没有重新尝试危险测试。

证据位于 `outputs/incident-20261013/`，包括心跳旧记录、当前 kernel、时间窗口查询、源码差异及新服务安装/资源测量报告。
