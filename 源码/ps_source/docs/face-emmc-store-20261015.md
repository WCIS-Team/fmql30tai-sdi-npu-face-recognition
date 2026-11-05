# eMMC 人员库与原帧复用上板记录

2026-10-15 已完成：eMMC 接口位流和设备树上板；人员库迁移至 eMMC；
每人保留一张原始图片、多份特征；修复厂商镜像自动挂载问题，并通过再次重启验收。
本阶段验收应用 `/root/wcis-face/apps/photo-emmc-3f5fb64b8c2b`，
页面仍为 `http://192.168.1.113:8091/`。

后续原帧驻留优化已更新应用，存储布局不变；现役版本见[原帧单次上传记录](face-retained-ddr-20261015.md)。

## 数据放在哪里

- SD `/dev/mmcblk0` 仍负责启动及根文件系统，根分区为 `/dev/mmcblk0p2`。
- eMMC `/dev/mmcblk1`，设备名 `Y2P032`，设备报告容量 31,268,536,320 bytes
  （29.1 GiB）；并非先前所说的 SD 配卡容量。没有做全容量破坏性扫测。
- 专用数据分区 `/dev/mmcblk1p1`，ext4，挂载 `/mnt/wcis-emmc`，
  UUID `67104a06-74a6-4268-a124-269d1b232a28`。
- 活动人员库 `/mnt/wcis-emmc/wcis-face/galleries/a49114c2174ff0b1/gallery.json`；
  同目录 `originals/` 每人一个原始文件，按实际图像类型返回 MIME。
- 迁移实数：4 人、7 份 512 维特征、4 张原图。全部原图 SHA 与上传/样本原文件一致，
  未把旧 PNG 预览重新命名成原图。原库的人员、样本及向量值保持一致，没有重跑模型。

这是接在 PL 引脚上的 eMMC，经 EMIO 连接 PS 的原生 MMC 控制器，文件系统由 Linux 管理。
没有实现 PL 自主读取文件或 PL 人脸向量比对。特征中心在 PS RAM 缓存，数据库原子更新后
刷新缓存；正常识别不反复从 eMMC 读取特征正文，也不读取登记原图、不重跑登记模型。
本次保存位置改变不等同于 NPU 推理本身加速。

## 保存和删除规则

同名追加登记仍对新照片执行一次 PL 预处理及 NPU 检测/特征提取，只保存新增向量。
首张原图保留为人员代表图；以后删除该张照片对应的特征，也继续保留这张代表图，
直到删除最后一份特征或删除整个人员。网页以“份特征”显示并提供逐份删除。

新登记的输入、对齐图和模型输出属于临时工作目录，成功、无效图片及失败路径均执行清理。
清理和写入完成后才释放忙碌状态并发送响应，避免多选连续登记的下一张误收 409。
现有识别查询的诊断图片、演示结果未在本次删除；“每人一张”指活动登记库。

原 SD 库 `/root/wcis-face/galleries/a49114c2174ff0b1` 及迁移前备份仍保留用于回退，
不再被现役服务用于登记和识别。备份包含历史图片，不能宣称整块板只剩四个图片文件。
新库删除会移除活动特征及最后一份特征对应的原图，不建立新的图片回收目录；
这也不代表存储介质上的取证级安全擦除。

## 硬件依据与实现范围

手册来自本机 `Downloads/Telegram Desktop/悟净开发板硬件使用手册V1.0_集创赛.pdf`，
已按用户要求复制到 `C:/Users/anxianji/Downloads/20260916/`，
并与学校服务器厂商资料副本核对 SHA-256：
`c50d3c99b90e065ae6bddbe7c982a6b5b7c1cb76cf9c8289d9a29706e51cff93`。

手册第22页文字称 Bank11，但第23页原理图及工具封装球脚一致指向 Bank13；
按精确球脚核对，没有依据该文字直接猜引脚。初期采用原生控制器、4-bit、最高25 MHz SDR，
保留官方 SDI、DDR、AI_Mate/NPU、既有 FAC1 及 SD 启动接口。

| 信号 | 封装球脚 | IO 标准 |
|---|---|---|
| CLK | AA20 | LVCMOS18 |
| CMD | AA19 | LVCMOS18 |
| RESET_n | AB19 | LVCMOS18 |
| D0 / D1 | AA18 / AC18 | LVCMOS18 |
| D2 / D3 | W19 / W18 | LVCMOS18 |

电平依据原理图 VCCQ/Bank VCCO 1.8V；芯片主电源3.3V。Linux `ios` 的默认 signal-voltage
报告为3.3V，不当作板上 VCCQ 实测，也没有据此改变引脚电平。驱动实际为 PIO、4-bit、25 MHz。

在隔离 case 完成综合、布局布线、官方 DISABLE_ICAP/VCCM 补丁和 Procise 676H 打包。
全部可布线网络完成，setup WNS +0.030 ns、hold WHS +0.022 ns，无 setup/hold 违规。
原厂 1 GHz NPU 核仍有2项最小周期告警，WPWS -0.409 ns；不作全设计生产时序签收。
新增 eMMC 输入按保守外部预算进行后布线检查；该预算不是 AT70B32G 实测 AC 参数。
工具对 PS7 SDIO 输出没有给出完整可分析时序路径，故不能声称外部输出接口完整静态时序闭合。
25 MHz 功能读写和重启验收不能替代器件 AC/板级偏斜签收或长期掉电耐久验证。

设备树工具只改 `/amba-apu@0/dwmmc@e0044000`，4-bit、25 MHz、non-removable；
其他节点、属性和保留内存逐项核对不变。工具使用上游 libfdt v1.7.2，
commit `2d10aa2afe35527728db30b35ec491ecb6959e5c`，使用学校服务器已有编译产物。
FSBL、BL31、U-Boot 三个 PS 载荷与上一版逐字节一致。

## 自动挂载故障和修复

首次重启后 eMMC 和分区正常，但 `fstab` UUID 项依赖 `/dev/disk/by-uuid/`。
实测厂商镜像不存在 `systemd-udevd.service`，也没有该目录，导致 mount 与识别服务依赖失败。
不能把手动挂载成功当作开机恢复成功。

移除本次新增的 UUID fstab 行，改用 `wcis-face-storage.service`：等待指定 MMC 分区，
确认它确在 eMMC 上，使用 blkid 核实 ext4 类型及精确 UUID，未挂载时执行受限 e2fsck，
再挂载。识别服务 Requires/After 此存储服务，启动及请求均校验存储身份，失败不回退 SD。
没有改系统全局 udev，也没有新增格式化或自动建库行为。首次建分区前未发现文件系统/分区签名，
头、中、尾各4 MiB读取为零，首尾备份保存在板端任务目录；未访问 eMMC boot0/boot1 的写接口。

## 验收与耗时

- 数据迁移、追加、逐份/整人删除、异常写入前后恢复、错误/丢失挂载拒绝、原图字节及 MIME、
  特征缓存不重复加载与更新失效检查通过。隔离 HTTP 服务实际完成两次 NPU 登记及坏图拒绝，
  登记工作图片无遗留；临时验证人员和目录已清理，未修改正式登记数据。
- 4 MiB写入及 fsync、读回 SHA、卸载重挂载和最终系统重启后的 SHA 校验通过；测试文件已删除。
- 修复挂载服务后的重启号 `afafcc68-d240-40a9-983a-4288addfd81e`。
  存储和识别服务自动恢复 active，人员 JSON 与所有代表图 SHA 一致，NPU 两模型输出与旧基线一致。
- 同一用户测试原图，重启后首次处理1052.9 ms、板端 HTTP1470.9 ms；随后两次处理
  742.1/737.5 ms、HTTP1060.1/1047.7 ms。它们不含电脑网络及浏览器加载，大图可能更慢。
- 原帧复用已先行部署：每张图只构建一次受控 BGRX 快照，检测缩放和五点对齐复用；
  仍有两次 PL DDR 上传，没有声称零拷贝或 DDR 常驻帧缓冲。摄像头和实时吞吐尚未验收。

## 身份与回退

当前 BOOT SHA `4be162a9be2f572bddce129465d1305932f114f236f08fbc2161f34e4251f77f`；
DTB SHA `e7edf0bc5eb31485962c9bfbefff60c250c9ec14363ccdd41a695173a127d3af`。
SD启动分区中 `FEC1015.BAK` 与 `FDT1015.BAK` 分别保留上一版 BOOT 与 DTB，
对应 SHA `0e44eea591fb9dcfba724ddde17b590d5ce0005904d87f6edbcae8c6e20ae0d2`
及 `4e690cf065424e28ad7e39e0dc87a72f4c593f5bd4d99c11f7c4e892feee3038`。
硬件试验的自动回退定时器已停止并禁用，不会在后续启动擅自恢复旧硬件。
软件原服务、网页及完整旧人员库备份在板端 `/root/wcis-face/candidates/emmc-20261015/`。
以后发生的新登记位于 eMMC，回退旧 SD 库前须先保存其增量，不能直接把旧库当最新数据。

## 可复核文件

源码：`npu_photo/persistent_gallery.py`、`migrate_gallery.py`、`serve_photos.py`、
`gallery.py`、`scripts/mount_face_store.py`；仅作必要网页显示及部署参数保留接线。
独立构建及日志均在 `D:/yzd/tmp/face-emmc-store-20261015`，主要证据：
`hardware-source-manifest.json`、`emmc-case.patch`、`timing*.rpt`、`route_status.rpt`、
`boot-candidate/manifest.json`、`dtb-verification.json`、`emmc-inspection.json`、
`filesystem.json`、`store-verification.json`、`migration.json`、`mount-startup-diagnostic.json`、
`storage-startup-fix.json`、`live-after-reboot.json`、`final-state.json`。
后台项目站点本轮 HTTP200 已读取；模型及推理 ELF 未重新编译。
