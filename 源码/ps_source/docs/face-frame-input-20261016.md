# ModelBackend直接帧回放入口

本任务于2026-10-15深夜开始，跨零点后的2026-10-16完成上板验证与入口安装。
任务临时目录仍沿用起始日命名 `D:/yzd/tmp/face-frame-input-20261015`。
后续无摄像头的ModelBackend联调使用帧回放入口，无需经网页逐张上传照片。

## 使用

在本机PowerShell运行：

```powershell
python D:/renlianshibie/fpga_project/scripts/run_frame_replay_board.py --frames 30
```

默认固定单人测试画面，自动执行30次识别并逐次输出结果，结束后退出。
可用 `--seed face-rgb565`、`--seed no-face`、`--seed two-faces` 切换已安装的测试源，
`--period-ms 1000` 设置每次处理的最短间隔。支持1～300次有界测试，不表示采集帧率。
Ctrl+C请求停止，等待在途帧完成及服务恢复。运行日志自动保存在独立的
`D:/yzd/tmp/face-replay-run-<id>/replay.log`。

已在板端SSH终端时也可运行：

```sh
python3 /root/wcis-face/run-replay.py --frames 30
```

启动器核对应用SHA、验证记录、当前启动号及照片服务单元，在硬件锁空闲时暂停照片服务。
每轮启动仅装载一次已打包的测试像素，后续直接从同一PL DDR帧缩放、检测、对齐、提取特征并比对。
运行结果不经过照片上传接口；`latest.json`保留最新结果，`timings.jsonl`保存小型逐次计时，
不把每次原图、裁切图或NPU张量留在持久存储。结果目录由 `REPLAY_OUTPUT` 行给出。
退出后恢复原照片服务；原服务是兼容/回退入口，本次没有改网页或登记功能。

## 实现与边界

- `npu_photo/recognize_frame.py`：将原有照片识别中的检测输出解码、对齐、特征提取及比对
  原样抽为共用计算入口。照片包装层和帧回放调用同一份逻辑、模型及阈值。
- `npu_photo/pl_preprocess.py`：增加已打包BGRX8/RGB565LE种子的初次装载及
  `resize_retained()`。调用者拥有种子文件，不删除其原文件；所有DDR地址仍由SDK分配。
- `npu_photo/run_frame_replay.py`：直接帧测试主程序，无照片参数、HTTP上传或图片解码。
  元数据明确写 `source=static_PL_DDR_replay`、`camera_input=false`、`content_updates=false`。
  固定内容的帧号保持不变，另用sequence表示处理次数，不将处理次数伪装成新采集帧。
- `scripts/launch_frame_replay.py`及 `scripts/run_frame_replay_board.py`：仅做有界测试的
  启停/设备所有权交接，不新增业务调度层、摄像头队列或网页。
- 通用照片部署辅助脚本增加共用计算模块，避免后续打包遗漏。

测试像素由本机已有公开样本提前打包，来源及原图SHA沿用
`photo_reference/data/public/sources.json`。RGB565参考图使用与RTL一致的位复制展开，
与其量化后参考像素比较，不把RGB565视为与原始8位颜色精度等价。
板端仍需要启动时经SDK写入一次测试像素；这是DDR静态测试种子装载，
没有PL内部产生人脸新帧、持续写帧、视频解码器或实际摄像头采集器。
PS仍做输出张量整理、框/关键点解码、对齐参数求解及特征比对。
真实摄像头还需接入缓冲完成/归还协议、格式/步长、帧身份和覆盖保护；
本次不接受猜测物理地址，也不把当前SDK的128MiB窗口/64MiB单帧上限外推为完整DDR验收。

## 验证

1. 共用计算抽取后，原有11张单人、无人脸和多人共13场景的PL像素、NPU原始输出SHA、
   框及适用时的特征/身份状态，与原已验收版本一致。
2. 新入口将 `cv2.imread` 替换为报错检查，仍完成BGRX单人10次、RGB565单人5次、
   无人脸3次、多人3次，共21次识别。每组末帧PL像素及NPU原始输出、适用时的分数
   与对应参考像素的照片路径完全一致。
3. 各组源图装载1次、PS原图打包0次；结束后的完整DDR原帧逐字节检查通过。
   未生成逐次持久图片，tmpfs交换区随退出清理。
4. 直接进程SIGTERM停止、独占硬件锁拒绝，以及完整SSH终端Ctrl+C停止通过。
   Ctrl+C测试请求300次，在完成第2次后停止；当前帧完成后再释放设备。
   SDK进程置于与终端分离的会话，终端中断只由启动器转成对Python主进程的停止请求，
   不对包含SDK/DMA进程的整个进程组发送中断，不使用SIGKILL。
5. 本机一键命令另完成3次自动识别，随后原服务ready。正式人员JSON/原图SHA、服务单元、
   boot_id均未变；最终空闲无PL工作进程、NPU设备句柄或tmpfs交换区遗留。

首次禁止解码的验证包装程序用 `runpy` 进入脚本时漏加模块目录，发生CPU导入错误，
未进入SDK；补齐测试包装程序路径后，仅继续未完成的帧入口测试，未重跑已通过13项回归。
原始失败和继续验证日志分别保留在 `verification.log` 与 `verification-resume.log`。
未以首次失败或重试掩盖功能/硬件结果。

## 部署身份与记录

帧回放应用：`/root/wcis-face/apps/frame-input-763dd048b8c3`。
模型版本仍为 `/root/wcis-face/releases/20261014-b5a454c11d22`，两个可执行文件沿用
此前学校服务器构建产物，本轮只有Python变更，无新C++/模型构建。
现役照片应用仍为 `photo-retain-dd13b53daa0e`；未替换该服务单元或BOOT/RTL。

板端启动配置：`/root/wcis-face/replay-current.json`；启动器
`/root/wcis-face/run-replay.py` 的SHA256为
`e776bc2a2ef0ca706c6408f26dfa6c0c1fd9f70bb816dade12193b28d75a381f`。
种子及证据：`/root/wcis-face/candidates/frame-input-20261015/`。
若重启导致boot_id变化，需先重新核对运行固件和后端，刷新已验收启动身份。
发生当前启动的硬件隔离标记时不自动恢复或重试设备访问。

本机证据目录：`D:/yzd/tmp/face-frame-input-20261015/`，主要文件为
`background-source.json`、`candidate.json`、`preflight.json`、`verification.json`、
`launcher-install.json`、`launcher-stop.log`、`launcher-stopped-latest.json`及
`launcher-verification.json`。普通3次启动记录另见
`D:/yzd/tmp/face-replay-run-755b3b55/replay.log`。
后台项目站点HTTP200已读取；页面仍写PS采集，本地厂商案例及当前目标为PL采集，
保留该来源差异，不将页面示意图当作当前采集实现证据。
